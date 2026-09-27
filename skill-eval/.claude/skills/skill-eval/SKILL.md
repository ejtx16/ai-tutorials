---
name: skill-eval
description: |
  Test, validate, and measure the ACCURACY of an agent skill's output (SKILL.md skills for Claude Code
  or GitHub Copilot CLI / VS Code Copilot Chat) against a source of truth (a codebase, docs, or data
  files). Runs the target skill headless on a small prompt set, captures
  traces, and scores it with deterministic checks (trigger, grounded facts, hallucinated file paths,
  expected files) plus an optional reference-grounded rubric grader. Use this skill when the user wants to:
  - Evaluate, test, validate, or benchmark a specific skill ("test my X skill", "is my skill accurate?")
  - Check whether a skill's answers or generated files are correct relative to a codebase or reference data
  - Catch a skill hallucinating files, functions, or facts that are not in the reference
  - Check that a skill triggers on the right prompts and stays quiet on the wrong ones
  - Compare a skill before/after editing its SKILL.md (regression testing)
  Not for improving an agent's runtime output with self-critique loops (that is agentic-eval).
---

# Skill Eval

Measure whether a skill's output is **accurate against a reference** (codebase, docs, data), not just whether it sounds good.

Method (from OpenAI's "eval skills" guide): **prompt → captured run (trace + artifacts) → small set of checks → score you compare over time.**
Deterministic checks first (cheap, repeatable, explainable). Model grading only for what code cannot check, and always grounded in reference files.

## Environments

Works in any agent that can run a terminal command. The script drives a headless agent CLI (`--runner`):

| You are running in | Use | Needs |
|---|---|---|
| Claude Code | `--runner claude` (default) | `claude` CLI logged in |
| GitHub Copilot CLI | `--runner copilot` | `copilot` CLI logged in (`npm i -g @github/copilot`, then `copilot login`) |
| VS Code Copilot Chat (agent mode) | `--runner copilot` | same as Copilot CLI; run the command in the integrated terminal tool |

Pick the runner matching the environment the skill will be *used* in: a skill can pass in one agent and fail in another (different models follow instructions differently). To check both, run twice and compare the summaries. `--grader` defaults to the runner; pass `--grader claude` for cheaper structured grading when both CLIs are available.

**Locate this skill's folder** to build the script path: it is the folder containing this SKILL.md, e.g. `.claude/skills/skill-eval/`, `.github/skills/skill-eval/`, `~/.claude/skills/skill-eval/`, or `~/.copilot/skills/skill-eval/`. Requires Python 3.9+ (`python` or `python3`).

## Workflow

### 1. Pin down target + source of truth
Establish, asking the user only if not inferable:
- **Target skill**: name, and where its `SKILL.md` lives. Project: `.claude/skills/`, `.github/skills/`, `.agents/skills/`. Personal: `~/.claude/skills/`, `~/.copilot/skills/`, `~/.agents/skills/`. Or a plugin. Both Claude Code and Copilot read `.claude/skills/` in the project.
- **Reference**: the repo / docs / data the output must agree with. This becomes `--repo`.
- **What "accurate" means** for this skill: correct facts? correct files cited? generated files exist and are valid?

Read the target `SKILL.md` fully so cases test what the skill claims to do.

### 2. Write the cases file — grounded, never invented
Create `evals/<skill>.cases.json` (format below). Start small: **4–6 cases**:
- 1–2 **explicit** (prompt names the skill)
- 1–2 **implicit** (matches the description without naming it)
- 1 **negative control** (similar topic, must NOT trigger)
- accuracy expectations on every positive case

**Ground every expectation in the reference.** Before adding a `must_include` fact, find it in the reference (Grep/Read) and note where. Before adding a `must_not_include`, confirm it is actually wrong. An expectation you did not verify is a bug in the eval, not in the skill.

Prefer checks in this order:
1. `must_include` / `must_not_include` regexes: exact facts (names, values, versions, file paths)
2. `check_paths` (on by default): every backticked file path in the answer must exist in the repo; catches hallucinated files
3. `expect_files`: files the skill should create
4. `rubric` + `reference`: only for judgments regexes can't make ("explains the auth flow in the correct order"). Each item must be checkable against the listed reference files.

### 3. Run
```bash
python <this-skill-dir>/scripts/run_skill_eval.py --cases evals/<skill>.cases.json --repo <reference-repo> --runner <claude|copilot>
```
Useful flags: `--only id1 id2` (rerun specific cases), `--skill-dir <path>` (inject a skill not installed in the repo), `--model` / `--grader-model`, `--max-turns N` (claude only, default 10), `--timeout S` (per run, default 600), `--in-place` (big repos; skips the temp copy, but the skill may modify files; warn the user first).

Each case runs in a **temp copy** of the repo (without `.git`, `node_modules`, etc.), so the reference is never modified. The copilot runner uses `--allow-all-tools` (required for headless mode), which is another reason not to use `--in-place` casually.

Cost: Claude ≈ $0.10–0.50 per case plus ~$0.01 per rubric grade. Copilot ≈ 1–2 premium requests per case plus 1 per rubric grade. Tell the user the estimate before running more than ~10 cases.

Output: table of PASS/FAIL/`-` per check, a **trigger/process score** and a separate **accuracy score**, failure details, and `runs/<skill>/<timestamp>-<runner>/` with one JSONL trace per case + `summary.json`.

### 4. Diagnose failures
Read the notes and, when unclear, the case's trace (`runs/.../<id>.jsonl`). Claude traces: `assistant` events hold tool calls, the `result` event holds the final answer. Copilot traces: `tool.execution_start` events hold tool calls (skill loads show as tool `skill`), `assistant.message` with `phase: "final_answer"` holds the answer.

| Failing check | Usually means | Fix where |
|---|---|---|
| `trigger_match` / `skill_first` | description doesn't match how users ask | target `description` |
| `facts` / `rubric` | skill instructions miss or misstate something | target SKILL.md body / its references |
| `forbidden` | skill states something wrong or outdated | target SKILL.md body |
| `paths_exist` | skill invents files instead of looking them up | tell the skill to verify paths (Glob/Grep) before citing |
| `files_created` | skill didn't finish or wrote elsewhere | target workflow steps |
| `completed` | hit max turns / timeout, errored, or CLI not logged in | check the trace is non-empty; raise `max_turns`/`--timeout`, or simplify the skill |
| passes on one runner, fails on the other | that agent's model ignores or overrides the skill's instructions | make the instruction explicit and imperative ("use exactly these values") |

An **empty trace on every case** means the harness could not run the CLI (not installed, not logged in, wrong PATH); fix that before judging the skill.

**First rule out an eval bug**: re-verify the failing expectation against the reference. If the expectation was wrong, fix the case, not the skill.

### 5. Fix, rerun, guard against overfitting
- Report the scores and root causes to the user. Edit the target skill only if the user asked for fixes.
- After a fix, rerun and compare with the previous `summary.json`.
- Then add 2–3 **held-out** cases worded differently from the ones you fixed against, plus a **near-miss negative**. 100% on only the cases you tuned for proves little.
- Turn every real-world failure the user reports into a new case (regression coverage grows from failures).

## Cases file format

```json
{
  "skill": "api-docs",
  "repo": "../my-service",
  "cases": [
    {
      "id": "explicit-auth",
      "prompt": "Use the api-docs skill to document the login endpoint. Answer in chat only.",
      "should_trigger": true,
      "chat_only": true,
      "must_include": ["POST\\s+/api/login", "15 ?min"],
      "must_not_include": ["/api/v1/login"],
      "reference": ["src/routes/auth.ts", "src/config/*.ts"],
      "rubric": [
        "States the token expiry exactly as configured in src/config",
        "Lists every required request field that the route handler validates"
      ]
    },
    {
      "id": "generates-file",
      "prompt": "Generate API docs for the users routes into docs/users.md",
      "should_trigger": true,
      "expect_files": ["docs/users.md"],
      "max_turns": 20
    },
    {
      "id": "negative-refactor",
      "prompt": "Refactor the login handler to use async/await.",
      "should_trigger": false
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id`, `prompt` | required |
| `should_trigger` | `true`/`false` → trigger checks; omit to skip them |
| `chat_only` | adds `no_file_writes` check |
| `must_include` / `must_not_include` | case-insensitive regexes over the final answer |
| `check_paths` | default on for positive cases; set `false` if the answer legitimately cites non-existent paths |
| `expect_files` | paths (relative to repo) that must exist after the run |
| `reference` | repo-relative files/globs given to the rubric grader (each truncated to 20k chars) |
| `rubric` | criteria the grader checks against `reference` only |
| `max_turns` | per-case override |
