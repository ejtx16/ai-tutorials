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

Eval folder layout (the eval dir can live anywhere; see --eval-dir):
    <eval-dir>/cases/<skill>.cases.json
    <eval-dir>/runs/<skill>/<timestamp>-<runner>/{<case-id>.jsonl, summary.json, report.html}

Usage:
    python run_skill_eval.py --cases <skill> [--eval-dir DIR] [--runner claude|copilot] [--repo PATH] [--only ID ...]
    python run_skill_eval.py --cases path/to/<skill>.cases.json ...
    python run_skill_eval.py --report <eval-dir>/runs/<skill>/<run>   # rebuild report.html from summary.json
"""

import argparse
import datetime
import html
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
CASES_DIR, RUNS_DIR = "cases", "runs"
EVAL_DIR_ENV = "SKILL_EVAL_DIR"
MAX_REF_CHARS = 20_000
FILE_EXTS = set(
    "py js mjs cjs ts tsx jsx json jsonl md mdx txt csv tsv yml yaml toml ini cfg conf env lock html htm css scss "
    "sh bash ps1 bat cmd go rs java kt kts rb php c h cc cpp hpp cs swift sql xml svg ipynb vue svelte gradle "
    "tf proto graphql dockerfile pdf docx xlsx pptx png jpg jpeg gif".split())
MIME_RE = re.compile(r"(application|audio|font|image|message|model|multipart|text|video)/[\w.+-]+", re.I)
# where agents install personal skills; checked for cited skill files and for --isolated injection
SKILL_HOMES = ("~/.claude/skills", "~/.copilot/skills", "~/.agents/skills")
PROJECT_SKILL_DIRS = (".claude/skills", ".github/skills", ".agents/skills")

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
    if args.isolated:
        # project settings only: no user settings, hooks, plugins, personal skills or user MCP servers
        cmd += ["--setting-sources", "project", "--strict-mcp-config"]
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
        if ("://" in token or token.startswith(("-", "@")) or MIME_RE.fullmatch(token)
                or re.search(r"/:|[{}<>]", token)):
            continue  # URLs, CLI flags, scoped packages, MIME types, route params like `/users/:id`
        ext = file_ext(token)
        if token.startswith("/") and ext not in FILE_EXTS:
            continue  # routes and slash commands like `/api/users`, `/mcp`
        # bare names need a real file extension, so `pytest.approx` / `json.loads` aren't taken as files
        if "/" in token or "\\" in token or (re.search(r"\w\.\w+$", token) and ext in FILE_EXTS):
            if not re.search(r"\(|\)|=|\$|\*", token):  # skip code like foo.bar() or globs
                paths.add(token.replace("\\", "/"))
    return paths


def file_ext(path: str) -> str:
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def installed_skill_dirs(skill: str) -> list[Path]:
    return [p for home in SKILL_HOMES if (p := Path(home).expanduser() / skill).is_dir()]


def is_checkable(rel: str, bases: list[Path]) -> bool:
    """Extensionless tokens like `origin/main` or `owner/repo` are usually git refs or repo names, not files:
    only check them when their first segment exists."""
    if file_ext(rel) in FILE_EXTS or Path(rel).expanduser().is_absolute():
        return True
    return any((base / rel.split("/")[0]).exists() for base in bases)


def path_exists(bases: list[Path], rel: str) -> bool:
    path = Path(rel).expanduser()
    if path.is_absolute():
        return path.exists()
    if any((base / rel).exists() for base in bases):
        return True
    # tolerate cited paths relative to a subfolder, or bare filenames
    return any(p.as_posix().endswith("/" + rel) for base in bases for p in base.rglob(Path(rel).name))


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


def copy_ignore(skip: set[Path]):
    """COPY_IGNORE plus exact folders (the eval's cases/ and runs/), so the skill can't read expected answers."""
    def ignore(directory, names):
        here = Path(directory).resolve()
        return set(COPY_IGNORE(directory, names)) | {n for n in names if here / n in skip}
    return ignore


def evaluate_case(case: dict, skill: str, repo: Path, args, trace_dir: Path) -> dict:
    run = RUNNERS[args.runner]
    with tempfile.TemporaryDirectory() as tmp:
        workdir = repo if args.in_place else Path(tmp) / "repo"
        if not args.in_place:
            shutil.copytree(repo, workdir, ignore=copy_ignore(args.eval_skip))
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
        should = case.get("should_trigger")
        if case.get("check_paths", should is not False):
            # check against the run dir too: the answer may cite files the run created or the injected skill
            bases = list(dict.fromkeys([workdir, repo, *installed_skill_dirs(skill)]
                                       + ([Path(args.skill_dir).resolve()] if args.skill_dir else [])))
            bad_paths = sorted(p for p in cited_paths(out["answer"], roots)
                               if is_checkable(p, bases) and not path_exists(bases, p))
        else:
            bad_paths = None

    calls, answer = out["calls"], out["answer"]
    skill_idx = [i for i, c in enumerate(calls) if is_skill_call(c, skill)]
    checks, notes = {}, {}

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
    if bad_paths is not None:
        checks["paths_exist"] = not bad_paths
        if bad_paths:
            notes["hallucinated_paths"] = bad_paths
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

    return {"id": case["id"], "prompt": case["prompt"], "checks": checks, "notes": notes, "answer": answer,
            "cost": cost}


TRIGGER_CHECKS = {"trigger_match", "skill_first", "completed", "no_file_writes"}


def check_names(results: list[dict]) -> list[str]:
    return sorted({n for r in results for n in r["checks"]}, key=lambda n: (n not in TRIGGER_CHECKS, n))


# --- Eval folder ----------------------------------------------------------------------------------

def resolve_eval_paths(args) -> tuple[Path, Path]:
    """Return (cases_file, eval_dir). `--cases` may be a file path or a bare skill name.

    eval dir: --eval-dir > $SKILL_EVAL_DIR > the folder holding `cases/` when the cases file is in one > cwd.
    """
    eval_dir = args.eval_dir or os.environ.get(EVAL_DIR_ENV)
    cases = Path(args.cases).expanduser()
    if not cases.is_file() and cases.suffix != ".json" and len(cases.parts) == 1:
        cases = Path(eval_dir or ".").expanduser() / CASES_DIR / f"{args.cases}.cases.json"
    if not cases.is_file():
        sys.exit(f"cases file not found: {cases}")
    cases = cases.resolve()
    if not eval_dir:
        eval_dir = cases.parent.parent if cases.parent.name == CASES_DIR else Path.cwd()
    return cases, Path(eval_dir).expanduser().resolve()


# --- HTML report ----------------------------------------------------------------------------------

REPORT_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1b;--muted:#6b6b66;--line:#e3e2dd;--pass:#1f7a4d;--pass-bg:#e3f3ea;
--fail:#b3261e;--fail-bg:#fbe7e5;--code:#f1f0ec}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--fg:#ecebe6;--muted:#9c9b95;--line:#33322f;
--pass:#6fd19c;--pass-bg:#183526;--fail:#f19a92;--fail-bg:#3d1c19;--code:#2a2927}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:32px 0 12px}.meta{color:var(--muted);font-size:13px;word-break:break-all}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:12px}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:8px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{font-size:12px;color:var(--muted);font-weight:600}tr:last-child td{border-bottom:0}
.pass,.fail{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:600}
.pass{color:var(--pass);background:var(--pass-bg)}.fail{color:var(--fail);background:var(--fail-bg)}
.na{color:var(--muted)}a{color:inherit}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:10px}
summary{cursor:pointer;padding:12px 16px;font-weight:600;display:flex;gap:10px;align-items:center}
.body{padding:0 16px 16px}.label{color:var(--muted);font-size:12px;margin:12px 0 4px}
pre{background:var(--code);border-radius:8px;padding:12px;margin:0;white-space:pre-wrap;word-break:break-word;
font:12.5px/1.5 ui-monospace,Consolas,monospace;max-height:480px;overflow:auto}
ul{margin:0;padding-left:20px}li{margin:4px 0}
"""


def badge(ok) -> str:
    if ok is None:
        return '<span class="na">-</span>'
    return '<span class="pass">PASS</span>' if ok else '<span class="fail">FAIL</span>'


def write_report(summary: dict, out_dir: Path) -> Path:
    """Self-contained report.html next to summary.json and the traces."""
    e = lambda s: html.escape(str(s))
    results = summary["results"]
    names = check_names(results)
    pct = lambda v: "n/a" if v is None else f"{v:.0%}"
    cost = ", ".join(f"${v:.2f}" if k == "usd" else f"{v} {k.replace('_', ' ')}"
                     for k, v in summary.get("cost", {}).items()) or "n/a"
    passed = sum(all(r["checks"].values()) for r in results)

    rows = "".join(
        f'<tr><td><a href="#case-{e(r["id"])}">{e(r["id"])}</a></td>'
        + "".join(f"<td>{badge(r['checks'].get(n))}</td>" for n in names) + "</tr>"
        for r in results)

    cases = []
    for r in results:
        notes = []
        for key, val in r["notes"].items():
            if key == "rubric" and isinstance(val, list):
                notes += [f"{badge(c['pass'])} {e(c['criterion'])}<br><span class='meta'>{e(c['evidence'])}</span>"
                          for c in val]
            else:
                notes.append(f"<b>{e(key)}</b>: {e(json.dumps(val) if not isinstance(val, str) else val)}")
        trace = out_dir / f"{r['id']}.jsonl"
        cases.append(
            f'<details id="case-{e(r["id"])}"{"" if all(r["checks"].values()) else " open"}>'
            f'<summary>{badge(all(r["checks"].values()))} {e(r["id"])}</summary><div class="body">'
            + (f'<div class="label">Prompt</div><pre>{e(r["prompt"])}</pre>' if r.get("prompt") else "")
            + (f'<div class="label">Notes</div><ul>{"".join(f"<li>{n}</li>" for n in notes)}</ul>' if notes else "")
            + f'<div class="label">Answer</div><pre>{e(r["answer"] or "(no answer)")}</pre>'
            + (f'<div class="label">Trace</div><a href="{e(trace.name)}">{e(trace.name)}</a>' if trace.exists() else "")
            + "</div></details>")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(summary['skill'])} eval report</title><style>{REPORT_CSS}</style></head><body><main>
<h1>{e(summary['skill'])}</h1>
<div class="meta">runner {e(summary['runner'])} · grader {e(summary.get('grader', '-'))} · {e(summary['timestamp'])}
· repo {e(summary['repo'])}</div>
<div class="tiles">
<div class="tile"><b>{passed}/{len(results)}</b><span>cases fully passing</span></div>
<div class="tile"><b>{pct(summary.get('trigger_score'))}</b><span>trigger / process</span></div>
<div class="tile"><b>{pct(summary.get('accuracy_score'))}</b><span>accuracy</span></div>
<div class="tile"><b>{e(cost)}</b><span>cost</span></div></div>
<h2>Checks</h2><div class="scroll"><table><thead><tr><th>case</th>
{"".join(f"<th>{e(n)}</th>" for n in names)}</tr></thead><tbody>{rows}</tbody></table></div>
<h2>Cases</h2>{"".join(cases)}
</main></body></html>"""
    path = out_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", help="cases JSON file, or a skill name to load <eval-dir>/cases/<name>.cases.json")
    ap.add_argument("--eval-dir", help=f"folder holding cases/ and runs/ (default: ${EVAL_DIR_ENV}, the parent of "
                                       "the cases file's cases/ folder, or cwd)")
    ap.add_argument("--report", metavar="RUN_DIR", help="rebuild report.html from a run's summary.json and exit")
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
    ap.add_argument("--isolated", action="store_true",
                    help="claude only: ignore user settings, hooks, plugins, personal skills and MCP servers so "
                         "results don't depend on this machine (personal skills are injected into the copy)")
    ap.add_argument("--out", help="runs folder (default: <eval-dir>/runs)")
    args = ap.parse_args()
    args.grader = args.grader or args.runner

    if args.report:
        run_dir = Path(args.report).expanduser()
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        print(f"report: {write_report(summary, run_dir)}")
        return
    if not args.cases:
        ap.error("--cases is required (unless --report)")

    cases_file, eval_dir = resolve_eval_paths(args)
    spec = json.loads(cases_file.read_text(encoding="utf-8"))
    skill = args.skill or spec["skill"]
    # --repo is relative to cwd; the cases file's "repo" is relative to the eval dir, so it works from anywhere
    repo = Path(args.repo).resolve() if args.repo else (eval_dir / (spec.get("repo") or ".")).resolve()
    runs_root = Path(args.out).resolve() if args.out else eval_dir / RUNS_DIR
    args.eval_skip = {eval_dir / CASES_DIR, runs_root}
    if args.isolated and args.runner == "copilot":
        print("note: --isolated only affects the claude runner; copilot still loads ~/.copilot skills, "
              "plugins and MCP servers")
    if args.isolated and not args.skill_dir and not any((repo / d / skill).is_dir() for d in PROJECT_SKILL_DIRS):
        # isolated runs can't see personal skills, so copy the installed one into the repo copy
        homes = installed_skill_dirs(skill)
        if homes and not args.in_place:
            args.skill_dir = str(homes[0])
            print(f"note: injecting personal skill from {homes[0]}")
        else:
            print(f"WARNING: skill '{skill}' is not in the repo"
                  + (" and --in-place can't inject it" if homes else " or a personal skills folder")
                  + "; pass --skill-dir (plugin skills too) or it will never trigger")
    cases = [c for c in spec["cases"] if not args.only or c["id"] in args.only]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = runs_root / skill / f"{stamp}-{args.runner}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"skill={skill} runner={args.runner} grader={args.grader} repo={repo} cases={len(cases)}\n"
          f"  cases: {cases_file}\n  out:   {out_dir}")
    results = []
    for case in cases:
        print(f"  running {case['id']} ...", flush=True)
        results.append(evaluate_case(case, skill, repo, args, out_dir))

    names = check_names(results)
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
               "cases_file": str(cases_file), "timestamp": stamp,
               "trigger_score": t_pass / t_total if t_total else None,
               "accuracy_score": a_pass / a_total if a_total else None,
               "cost": cost, "results": results}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nsummary: {out_dir / 'summary.json'}\nreport:  {write_report(summary, out_dir)}")


if __name__ == "__main__":
    main()
