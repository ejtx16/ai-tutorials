"""Skill accuracy eval harness for Claude Code and GitHub Copilot CLI.

Method from https://developers.openai.com/blog/eval-skills:
    prompt -> captured run (JSONL trace) -> checks -> score you can compare over time.

Each case runs the target skill headless (`claude -p` or `copilot -p`) against a reference repo, then checks:
  trigger_match   skill fired exactly when it should
  skill_first     skill loaded before any other tool
  completed       run finished without error
  no_file_writes  (chat_only cases) nothing was written
  facts           every `must_include` pattern appears in the answer (grounded facts)
  forbidden       no `must_not_include` pattern appears (known-wrong claims)
  paths_exist     every file path the answer cites exists in the reference repo (hallucination check)
  files_created   every `expect_files` path exists after the run
  rubric          model grader confirms each rubric item against the `reference` files

Usage:
    python run_skill_eval.py --cases evals/<skill>.cases.json [--runner claude|copilot] [--repo PATH] [--only ID ...]
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

COPY_IGNORE = shutil.ignore_patterns(
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "runs")
MAX_REF_CHARS = 20_000
FILE_EXTS = set(
    "py js mjs cjs ts tsx jsx json jsonl md mdx txt csv tsv yml yaml toml ini cfg conf env lock html htm css scss "
    "sh bash ps1 bat cmd go rs java kt kts rb php c h cc cpp hpp cs swift sql xml svg ipynb vue svelte gradle "
    "tf proto graphql dockerfile pdf docx xlsx pptx png jpg jpeg gif".split())

GRADER_SYSTEM = (
    "You are a strict grader checking an AI answer for factual accuracy against reference material. "
    "Judge ONLY against the reference provided. A criterion passes only if the answer satisfies it "
    "and nothing the answer says about it contradicts the reference. Quote short evidence.")
GRADER_SCHEMA = {
    "type": "object",
    "properties": {"criteria": {"type": "array", "items": {
        "type": "object",
        "properties": {"criterion": {"type": "string"}, "pass": {"type": "boolean"},
                       "evidence": {"type": "string"}},
        "required": ["criterion", "pass", "evidence"]}}},
    "required": ["criteria"]}


def resolve_cli(name: str) -> list[str]:
    """Command prefix for a CLI. On Windows, bypass npm .cmd shims (cmd.exe mangles prompt quoting)."""
    path = shutil.which(name)
    if not path:
        sys.exit(f"{name} CLI not found on PATH")
    if os.name == "nt" and path.lower().endswith((".cmd", ".bat")):
        shim = Path(path).read_text(encoding="utf-8", errors="replace")
        # last match is the real entry point; earlier ones can be node.exe itself (%_prog%)
        targets = re.findall(r'"%dp0%\\([^"]+\.(?:exe|js))"', shim)
        if targets:
            target = str(Path(path).parent / targets[-1])
            return [shutil.which("node") or "node", target] if target.endswith(".js") else [target]
    return [path]


def parse_jsonl(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


# --- Runners: each returns a normalized run -------------------------------------------------------
# {"calls": [{"name", "input"}], "answer": str, "completed": bool,
#  "files_written": [paths], "cost": {...}}

def run_claude(prompt: str, workdir: Path, args, max_turns: int, trace_path: Path) -> dict:
    cmd = [*resolve_cli("claude"), "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(max_turns)]
    if args.model:
        cmd += ["--model", args.model]
    proc = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", timeout=args.timeout)
    trace_path.write_text(proc.stdout, encoding="utf-8")
    events = parse_jsonl(proc.stdout)
    calls = [{"name": c["name"], "input": c.get("input", {})}
             for e in events if e.get("type") == "assistant"
             for c in e["message"]["content"] if c.get("type") == "tool_use"]
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    written = [c["input"].get("file_path", "") for c in calls if c["name"] in {"Write", "Edit", "NotebookEdit"}]
    return {"calls": calls, "answer": result.get("result") or "",
            "completed": result.get("subtype") == "success" and not result.get("is_error"),
            "files_written": written, "cost": {"usd": result.get("total_cost_usd") or 0}}


def run_copilot(prompt: str, workdir: Path, args, max_turns: int, trace_path: Path) -> dict:
    # Copilot has no turn limit flag; --timeout bounds the run instead.
    cmd = [*resolve_cli("copilot"), "-p", prompt, "--output-format", "json",
           "--allow-all-tools", "--no-ask-user"]
    if args.model:
        cmd += ["--model", args.model]
    proc = subprocess.run(cmd, cwd=workdir, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", timeout=args.timeout)
    trace_path.write_text(proc.stdout, encoding="utf-8")
    events = parse_jsonl(proc.stdout)
    calls = [{"name": e["data"].get("toolName", ""), "input": e["data"].get("arguments") or {}}
             for e in events if e.get("type") == "tool.execution_start"]
    messages = [e["data"] for e in events if e.get("type") == "assistant.message" and e["data"].get("content")]
    final = [m for m in messages if m.get("phase") == "final_answer"] or messages
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    usage = result.get("usage", {})
    return {"calls": calls, "answer": final[-1]["content"] if final else "",
            "completed": proc.returncode == 0 and result.get("exitCode") == 0,
            "files_written": usage.get("codeChanges", {}).get("filesModified", []),
            "cost": {"premium_requests": usage.get("premiumRequests", 0)}}


RUNNERS = {"claude": run_claude, "copilot": run_copilot}


# --- Grader ---------------------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def grade(answer: str, rubric: list[str], reference: str, args) -> tuple[list[dict], dict]:
    prompt = (f"REFERENCE MATERIAL:\n{reference}\n\n"
              f"ANSWER TO GRADE:\n{answer}\n\n"
              "CRITERIA (grade each one, in order):\n" + "\n".join(f"- {r}" for r in rubric))
    try:
        if args.grader == "claude":
            # No user settings, plugins, MCP, skills or tools: small context, cheap, no side effects.
            cmd = [*resolve_cli("claude"), "-p", "--output-format", "json",
                   "--json-schema", json.dumps(GRADER_SCHEMA), "--system-prompt", GRADER_SYSTEM,
                   "--model", args.grader_model or "sonnet", "--setting-sources", "",
                   "--strict-mcp-config", "--disable-slash-commands", "--tools", ""]
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                  cwd=tempfile.gettempdir(), timeout=args.timeout)
            data = json.loads(proc.stdout)
            return data["structured_output"]["criteria"], {"usd": data.get("total_cost_usd") or 0}
        # copilot: prompt piped on stdin (no -p) to avoid command-line length limits; no tools available.
        cmd = [*resolve_cli("copilot"), "--allow-all-tools", "--available-tools=", "--no-custom-instructions",
               "--disable-builtin-mcps", "--no-ask-user", "-s"]
        if args.grader_model:
            cmd += ["--model", args.grader_model]
        full = (f"{GRADER_SYSTEM}\n\n{prompt}\n\nReturn ONLY JSON, no prose, matching this schema:\n"
                f"{json.dumps(GRADER_SCHEMA)}")
        proc = subprocess.run(cmd, input=full, capture_output=True, text=True, encoding="utf-8",
                              cwd=tempfile.gettempdir(), timeout=args.timeout)
        return extract_json(proc.stdout)["criteria"], {"premium_requests": 1}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        out = locals().get("proc")
        detail = (out.stdout[-300:] or out.stderr[-300:]) if out else str(exc)
        return [{"criterion": "grader", "pass": False, "evidence": f"grader failed: {detail}"}], {}


# --- Checks ---------------------------------------------------------------------------------------

def cited_paths(answer: str, roots: tuple[str, ...] = ()) -> set[str]:
    """File paths the answer cites in backticks, e.g. `src/auth.py:42` -> src/auth.py.

    `roots` are directory names/paths the run happened in; absolute paths under them are made repo-relative.
    """
    paths = set()
    for token in re.findall(r"`([^`\s]+)`", answer):
        token = re.sub(r"^\./", "", re.sub(r"(?<=\w):\d+(:\d+)?$", "", token))
        for root in roots:
            m = re.search(re.escape(root.replace("\\", "/").rstrip("/")) + "/", token.replace("\\", "/"), re.I)
            if m:
                token = token.replace("\\", "/")[m.end():]
                break
        if "://" in token or token.startswith("-") or re.fullmatch(r"/[\w-]+", token):
            continue  # URLs, CLI flags, slash commands like `/mcp`
        ext = token.rsplit(".", 1)[-1].lower() if "." in token else ""
        # bare names need a real file extension, so `pytest.approx` / `json.loads` aren't taken as files
        if "/" in token or "\\" in token or (re.search(r"\w\.\w+$", token) and ext in FILE_EXTS):
            if not re.search(r"\(|\)|=|\$|\*", token):  # skip code like foo.bar() or globs
                paths.add(token.replace("\\", "/"))
    return paths


def path_exists(repo: Path, rel: str) -> bool:
    if (repo / rel).exists():
        return True
    # tolerate cited paths relative to a subfolder, or bare filenames
    return any(p.as_posix().endswith("/" + rel) for p in repo.rglob(Path(rel).name))


def read_reference(repo: Path, refs: list[str]) -> str:
    chunks = []
    for ref in refs:
        for path in sorted(repo.glob(ref)) or [repo / ref]:
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")[:MAX_REF_CHARS]
                chunks.append(f"=== {path.relative_to(repo).as_posix()} ===\n{text}")
            else:
                chunks.append(f"=== {ref} === (not found)")
    return "\n\n".join(chunks)


def is_skill_call(call: dict, skill: str) -> bool:
    return call["name"].lower() == "skill" and str(call["input"].get("skill", "")).split(":")[-1] == skill


def evaluate_case(case: dict, skill: str, repo: Path, args, trace_dir: Path) -> dict:
    run = RUNNERS[args.runner]
    with tempfile.TemporaryDirectory() as tmp:
        workdir = repo if args.in_place else Path(tmp) / "repo"
        if not args.in_place:
            shutil.copytree(repo, workdir, ignore=COPY_IGNORE)
            if args.skill_dir:
                shutil.copytree(args.skill_dir, workdir / ".claude" / "skills" / skill, dirs_exist_ok=True)
        try:
            out = run(case["prompt"], workdir, args, case.get("max_turns", args.max_turns),
                      trace_dir / f"{case['id']}.jsonl")
        except subprocess.TimeoutExpired:
            out = {"calls": [], "answer": "", "completed": False, "files_written": [], "cost": {}}
        created = {f: (workdir / f).exists() for f in case.get("expect_files", [])}
        # agents sometimes cite absolute paths in the run dir; the temp dir name is unique, so match on it
        roots = (repo.as_posix(),) if args.in_place else (f"{Path(tmp).name}/repo", repo.as_posix())

    calls, answer = out["calls"], out["answer"]
    skill_idx = [i for i, c in enumerate(calls) if is_skill_call(c, skill)]
    checks, notes = {}, {}

    should = case.get("should_trigger")
    if should is not None:
        checks["trigger_match"] = bool(skill_idx) == should
        if should:
            checks["skill_first"] = bool(skill_idx) and skill_idx[0] == 0
    checks["completed"] = out["completed"]
    if case.get("chat_only"):
        checks["no_file_writes"] = not out["files_written"]
        if out["files_written"]:
            notes["files_written"] = out["files_written"]

    if case.get("must_include"):
        missing = [p for p in case["must_include"] if not re.search(p, answer, re.I)]
        checks["facts"] = not missing
        if missing:
            notes["facts_missing"] = missing
    if case.get("must_not_include"):
        found = [p for p in case["must_not_include"] if re.search(p, answer, re.I)]
        checks["forbidden"] = not found
        if found:
            notes["forbidden_found"] = found
    if case.get("check_paths", should is not False):
        bad = sorted(p for p in cited_paths(answer, roots) if not path_exists(repo, p))
        checks["paths_exist"] = not bad
        if bad:
            notes["hallucinated_paths"] = bad
    if created:
        checks["files_created"] = all(created.values())
        if not all(created.values()):
            notes["files_missing"] = [f for f, ok in created.items() if not ok]

    cost = dict(out["cost"])
    if case.get("rubric") and answer:
        criteria, grader_cost = grade(answer, case["rubric"], read_reference(repo, case.get("reference", [])), args)
        checks["rubric"] = all(c["pass"] for c in criteria)
        notes["rubric"] = criteria
        for k, v in grader_cost.items():
            cost[k] = cost.get(k, 0) + v
    elif case.get("rubric"):
        checks["rubric"] = False
        notes["rubric"] = "no answer to grade"

    return {"id": case["id"], "checks": checks, "notes": notes, "answer": answer, "cost": cost}


TRIGGER_CHECKS = {"trigger_match", "skill_first", "completed", "no_file_writes"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", required=True, help="cases JSON file")
    ap.add_argument("--runner", choices=RUNNERS, default="claude", help="agent CLI that runs the target skill")
    ap.add_argument("--grader", choices=RUNNERS, help="agent CLI that grades rubrics (default: same as --runner)")
    ap.add_argument("--repo", help="reference repo / working dir the skill runs in (default: cases 'repo' or cwd)")
    ap.add_argument("--skill", help="target skill name (default: cases 'skill')")
    ap.add_argument("--skill-dir", help="skill folder to inject into the temp repo copy (if not already installed)")
    ap.add_argument("--only", nargs="*", help="run only these case ids")
    ap.add_argument("--model", help="model for the target run (default: the CLI's default)")
    ap.add_argument("--grader-model", help="model for the grader (claude default: sonnet)")
    ap.add_argument("--max-turns", type=int, default=10, help="claude only")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per run")
    ap.add_argument("--in-place", action="store_true",
                    help="run in the repo itself instead of a temp copy (large repos; skill may modify files)")
    ap.add_argument("--out", default="runs")
    args = ap.parse_args()
    args.grader = args.grader or args.runner

    spec = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    skill = args.skill or spec["skill"]
    repo = Path(args.repo or spec.get("repo") or ".").resolve()
    cases = [c for c in spec["cases"] if not args.only or c["id"] in args.only]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / skill / f"{stamp}-{args.runner}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"skill={skill} runner={args.runner} grader={args.grader} repo={repo} cases={len(cases)} -> {out_dir}")
    results = []
    for case in cases:
        print(f"  running {case['id']} ...", flush=True)
        results.append(evaluate_case(case, skill, repo, args, out_dir))

    names = sorted({n for r in results for n in r["checks"]},
                   key=lambda n: (n not in TRIGGER_CHECKS, n))
    width = max([len(r["id"]) for r in results] + [4]) + 2
    print("\n" + "id".ljust(width) + "".join(n.ljust(15) for n in names))
    for r in results:
        cells = [("PASS" if r["checks"][n] else "FAIL") if n in r["checks"] else "-" for n in names]
        print(r["id"].ljust(width) + "".join(c.ljust(15) for c in cells))

    def score(pred):
        vals = [v for r in results for n, v in r["checks"].items() if pred(n)]
        return sum(vals), len(vals)

    t_pass, t_total = score(lambda n: n in TRIGGER_CHECKS)
    a_pass, a_total = score(lambda n: n not in TRIGGER_CHECKS)
    cost = {}
    for r in results:
        for k, v in r["cost"].items():
            cost[k] = cost.get(k, 0) + v
    pct = lambda p, t: f"{p}/{t} ({p / t:.0%})" if t else "n/a"
    cost_str = ", ".join(f"${v:.2f}" if k == "usd" else f"{v} {k.replace('_', ' ')}" for k, v in cost.items())
    print(f"\ntrigger/process: {pct(t_pass, t_total)}   accuracy: {pct(a_pass, a_total)}   cost: {cost_str}")

    if results and all(not r["answer"] for r in results):
        print(f"\nWARNING: every run returned no answer. The {args.runner} CLI probably failed "
              f"(not logged in / not on PATH). Check the traces in {out_dir} before judging the skill.")
    for r in results:
        for key, val in r["notes"].items():
            if key == "rubric" and isinstance(val, list):
                for c in val:
                    if not c["pass"]:
                        print(f"  {r['id']}: rubric FAIL - {c['criterion']} | {c['evidence']}")
            else:
                print(f"  {r['id']}: {key}: {val}")

    summary = {"skill": skill, "runner": args.runner, "grader": args.grader, "repo": str(repo),
               "timestamp": stamp,
               "trigger_score": t_pass / t_total if t_total else None,
               "accuracy_score": a_pass / a_total if a_total else None,
               "cost": cost, "results": results}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary: {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
