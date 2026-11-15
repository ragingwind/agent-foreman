#!/usr/bin/env python3
"""A task's pass conditions, as code: the foreman writes the gate file, the
lead runs it before it reports ready, and the foreman runs it again before
it merges.

Usage:
  gate.py template --loop LOOP.json [--pr N]
  gate.py hash GATE.json
  gate.py run GATE.json [--pr N] [--cwd CLONE] [--task-dir DIR] [--skip CHECK,...] [--before-ready] [--sha HEX]

A gate file:
  {"repo": "owner/name", "pr": 12, "checks": [{"check": "<name>", ...}, ...]}

`template` builds the standard gate from the task's `loop.json` (`loop.py
render --json`), so the gate and the loop come from one place. The foreman
writes it with the brief, before the pull request exists, so "pr" may be
null; `run --pr N` names the pull request then. A file that names one and a
different --pr is refused.

The lead can write in its task folder, so the foreman records the gate
file's `hash` with the brief and passes it to every run it makes with --sha:
a changed gate file blocks. The `loop-file` check does the same for
`loop.json`, whose hash the template writes into the gate file.

Checks (each may say "severity": "warn" to report without blocking):
  pr-open         the pull request exists and is open
  loop-file       the task folder's loop.json has the "sha256" in the check
  steps           the task folder's status.jsonl has an `end` line for each
                  step in "ids" (status.py note)
  docs            the task folder's records: every row of plan.md's work
                  breakdown is done, handoff.md has its sections, and
                  scenario.md's closing verdict is pass with every Agent block
                  filled (not for a trivial task)
  ci              every status check finished and passed
  base-fresh      the head contains the base branch's head
  verdict         an agent of "role" whose latest answer in the
                  task folder's reviews/ (launch.py --role) ends with a
                  `Verdict:` in "accept", given at the head SHA (with --cwd,
                  also at an earlier SHA whose change is the same), on a
                  profile not in "not_profiles" (the lead's)
  tests-weakened  no removed test file, added skip marker, edited CI file or
                  changed coverage threshold, except the kinds in "allow"
  size            additions + deletions at most "max_lines"
  ready           the pull request is no longer a draft
  command         "run" exits 0 in the clone (--cwd)

--before-ready skips `ready` and every check marked "at": "merge": the lead
runs the gate before the verification session. --skip names checks to leave
out; a verdict check is named with its role, `verdict:qa`, and only when the
person said so.

`run` prints one JSON object and exits 0 when nothing blocks, 6 when a check
blocks, 2 on bad arguments, 1 when gh or git fails.
"""
import argparse
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

EXIT_GATE_FAILED = 6
TEST_PATHS = ["**/tests/**", "**/test/**", "**/__tests__/**", "**/*_test.*", "**/test_*.*", "**/*.test.*",
              "**/*.spec.*", "**/spec/**"]
CI_PATHS = ["**/.github/workflows/**", "**/.gitlab-ci.yml", "**/Jenkinsfile", "**/.circleci/**",
            "**/azure-pipelines.yml"]
SKIP_MARKERS = re.compile(r"@pytest\.mark\.(skip|xfail)|\b(it|test|describe)\.skip\(|\bx(it|describe)\(|"
                          r"\bt\.Skip(Now|f)?\(|@Ignore\b|@Disabled\b|#\[ignore\]|unittest\.skip|\.only\(")
COVERAGE = re.compile(r"fail_under|fail-under|cov-fail-under|coverageThreshold|min(imum)?_coverage", re.I)
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}
HANDOFF_SECTIONS = ("Purpose", "Decisions", "Tests", "Not touched", "Follow-ups")
VERDICT = re.compile(r"^Verdict:\s*([A-Za-z][\w-]*)\W*$", re.I)


def matches(path, pattern):
    pat = pattern[3:] if pattern.startswith("**/") else pattern
    return fnmatch.fnmatch("/" + path, "*/" + pat) or fnmatch.fnmatch(path, pat)


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def last_verdict(text):
    """The word on the answer's last `Verdict:` line, lower case, or "". Bold,
    backticks or a period around the line do not count against it."""
    found = ""
    for line in str(text or "").splitlines():
        m = VERDICT.match(line.strip().strip("*_`> ").strip())
        if m:
            found = m.group(1).lower()
    return found


def gh_json(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"gate.py: gh {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(out.stdout or "null")


def fetch(repo, pr):
    """Everything the checks read about one pull request."""
    view = gh_json("pr", "view", str(pr), "--repo", repo, "--json",
                   "number,state,isDraft,baseRefName,headRefOid,additions,deletions,statusCheckRollup")
    files = gh_json("api", "--paginate", f"repos/{repo}/pulls/{pr}/files?per_page=100")
    compare = gh_json("api", f"repos/{repo}/compare/{view['baseRefName']}...{view['headRefOid']}")
    view["files"] = files
    view["behind_by"] = compare.get("behind_by")
    return view


def same_sha(a, b):
    a, b = a.lower(), b.lower()
    return len(min(a, b, key=len)) >= 7 and (a.startswith(b) or b.startswith(a))


def same_change(cwd, base, a, b):
    """Whether two commits carry the same change against the base (`git
    patch-id` of each squashed diff), as after a clean rebase."""
    def run(*args, stdin=None):
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, input=stdin)

    ids = []
    for sha in (a, b):
        if run("cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            run("fetch", "--quiet", "origin", sha)
        mb = run("merge-base", f"origin/{base}", sha)
        if mb.returncode != 0:
            return False
        diff = run("diff", mb.stdout.strip(), sha)
        pid = run("patch-id", "--stable", stdin=diff.stdout)
        if diff.returncode != 0 or pid.returncode != 0 or not pid.stdout.strip():
            return False
        ids.append(pid.stdout.split()[0])
    return ids[0] == ids[1]


def section(body, name):
    """The text under `## name` up to the next `## ` heading, or None."""
    m = re.search(rf"^##\s+{re.escape(name)}\b[^\n]*\n(.*?)(?=^##\s|\Z)", body or "", re.M | re.S | re.I)
    return m.group(1) if m else None


def read_task_file(ctx, name):
    try:
        with open(os.path.join(ctx["task_dir"], name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def check_pr_open(pr, spec, ctx):
    return pr["state"] == "OPEN", f"state {pr['state']}"


def check_loop_file(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    path = os.path.join(ctx["task_dir"], "loop.json")
    if not os.path.isfile(path):
        return False, "no loop.json in the task folder"
    found = sha256_file(path)
    return found == spec.get("sha256"), ("loop.json is the one in the brief" if found == spec.get("sha256")
                                         else "loop.json changed after the brief")


def check_steps(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    ended = set()
    for line in (read_task_file(ctx, "status.jsonl") or "").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("event") == "end":
            ended.add(row.get("step"))
    missing = [s for s in spec.get("ids", []) if s not in ended]
    return not missing, (f"no end line for: {', '.join(missing)}" if missing
                         else f"an end line for each of {', '.join(spec.get('ids', []))}")


def table(text, heading):
    """(header, rows) of the first table under `## heading`, each a list of
    cells, or None when there is no such heading."""
    body = section(text, heading)
    if body is None:
        return None
    lines = [l.strip() for l in body.splitlines() if l.strip().startswith("|")]
    cells = [[c.strip() for c in l.strip("|").split("|")] for l in lines]
    return (cells[0], cells[2:]) if len(cells) >= 2 else ([], [])


def plan_problems(plan_text):
    if plan_text is None:
        return ["no plan.md"]
    found = table(plan_text, "Work breakdown")
    if found is None:
        return ["plan.md has no work breakdown"]
    header, rows = found
    names = [h.lower() for h in header]
    if "status" not in names:
        return ["plan.md's work breakdown has no status column"]
    if not rows:
        return ["plan.md's work breakdown is empty"]
    at = names.index("status")
    open_rows, broken = [], []
    for r in rows:
        if len(r) != len(header):
            broken.append(f"{r[0] or '?'} ({len(r)} cells, not {len(header)})")
        elif r[at].lower() != "done":
            open_rows.append(r[0])
    return ([f"work items not done: {', '.join(open_rows)}"] if open_rows else []) + (
        [f"rows that do not fit the header: {', '.join(broken)}"] if broken else [])


def empty_agent_blocks(scenario):
    """How many `**Agent**` blocks hold no output: no fence after the label,
    an empty fence, or a fence that holds only `<...>` placeholders."""
    empty = 0
    for after in scenario.split("**Agent**")[1:]:
        m = re.match(r"\s*```[^\n]*\n(.*?)```", after, re.S)
        if not m or not m.group(1).strip() or re.fullmatch(r"(\s*<[^>\n]*>\s*)+", m.group(1)):
            empty += 1
    return empty


def check_docs(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    problems = plan_problems(read_task_file(ctx, "plan.md"))
    handoff = read_task_file(ctx, "handoff.md")
    if handoff is None:
        problems.append("no handoff.md")
    else:
        missing = [n for n in HANDOFF_SECTIONS if section(handoff, n) is None]
        if missing:
            problems.append(f"handoff.md lacks {', '.join(missing)}")
    if not spec.get("trivial"):
        scenario = read_task_file(ctx, "scenario.md")
        closing = (section(scenario or "", "Closing") or "").strip()
        if scenario is None:
            problems.append("no scenario.md")
        elif not re.fullmatch(r"Verdict:\s*pass", closing.splitlines()[0].strip() if closing else "", re.I):
            problems.append("scenario.md's closing verdict is not pass")
        elif empty_agent_blocks(scenario):
            problems.append(f"scenario.md has {empty_agent_blocks(scenario)} Agent block(s) with no output")
    return not problems, "; ".join(problems) if problems else "plan, handoff and scenario in order"


def check_ci(pr, spec, ctx):
    bad = []
    for c in pr.get("statusCheckRollup") or []:
        done = c.get("status", "COMPLETED") == "COMPLETED"
        result = c.get("conclusion") or c.get("state")
        if not done or result not in PASSED:
            bad.append(f"{c.get('name') or c.get('context')}: {result or c.get('status')}")
    total = len(pr.get("statusCheckRollup") or [])
    return not bad, "; ".join(bad) if bad else f"{total} check(s) passed"


def check_base_fresh(pr, spec, ctx):
    behind = pr.get("behind_by")
    return behind == 0, f"{behind} commit(s) behind {pr['baseRefName']}"


def latest_answers(task_dir, role):
    """(agent, meta, answer text) of each agent of a role: its latest run in the
    task folder's reviews/ (launch.py --print --role writes `<out>.meta.json`)."""
    by_agent = {}
    for meta_file in glob.glob(os.path.join(task_dir, "reviews", "*.meta.json")):
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or meta.get("role") != role:
            continue
        agent = meta.get("agent") or meta_file
        if agent not in by_agent or str(meta.get("ended", "")) > str(by_agent[agent][0].get("ended", "")):
            by_agent[agent] = (meta, meta_file[:-len(".meta.json")] + ".json")
    out = []
    for agent, (meta, answer_file) in sorted(by_agent.items()):
        text = ""
        try:
            with open(answer_file, encoding="utf-8") as f:
                text = str(json.load(f).get("result") or "")
        except (OSError, ValueError, AttributeError):
            pass
        out.append((agent, meta, text))
    return out


def check_verdict(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    accept = [a.lower() for a in spec.get("accept", ["approved"])]
    banned = set(spec.get("not_profiles", []))
    good, seen = 0, []
    for agent, meta, text in latest_answers(ctx["task_dir"], spec["role"]):
        verdict = last_verdict(text)
        head = meta.get("head") or ""
        at_head = bool(head) and (same_sha(head, pr["headRefOid"]) or bool(
            ctx.get("cwd") and same_change(ctx["cwd"], pr["baseRefName"], head, pr["headRefOid"])))
        ok = verdict in accept and at_head and meta.get("profile") not in banned and meta.get("ok") is True
        good += ok
        seen.append(f"{agent} {meta.get('profile')} {head[:7] or '?'} {verdict or 'no verdict'}"
                    + ("" if meta.get("ok") is True else " (the run failed)")
                    + ("" if meta.get("profile") not in banned else " (the lead's profile)"))
    return good > 0, f"{good} accepted {spec['role']} answer(s) at the head; seen: {', '.join(seen) or 'none'}"


def check_tests_weakened(pr, spec, ctx):
    allow = set(spec.get("allow", []))
    found = []
    for f in pr.get("files") or []:
        path, status, patch = f.get("filename", ""), f.get("status", ""), f.get("patch") or ""
        if status == "removed" and any(matches(path, p) for p in TEST_PATHS) and "removed-test" not in allow:
            found.append(f"removed test file {path}")
        if any(matches(path, p) for p in CI_PATHS) and "ci-edit" not in allow:
            found.append(f"edited CI file {path}")
        added = [l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
        changed = added + [l[1:] for l in patch.splitlines() if l.startswith("-") and not l.startswith("---")]
        if "skip-marker" not in allow and any(SKIP_MARKERS.search(l) for l in added):
            found.append(f"added a skip or focus marker in {path}")
        if "coverage" not in allow and any(COVERAGE.search(l) for l in changed):
            found.append(f"changed a coverage threshold in {path}")
    return not found, "; ".join(found) if found else "none found"


def check_size(pr, spec, ctx):
    lines = pr.get("additions", 0) + pr.get("deletions", 0)
    limit = spec.get("max_lines", 400)
    return lines <= limit, f"{lines} changed lines (limit {limit})"


def check_ready(pr, spec, ctx):
    return not pr.get("isDraft"), "draft" if pr.get("isDraft") else "ready"


def check_command(pr, spec, ctx):
    if not ctx.get("cwd"):
        return False, "needs --cwd"
    out = subprocess.run(spec["run"], shell=True, cwd=ctx["cwd"], capture_output=True, text=True)
    tail = (out.stdout + out.stderr).strip().splitlines()[-3:]
    return out.returncode == 0, f"exit {out.returncode}: {' | '.join(tail)}"


CHECKS = {"pr-open": check_pr_open, "loop-file": check_loop_file, "steps": check_steps, "docs": check_docs,
          "ci": check_ci, "base-fresh": check_base_fresh, "verdict": check_verdict,
          "tests-weakened": check_tests_weakened, "size": check_size, "ready": check_ready, "command": check_command}


def check_name(spec):
    """How a check is named in --skip and in the report: `verdict:<role>` for
    a verdict, its check name otherwise."""
    return f"verdict:{spec['role']}" if spec["check"] == "verdict" else spec["check"]


def evaluate(pr, gate, cwd=None, skip=(), task_dir=None, before_ready=False):
    results = []
    for spec in gate["checks"]:
        name = check_name(spec)
        if name in skip or (before_ready and (spec.get("at") == "merge" or name == "ready")):
            continue
        ok, evidence = CHECKS[spec["check"]](pr, spec, {"cwd": cwd, "task_dir": task_dir})
        results.append({"check": name, "ok": ok, "severity": spec.get("severity", "block"), "evidence": evidence})
    blocked = [r for r in results if not r["ok"] and r["severity"] == "block"]
    return {"repo": gate["repo"], "pr": gate["pr"], "head": pr["headRefOid"], "pass": not blocked,
            "blocked": [r["check"] for r in blocked], "checks": results}


def validate_gate(gate):
    problems = []
    if not isinstance(gate, dict) or not re.match(r"^[\w.-]+/[\w.-]+$", str(gate.get("repo", ""))):
        return ["gate: repo must look like owner/name"]
    if gate.get("pr") is not None and (not isinstance(gate["pr"], int) or isinstance(gate["pr"], bool)):
        problems.append("gate: pr must be a number, or null until the pull request exists")
    for i, spec in enumerate(gate.get("checks", [])):
        name = spec.get("check") if isinstance(spec, dict) else None
        if name not in CHECKS:
            problems.append(f"gate: check {i + 1} is {name!r}; known: {', '.join(CHECKS)}")
        elif name == "verdict" and not spec.get("role"):
            problems.append(f"gate: verdict check {i + 1} needs a role")
        elif name == "command" and not spec.get("run"):
            problems.append(f"gate: command check {i + 1} needs run")
        elif name == "loop-file" and not spec.get("sha256"):
            problems.append(f"gate: loop-file check {i + 1} needs sha256")
        if isinstance(spec, dict) and spec.get("severity", "block") not in ("block", "warn"):
            problems.append(f"gate: check {i + 1} severity must be block or warn")
    if not gate.get("checks"):
        problems.append("gate: no checks")
    return problems


def template(task_loop, loop_sha=None, pr=None):
    """The standard gate for a task, from its loop.json: the loop file itself,
    the steps the lead must end before finalize, the task folder's records,
    one verdict check per judging role that runs (the build session's before
    ready, the verification session's at merge), each refusing the lead's
    profile, the full tests, and the standing checks."""
    lead = task_loop.get("lead_profile")
    roles = task_loop.get("roles", {})
    work = task_loop["work"]
    last_stage = work[-1]["stage"]
    checks = [{"check": "pr-open"}]
    if loop_sha:
        checks.append({"check": "loop-file", "sha256": loop_sha})
    checks += [{"check": "steps", "ids": [s["id"] for s in work if s["stage"] != last_stage]},
               {"check": "docs", "trivial": task_loop["trivial"]}, {"check": "ci"}, {"check": "base-fresh"}]
    for which, at in (("work", None), ("check", "merge")):
        for role in dict.fromkeys(s["actor"] for s in task_loop[which] if s["actor"] in roles):
            spec = {"check": "verdict", "role": role, "accept": roles[role].get("accept", ["approved"]),
                    "not_profiles": [lead] if lead else []}
            if at:
                spec["at"] = at
            checks.append(spec)
    if task_loop.get("tests_full"):
        checks.append({"check": "command", "run": task_loop["tests_full"]})
    checks += [{"check": "tests-weakened", "allow": []},
               {"check": "size", "max_lines": task_loop.get("max_lines", 400), "severity": "warn"},
               {"check": "ready"}]
    return {"repo": task_loop["repo"], "pr": pr, "task": task_loop["task"], "difficulty": task_loop["difficulty"],
            "trivial": task_loop["trivial"], "checks": checks}


def main(argv):
    ap = argparse.ArgumentParser(prog="gate.py", description="agent-foreman pass conditions")
    ap.add_argument("command", choices=["template", "hash", "run"])
    ap.add_argument("gate", nargs="?")
    ap.add_argument("--loop", metavar="LOOP.json", help="template: the task's loop.json")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--cwd")
    ap.add_argument("--task-dir", help="the task folder (status.py dir): reviews/ and the records")
    ap.add_argument("--skip", default="")
    ap.add_argument("--before-ready", action="store_true")
    ap.add_argument("--sha", metavar="HEX", help="run: the gate file's hash the foreman recorded with the brief")
    args = ap.parse_args(argv)

    if args.command == "template":
        if not args.loop:
            print("gate.py: template needs --loop <the task's loop.json>", file=sys.stderr)
            return 2
        path = os.path.expanduser(args.loop)
        try:
            with open(path, encoding="utf-8") as f:
                task_loop = json.load(f)
            gate = template(task_loop, sha256_file(path), args.pr)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            print(f"gate.py: {args.loop} is not a task's loop.json (loop.py render --json): {e}", file=sys.stderr)
            return 2
        print(json.dumps(gate, indent=2))
        return 0

    if not args.gate:
        print(f"gate.py: {args.command} needs a gate file", file=sys.stderr)
        return 2
    path = os.path.expanduser(args.gate)
    if args.command == "hash":
        print(sha256_file(path))
        return 0
    with open(path, encoding="utf-8") as f:
        gate = json.load(f)
    problems = validate_gate(gate)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    if gate.get("pr") is not None and args.pr is not None and gate["pr"] != args.pr:
        print(f"gate.py: the gate file is for #{gate['pr']}, not #{args.pr}", file=sys.stderr)
        return 2
    gate["pr"] = gate.get("pr") if gate.get("pr") is not None else args.pr
    if gate["pr"] is None:
        print("gate.py: the gate file names no pull request yet; add --pr N", file=sys.stderr)
        return 2
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    if "verdict" in skip:
        print("gate.py: --skip names a verdict check with its role, such as verdict:qa", file=sys.stderr)
        return 2
    if args.sha and sha256_file(path) != args.sha.strip().lower():
        print(json.dumps({"repo": gate["repo"], "pr": gate["pr"], "pass": False, "blocked": ["gate-file"],
                          "checks": [{"check": "gate-file", "ok": False, "severity": "block",
                                      "evidence": "the gate file changed after the brief"}]}, indent=2))
        return EXIT_GATE_FAILED
    task_dir = os.path.abspath(os.path.expanduser(args.task_dir)) if args.task_dir else None
    cwd = os.path.expanduser(args.cwd) if args.cwd else None
    report = evaluate(fetch(gate["repo"], gate["pr"]), gate, cwd, skip, task_dir, args.before_ready)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["pass"] else EXIT_GATE_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
