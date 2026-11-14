#!/usr/bin/env python3
"""A task's pass conditions, as code: the foreman writes the gate file, the
lead runs it before it reports ready, and the foreman runs it again before
it merges.

Usage:
  gate.py template --project OWNER/REPO [--pr N] --difficulty low|mid|high [--trivial]
  gate.py run GATE.json [--pr N] [--cwd CLONE] [--task-dir DIR] [--skip CHECK,...] [--before-ready]

A gate file:
  {"repo": "owner/name", "pr": 12, "checks": [{"check": "<name>", ...}, ...]}

The foreman writes it with the brief, before the pull request exists, so
"pr" may be null; `run --pr N` names the pull request then. A file that
names one and a different --pr is refused.

Checks (each may say "severity": "warn" to report without blocking):
  pr-open         the pull request exists and is open
  sections        the body has the `## <name>` headings in "names"
  ci              every status check finished and passed
  base-fresh      the head contains the base branch's head
  verdict         with "role": at least "count" agents of that role whose latest
                  answer in the task folder's reviews/ (launch.py --role) ends
                  with a `Verdict:` in "accept", given at the head SHA (with
                  --cwd, also at an earlier SHA whose change is the same), on a
                  profile not in "not_profiles" (the lead's). Without "role",
                  the old form: comments titled `## <title> of #<PR> at <sha>`
  docs            the task folder's records: plan.md's work breakdown all done,
                  handoff.md's sections, and scenario.md's closing verdict pass
                  with no empty Agent block (not for a trivial task)
  scenario        a comment titled "title" holding raw output in a code block;
                  for a trivial change, a skip reason under `## Tests` instead
  tests-weakened  no removed test file, added skip marker, edited CI file or
                  changed coverage threshold, except the kinds in "allow"
  size            additions + deletions at most "max_lines"
  ready           the pull request is no longer a draft
                  (--before-ready skips it and every check marked "at": "merge":
                  the lead runs the gate before the verification session)
  command         "run" exits 0 in the clone (--cwd)

`run` prints one JSON object and exits 0 when nothing blocks, 6 when a check
blocks, 2 on bad arguments, 1 when gh or git fails.
"""
import argparse
import fnmatch
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


def matches(path, pattern):
    pat = pattern[3:] if pattern.startswith("**/") else pattern
    return fnmatch.fnmatch("/" + path, "*/" + pat) or fnmatch.fnmatch(path, pat)


def gh_json(*args):
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"gate.py: gh {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    return json.loads(out.stdout or "null")


def fetch(repo, pr):
    """Everything the checks read about one pull request."""
    view = gh_json("pr", "view", str(pr), "--repo", repo, "--json",
                   "number,state,isDraft,baseRefName,headRefOid,body,additions,deletions,comments,statusCheckRollup")
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


def check_pr_open(pr, spec, ctx):
    return pr["state"] == "OPEN", f"state {pr['state']}"


def check_sections(pr, spec, ctx):
    missing = [n for n in spec.get("names", []) if section(pr["body"], n) is None]
    return not missing, f"missing: {', '.join(missing)}" if missing else "all present"


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


def verdicts(pr, title):
    """(sha, verdict) for each comment under the fixed title."""
    head = re.compile(rf"^##\s+{re.escape(title)} of #{pr['number']} at ([0-9a-fA-F]{{7,40}})")
    out = []
    for c in pr.get("comments") or []:
        body = (c.get("body") or "").strip()
        m = head.match(body)
        if not m:
            continue
        lines = re.findall(r"^Verdict:\s*(.+?)\s*$", body, re.M)
        out.append((m.group(1), lines[-1].lower() if lines else ""))
    return out


def latest_answers(task_dir, role):
    """(agent, meta, answer text) of each agent of a role: its latest run in the
    task folder's reviews/ (launch.py --print --role writes `<out>.meta.json`)."""
    import glob
    by_agent = {}
    for meta_file in glob.glob(os.path.join(task_dir, "reviews", "*.meta.json")):
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if meta.get("role") != role:
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


def check_role_verdict(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    accept = [a.lower() for a in spec.get("accept", ["approved"])]
    count = spec.get("count", 1)
    banned = set(spec.get("not_profiles", []))
    good, seen = 0, []
    for agent, meta, text in latest_answers(ctx["task_dir"], spec["role"]):
        lines = re.findall(r"^Verdict:\s*(.+?)\s*$", text, re.M)
        verdict = lines[-1].lower() if lines else ""
        head = meta.get("head") or ""
        at_head = bool(head) and (same_sha(head, pr["headRefOid"]) or bool(
            ctx.get("cwd") and same_change(ctx["cwd"], pr["baseRefName"], head, pr["headRefOid"])))
        ok = verdict in accept and at_head and meta.get("profile") not in banned and meta.get("ok", True)
        good += ok
        seen.append(f"{agent} {meta.get('profile')} {head[:7] or '?'} {verdict or 'no verdict'}"
                    + ("" if meta.get("profile") not in banned else " (the lead's profile)"))
    return good >= count, f"{good} of {count} {spec['role']} at the head; seen: {', '.join(seen) or 'none'}"


def _section_rows(text, heading):
    body = section(text, heading)
    if body is None:
        return None
    rows = [l for l in body.splitlines() if l.strip().startswith("|")]
    return [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[2:]] if len(rows) >= 2 else []


def check_docs(pr, spec, ctx):
    if not ctx.get("task_dir"):
        return False, "needs --task-dir"
    def read(name):
        try:
            with open(os.path.join(ctx["task_dir"], name), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
    problems = []
    plan_text = read("plan.md")
    rows = _section_rows(plan_text or "", "Work breakdown") if plan_text is not None else None
    if rows is None:
        problems.append("plan.md has no work breakdown")
    else:
        open_rows = [r[0] for r in rows if len(r) >= 6 and r[5].lower() != "done"]
        if not rows:
            problems.append("plan.md's work breakdown is empty")
        if open_rows:
            problems.append(f"work items not done: {', '.join(open_rows)}")
    handoff = read("handoff.md")
    missing = [n for n in ("Purpose", "Decisions", "Tests", "Not touched", "Follow-ups")
               if section(handoff or "", n) is None]
    if handoff is None:
        problems.append("no handoff.md")
    elif missing:
        problems.append(f"handoff.md lacks {', '.join(missing)}")
    if not spec.get("trivial"):
        scenario = read("scenario.md")
        closing = section(scenario or "", "Closing")
        if scenario is None:
            problems.append("no scenario.md")
        elif closing is None or not re.search(r"^Verdict:\s*pass\s*$", closing.strip().splitlines()[0] if closing.strip() else "", re.I):
            problems.append("scenario.md's closing verdict is not pass")
        elif re.search(r"\*\*Agent\*\*\s*```[^\n]*\n\s*```", scenario):
            problems.append("scenario.md has an empty Agent block")
    return not problems, "; ".join(problems) if problems else "plan, handoff and scenario in order"


def check_verdict(pr, spec, ctx):
    if spec.get("role"):
        return check_role_verdict(pr, spec, ctx)
    accept = [a.lower() for a in spec.get("accept", ["approved"])]
    count = spec.get("count", 1)
    found = verdicts(pr, spec["title"])
    good, rebased = 0, 0
    for sha, verdict in found:
        if verdict not in accept:
            continue
        if same_sha(sha, pr["headRefOid"]):
            good += 1
        elif ctx.get("cwd") and same_change(ctx["cwd"], pr["baseRefName"], sha, pr["headRefOid"]):
            good += 1
            rebased += 1
    note = f"{good} of {count} at the head" + (f" ({rebased} after a rebase with the same change)" if rebased else "")
    seen = ", ".join(f"{s[:7]} {v or 'no verdict'}" for s, v in found) or "none"
    return good >= count, f"{note}; seen: {seen}"


def check_scenario(pr, spec, ctx):
    if spec.get("trivial"):
        tests = section(pr["body"], "Tests") or ""
        ok = bool(re.search(r"trivial|no scenario|scenario (is )?skipped|skip(s|ped)? the scenario", tests, re.I))
        return ok, "skip reason under ## Tests" if ok else "trivial, but no skip reason under ## Tests"
    title = spec.get("title", "## Manual scenario")
    for c in pr.get("comments") or []:
        body = (c.get("body") or "").strip()
        if body.startswith(title):
            return "```" in body, "scenario comment with raw output" if "```" in body else "scenario comment has no raw output"
    return False, f"no comment starting with {title!r}"


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


CHECKS = {"pr-open": check_pr_open, "sections": check_sections, "ci": check_ci, "base-fresh": check_base_fresh,
          "verdict": check_verdict, "docs": check_docs, "scenario": check_scenario,
          "tests-weakened": check_tests_weakened, "size": check_size, "ready": check_ready, "command": check_command}


def evaluate(pr, gate, cwd=None, skip=(), task_dir=None, before_ready=False):
    results = []
    for spec in gate["checks"]:
        name = spec["check"]
        if name in skip or (before_ready and spec.get("at") == "merge"):
            continue
        ok, evidence = CHECKS[name](pr, spec, {"cwd": cwd, "task_dir": task_dir})
        label = name + (f" {spec.get('role') or spec.get('title')}" if name == "verdict" else "")
        results.append({"check": label, "ok": ok, "severity": spec.get("severity", "block"), "evidence": evidence})
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
        elif name == "verdict" and not (spec.get("title") or spec.get("role")):
            problems.append(f"gate: verdict check {i + 1} needs a role (or the old title)")
        elif name == "command" and not spec.get("run"):
            problems.append(f"gate: command check {i + 1} needs run")
        if isinstance(spec, dict) and spec.get("severity", "block") not in ("block", "warn"):
            problems.append(f"gate: check {i + 1} severity must be block or warn")
    if not gate.get("checks"):
        problems.append("gate: no checks")
    return problems


def template(cfg, repo, pr, difficulty, trivial):
    """The standard gate for a task: the task folder's records, one verdict
    check per judging role that runs (the build session's before ready, the
    verification session's at merge), each refusing the lead's profile, and
    the standing checks."""
    import loop
    from config import lead_profile
    lead = lead_profile(cfg, difficulty)
    checks = [{"check": "pr-open"}, {"check": "docs", "trivial": trivial}, {"check": "ci"}, {"check": "base-fresh"}]
    for which, at in (("work", "ready"), ("check", "merge")):
        counts = {}
        for st in loop.plan(cfg["loop"], difficulty, trivial, which):
            if st["actor"] in cfg["loop"]["roles"]:
                counts[st["actor"]] = max(counts.get(st["actor"], 1), st["count"])
        for role, count in counts.items():
            spec = {"check": "verdict", "role": role, "count": count,
                    "accept": cfg["loop"]["roles"][role].get("accept", ["approved"]), "not_profiles": [lead] if lead else []}
            if at == "merge":
                spec["at"] = "merge"
            checks.append(spec)
    full = cfg.get("tests", {}).get("full")
    if full:
        checks.append({"check": "command", "run": full})
    checks += [{"check": "tests-weakened", "allow": []},
               {"check": "size", "max_lines": cfg["difficulty"]["lines"], "severity": "warn"},
               {"check": "ready"}]
    return {"repo": repo, "pr": pr, "difficulty": difficulty, "trivial": trivial, "checks": checks}


def main(argv):
    ap = argparse.ArgumentParser(prog="gate.py", description="agent-foreman pass conditions")
    ap.add_argument("command", choices=["template", "run"])
    ap.add_argument("gate", nargs="?")
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--difficulty", choices=["low", "mid", "high"])
    ap.add_argument("--trivial", action="store_true")
    ap.add_argument("--cwd")
    ap.add_argument("--task-dir", help="the task folder (status.py dir): reviews/ and the records")
    ap.add_argument("--skip", default="")
    ap.add_argument("--before-ready", action="store_true")
    args = ap.parse_args(argv)

    if args.command == "template":
        if not (args.project and args.difficulty):
            print("gate.py: template needs --project and --difficulty", file=sys.stderr)
            return 2
        from config import load
        print(json.dumps(template(load(args.project), args.project, args.pr, args.difficulty, args.trivial), indent=2))
        return 0

    if not args.gate:
        print("gate.py: run needs a gate file", file=sys.stderr)
        return 2
    with open(args.gate, encoding="utf-8") as f:
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
    skip = {s.strip() for s in args.skip.split(",") if s.strip()} | ({"ready"} if args.before_ready else set())
    task_dir = os.path.abspath(os.path.expanduser(args.task_dir)) if args.task_dir else None
    report = evaluate(fetch(gate["repo"], gate["pr"]), gate, args.cwd, skip, task_dir, args.before_ready)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["pass"] else EXIT_GATE_FAILED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
