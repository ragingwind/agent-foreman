import json
import os
import shutil
import stat
import subprocess
import unittest

from helpers import TempHome, run, task_loop

import config
import gate

HEAD = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"


def pr(**over):
    data = {"number": 7, "state": "OPEN", "isDraft": False, "baseRefName": "main", "headRefOid": HEAD,
            "additions": 30, "deletions": 5, "behind_by": 0,
            "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}],
            "files": [{"filename": "src/x.py", "status": "modified", "patch": "@@\n-a = 1\n+a = 2"}]}
    data.update(over)
    return data


PLAN = ("# Plan: x\n\n## Work breakdown\n\n| id | goal | done when | files | test | status | commit |\n"
        "|---|---|---|---|---|---|---|\n| W1 | a | b | c | test-first | done | abc1234 |\n\n## Decisions\n- none\n")
HANDOFF = "# Handoff: x\n\n## Purpose\na\n\n## Decisions\nb\n\n## Tests\nc\n\n## Not touched\nd\n\n## Follow-ups\ne\n"
SCENARIO = ("# Scenario: x\n\n### 1 · run it\nWhy.\n\n**Expect** — `ok`\n\n**Do**\n\n```bash\nrun\n```\n\n"
            "**Agent**\n\n```\nok\n```\n\n## Closing\nVerdict: pass\nNothing left up.\n")


def task_folder(home, answers=(), plan=PLAN, handoff=HANDOFF, scenario=SCENARIO):
    """A task folder with the records and one answer per (agent, role, profile, verdict, head, ended[, ok])."""
    root = os.path.join(home.root, "task")
    for name, text in (("plan.md", plan), ("handoff.md", handoff), ("scenario.md", scenario)):
        if text is not None:
            home.write(f"task/{name}", text)
    for agent, role, profile, verdict, head, ended, *ok in answers:
        home.write(f"task/reviews/{agent}-{ended}.json", {"result": f"must-fix: none\nVerdict: {verdict}"})
        home.write(f"task/reviews/{agent}-{ended}.meta.json", {"role": role, "agent": agent, "profile": profile,
                                                              "head": head, "ended": ended, "ok": ok[0] if ok else True})
    return root


def status_lines(home, *steps):
    """status.jsonl with a heartbeat and an `end` line for each step."""
    rows = [{"event": "heartbeat", "agent": "7"}] + [{"stage": s, "step": s, "event": "end"} for s in steps]
    home.write("task/status.jsonl", "".join(json.dumps(r) + "\n" for r in rows))


def check(name, data, **spec):
    ctx = {"cwd": spec.pop("cwd", None), "task_dir": spec.pop("task_dir", None)}
    return gate.CHECKS[name](data, {"check": name, **spec}, ctx)


class Checks(unittest.TestCase):
    def test_open_ci_fresh_ready(self):
        self.assertTrue(check("pr-open", pr())[0])
        self.assertFalse(check("pr-open", pr(state="MERGED"))[0])
        self.assertTrue(check("ci", pr())[0])
        pending = [{"name": "e2e", "status": "IN_PROGRESS", "conclusion": None}]
        self.assertFalse(check("ci", pr(statusCheckRollup=pending))[0])
        self.assertFalse(check("ci", pr(statusCheckRollup=[{"context": "lint", "state": "FAILURE"}]))[0])
        self.assertFalse(check("base-fresh", pr(behind_by=2))[0])
        self.assertFalse(check("ready", pr(isDraft=True))[0])

    def test_last_verdict_line(self):
        self.assertEqual(gate.last_verdict("x\nVerdict: approved"), "approved")
        self.assertEqual(gate.last_verdict("**Verdict: Changes**\n"), "changes")
        self.assertEqual(gate.last_verdict("`Verdict: pass.`"), "pass")
        self.assertEqual(gate.last_verdict("Verdict: approved\nmore\nVerdict: changes"), "changes")
        self.assertEqual(gate.last_verdict("The verdict: approved\nVerdict: approved because x"), "")
        self.assertEqual(gate.last_verdict(None), "")

    def test_tests_weakened(self):
        files = [{"filename": "tests/test_old.py", "status": "removed", "patch": ""},
                 {"filename": ".github/workflows/ci.yml", "status": "modified", "patch": "-  run: make e2e\n+  run: true"},
                 {"filename": "tests/test_x.py", "status": "modified", "patch": "+@pytest.mark.skip(reason='later')"},
                 {"filename": "pyproject.toml", "status": "modified", "patch": "-fail_under = 90\n+fail_under = 60"}]
        ok, evidence = check("tests-weakened", pr(files=files))
        self.assertFalse(ok)
        for words in ("removed test file tests/test_old.py", "edited CI file", "skip or focus marker", "coverage threshold"):
            self.assertIn(words, evidence)
        ok, evidence = check("tests-weakened", pr(files=files), allow=["removed-test", "ci-edit", "skip-marker", "coverage"])
        self.assertTrue(ok)
        self.assertTrue(check("tests-weakened", pr())[0])

    def test_size_ready_and_skips(self):
        big = pr(additions=500, deletions=20)
        self.assertFalse(check("size", big, max_lines=400)[0])
        report = gate.evaluate(big, {"repo": "o/r", "pr": 7, "checks": [{"check": "size", "max_lines": 400, "severity": "warn"},
                                                                         {"check": "ci"}]})
        self.assertTrue(report["pass"])
        draft = {"repo": "o/r", "pr": 7, "checks": [{"check": "ready"}, {"check": "ci", "at": "merge"}]}
        self.assertEqual(gate.evaluate(pr(isDraft=True), draft)["blocked"], ["ready"])
        self.assertEqual(gate.evaluate(pr(isDraft=True), draft, before_ready=True)["checks"], [])
        verdicts = {"repo": "o/r", "pr": 7, "checks": [{"check": "verdict", "role": "redteam"},
                                                       {"check": "verdict", "role": "qa"}]}
        report = gate.evaluate(pr(), verdicts, skip={"verdict:qa"})
        self.assertEqual([c["check"] for c in report["checks"]], ["verdict:redteam"])  # only the named role is left out

    def test_validate(self):
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": 1, "checks": [{"check": "ci"}]}), [])
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": None, "checks": [{"check": "ci"}]}), [])
        p = gate.validate_gate({"repo": "o/r", "pr": "1", "checks": [{"check": "magic"}, {"check": "verdict"},
                                                                     {"check": "command"}, {"check": "loop-file"},
                                                                     {"check": "ci", "severity": "x"}]})
        for words in ("pr must be a number", "'magic'", "needs a role", "needs run", "needs sha256", "severity must be"):
            self.assertTrue(any(words in x for x in p), words)
        self.assertEqual(gate.validate_gate({"repo": "bad"}), ["gate: repo must look like owner/name"])
        for old in ("sections", "scenario"):  # the pull-request comment checks are gone
            self.assertIn(f"'{old}'", gate.validate_gate({"repo": "o/r", "checks": [{"check": old}]})[0])


class RoleChecks(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_role_verdict_from_the_task_folder(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": ["opus"]}
        good = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        self.assertTrue(check("verdict", pr(), task_dir=good, **spec)[0])
        self.assertFalse(check("verdict", pr(), **spec)[0])  # needs --task-dir

    def test_role_verdict_refuses_the_lead_profile(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": ["opus"]}
        lead = task_folder(self.home, [("pair-1", "pair", "opus", "approved", HEAD, "2026-11-14T01:00:00Z")])
        ok, evidence = check("verdict", pr(), task_dir=lead, **spec)
        self.assertFalse(ok)
        self.assertIn("(the lead's profile)", evidence)

    def test_role_verdict_old_head_and_latest_run(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": []}
        root = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", "0" * 40, "2026-11-14T01:00:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])
        task_folder(self.home, [("pair-1", "pair", "sonnet", "changes", HEAD, "2026-11-14T02:00:00Z"),
                                ("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:30:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])  # the latest run says changes
        task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T03:00:00Z")])
        self.assertTrue(check("verdict", pr(), task_dir=root, **spec)[0])
        shutil.rmtree(os.path.join(root, "reviews"))
        qa = task_folder(self.home, [("qa-1", "qa", "sonnet", "pass", HEAD, "2026-11-14T03:00:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=qa, **spec)[0])  # a qa answer is not the pair's
        self.assertTrue(check("verdict", pr(), task_dir=qa, role="qa", accept=["pass"])[0])

    def test_failed_run_and_last_line(self):
        spec = {"role": "pair", "accept": ["approved"]}
        root = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z", False)])
        ok, evidence = check("verdict", pr(), task_dir=root, **spec)
        self.assertFalse(ok)
        self.assertIn("(the run failed)", evidence)
        shutil.rmtree(os.path.join(root, "reviews"))
        task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        with open(os.path.join(root, "reviews", "pair-1-2026-11-14T01:00:00Z.json"), "w") as f:
            json.dump({"result": "Verdict: approved\nOn second look:\nVerdict: changes"}, f)
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])  # the last Verdict line counts

    def test_docs(self):
        root = task_folder(self.home)
        self.assertTrue(check("docs", pr(), task_dir=root)[0])
        self.assertEqual(check("docs", pr())[1], "needs --task-dir")
        todo = PLAN.replace("| done |", "| todo |")
        root = task_folder(self.home, plan=todo)
        self.assertIn("work items not done: W1", check("docs", pr(), task_dir=root)[1])
        moved = PLAN.replace("| test | status |", "| status | test |").replace("| test-first | done |", "| done | test-first |")
        root = task_folder(self.home, plan=moved)
        self.assertTrue(check("docs", pr(), task_dir=root)[0])  # the status column is found by its name
        short = PLAN.replace("| W1 | a | b | c | test-first | done | abc1234 |", "| W1 | a | b | c | todo |")
        root = task_folder(self.home, plan=short)
        self.assertIn("rows that do not fit the header: W1 (5 cells, not 7)", check("docs", pr(), task_dir=root)[1])
        empty = PLAN.split("| W1")[0]
        root = task_folder(self.home, plan=empty)
        self.assertIn("work breakdown is empty", check("docs", pr(), task_dir=root)[1])
        root = task_folder(self.home, plan=PLAN, handoff="# Handoff\n\n## Purpose\nx\n")
        self.assertIn("handoff.md lacks Decisions", check("docs", pr(), task_dir=root)[1])
        failing = SCENARIO.replace("Verdict: pass", "Verdict: fail")
        root = task_folder(self.home, handoff=HANDOFF, scenario=failing)
        self.assertIn("closing verdict is not pass", check("docs", pr(), task_dir=root)[1])
        self.assertTrue(check("docs", pr(), task_dir=root, trivial=True)[0])  # no scenario for a trivial task
        for agent_block in ("**Agent**\n\n```\n```", "**Agent**\n\n```\n<what the last full run printed>\n```",
                            "**Agent**\n\nok"):
            root = task_folder(self.home, scenario=SCENARIO.replace("**Agent**\n\n```\nok\n```", agent_block))
            self.assertIn("1 Agent block(s) with no output", check("docs", pr(), task_dir=root)[1], agent_block)
        for name in ("plan.md", "handoff.md", "scenario.md"):
            root = task_folder(self.home)
            os.remove(os.path.join(root, name))
            self.assertIn(f"no {name}", check("docs", pr(), task_dir=root)[1])

    def test_steps(self):
        root = task_folder(self.home)
        self.assertEqual(check("steps", pr(), ids=["plan"])[1], "needs --task-dir")
        self.assertIn("no end line for: plan, build", check("steps", pr(), task_dir=root, ids=["plan", "build"])[1])
        status_lines(self.home)  # heartbeats only
        self.assertIn("no end line for: plan, build", check("steps", pr(), task_dir=root, ids=["plan", "build"])[1])
        status_lines(self.home, "plan", "build")
        self.assertTrue(check("steps", pr(), task_dir=root, ids=["plan", "build"])[0])

    def test_loop_file(self):
        root = task_folder(self.home)
        self.assertEqual(check("loop-file", pr(), sha256="x")[1], "needs --task-dir")
        self.assertFalse(check("loop-file", pr(), task_dir=root, sha256="x")[0])  # no loop.json
        path = self.home.write("task/loop.json", task_loop())
        sha = gate.sha256_file(path)
        self.assertTrue(check("loop-file", pr(), task_dir=root, sha256=sha)[0])
        with open(path, "a") as f:
            f.write(" ")
        self.assertIn("changed after the brief", check("loop-file", pr(), task_dir=root, sha256=sha)[1])


class Template(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_follows_the_loop(self):
        high = gate.template(task_loop(difficulty="high"), "f" * 64, 7)
        verdicts = [(c["role"], c["accept"], c["not_profiles"], c.get("at"))
                    for c in high["checks"] if c["check"] == "verdict"]
        self.assertEqual(verdicts, [("pair", ["approved"], ["opus"], None),
                                    ("redteam", ["approved"], ["opus"], "merge"),
                                    ("qa", ["pass"], ["opus"], "merge")])
        self.assertEqual(gate.validate_gate(high), [])
        self.assertEqual([c["sha256"] for c in high["checks"] if c["check"] == "loop-file"], ["f" * 64])
        self.assertEqual([c["ids"] for c in high["checks"] if c["check"] == "steps"],
                         [["plan", "build", "verify", "review", "simplify", "fix", "recheck"]])
        fallback = gate.template(task_loop(difficulty="high", lead="sonnet"))
        self.assertEqual({tuple(c["not_profiles"]) for c in fallback["checks"] if c["check"] == "verdict"}, {("sonnet",)})
        low = gate.template(task_loop(difficulty="low", trivial=True))
        self.assertEqual([c["role"] for c in low["checks"] if c["check"] == "verdict"], ["redteam", "qa"])
        self.assertEqual([c["ids"] for c in low["checks"] if c["check"] == "steps"], [["plan", "build", "verify"]])
        self.assertTrue([c for c in low["checks"] if c["check"] == "docs"][0]["trivial"])
        self.assertEqual([c for c in low["checks"] if c["check"] == "size"][0]["severity"], "warn")
        self.assertFalse([c for c in low["checks"] if c["check"] in ("command", "loop-file")])
        cmd = gate.template(task_loop(config.merge(self.cfg, {"tests": {"full": "make test"}}), difficulty="low"))
        self.assertEqual([c["run"] for c in cmd["checks"] if c["check"] == "command"], ["make test"])


def git_repo(home):
    """A bare origin and a clone with one commit on main: (clone, git runner)."""
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    origin, work = os.path.join(home.root, "origin.git"), os.path.join(home.root, "work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, work], check=True, capture_output=True)

    def sh(*a):
        return subprocess.run(g + ["-C", work, *a], check=True, capture_output=True, text=True).stdout.strip()
    with open(os.path.join(work, "a.txt"), "w") as f:
        f.write("a\n")
    sh("add", "-A"); sh("commit", "-q", "-m", "init"); sh("push", "-q", "origin", "HEAD:main")
    return work, sh


class SameChange(unittest.TestCase):
    def test_clean_rebase_keeps_the_verdict(self):
        home = TempHome()
        try:
            work, sh = git_repo(home)
            sh("checkout", "-q", "-b", "feature")
            open(os.path.join(work, "b.txt"), "w").write("b\n")
            sh("add", "-A"); sh("commit", "-q", "-m", "change")
            reviewed = sh("rev-parse", "HEAD")
            sh("checkout", "-q", "main")
            open(os.path.join(work, "c.txt"), "w").write("c\n")
            sh("add", "-A"); sh("commit", "-q", "-m", "other"); sh("push", "-q", "origin", "HEAD:main")
            sh("checkout", "-q", "feature"); sh("fetch", "-q"); sh("rebase", "-q", "origin/main")
            head = sh("rev-parse", "HEAD")
            self.assertNotEqual(reviewed, head)
            self.assertTrue(gate.same_change(work, "main", reviewed, head))
            root = task_folder(home, [("pair-1", "pair", "sonnet", "approved", reviewed, "2026-11-14T01:00:00Z")])
            self.assertFalse(check("verdict", pr(headRefOid=head), task_dir=root, role="pair")[0])
            self.assertTrue(check("verdict", pr(headRefOid=head), task_dir=root, role="pair", cwd=work)[0])
            open(os.path.join(work, "b.txt"), "w").write("b changed\n")
            sh("add", "-A"); sh("commit", "-q", "--amend", "-m", "change")
            self.assertFalse(gate.same_change(work, "main", reviewed, sh("rev-parse", "HEAD")))
        finally:
            home.close()


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
data = json.load(open(os.environ["FAKE_GH_DATA"]))
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    print(json.dumps(data["view"]))
elif args[0] == "api" and "/files" in args[-1]:
    print(json.dumps(data["files"]))
elif args[0] == "api" and "/compare/" in args[-1]:
    print(json.dumps({"behind_by": data["behind_by"]}))
else:
    sys.exit(1)
"""


def fake_gh(home, view):
    """A `gh` on PATH that answers from a file: (env, data file)."""
    bindir = os.path.join(home.root, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "gh")
    with open(path, "w") as f:
        f.write(FAKE_GH)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    data = home.write("gh.json", {"view": {k: v for k, v in view.items() if k not in ("files", "behind_by")},
                                  "files": view["files"], "behind_by": view["behind_by"]})
    return {"PATH": bindir + os.pathsep + os.environ["PATH"], "FAKE_GH_DATA": data}, data


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.env, _ = fake_gh(self.home, pr())
        self.task = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        self.loop = self.home.write("task/loop.json", task_loop(difficulty="low"))
        status_lines(self.home, "plan", "build", "verify", "review", "simplify", "fix", "recheck")

    def tearDown(self):
        self.home.close()

    def template(self, *args):
        r = run("gate.py", "template", "--loop", self.loop, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.home.write("gate.json", r.stdout)

    def test_run_passes_and_blocks(self):
        g = self.template("--pr", "7")
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["pass"])  # the verification session's verdicts wait for the merge gate
        r = run("gate.py", "run", g, "--task-dir", self.task, env=self.env)
        self.assertEqual(r.returncode, 6)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["verdict:redteam", "verdict:qa"])
        r = run("gate.py", "run", g, "--task-dir", self.task, "--skip", "verdict", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("verdict:qa", r.stderr)
        r = run("gate.py", "run", g, "--task-dir", self.task, "--skip", "verdict:qa", env=self.env)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["verdict:redteam"])
        task_folder(self.home, [("redteam-1", "redteam", "opus", "approved", HEAD, "2026-11-14T02:00:00Z"),
                                ("qa-1", "qa", "opus", "pass", HEAD, "2026-11-14T02:00:00Z")])
        r = run("gate.py", "run", g, "--task-dir", self.task, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_gate_and_loop_files_must_be_the_briefs(self):
        g = self.template("--pr", "7")
        sha = run("gate.py", "hash", g).stdout.strip()
        self.assertEqual(sha, gate.sha256_file(g))
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", "--sha", sha, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(g) as f:
            weaker = json.load(f)
        weaker["checks"] = [c for c in weaker["checks"] if c["check"] != "verdict"]
        with open(g, "w") as f:
            json.dump(weaker, f)
        r = run("gate.py", "run", g, "--task-dir", self.task, "--sha", sha, env=self.env)
        self.assertEqual(r.returncode, 6)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["gate-file"])
        g = self.template("--pr", "7")
        with open(self.loop, "a") as f:
            f.write("\n")
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["loop-file"])

    def test_pull_request_named_at_run_time(self):
        g = self.template()
        self.assertEqual(run("gate.py", "run", g, "--before-ready", env=self.env).returncode, 2)  # no PR yet
        r = run("gate.py", "run", g, "--pr", "7", "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        named = self.template("--pr", "7")
        r = run("gate.py", "run", named, "--pr", "8", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("for #7, not #8", r.stderr)

    def test_paths_with_a_tilde(self):
        g = self.template("--pr", "7")
        rel = "~/" + os.path.relpath(g, self.home.root)
        task = "~/" + os.path.relpath(self.task, self.home.root)
        r = run("gate.py", "run", rel, "--task-dir", task, "--before-ready", env={**self.env, "HOME": self.home.root})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_template_and_bad_arguments(self):
        self.assertEqual(json.loads(run("gate.py", "template", "--loop", self.loop).stdout)["pr"], None)
        self.assertEqual(run("gate.py", "template").returncode, 2)
        bad_loop = self.home.write("bad-loop.json", {"task": "7"})
        self.assertEqual(run("gate.py", "template", "--loop", bad_loop).returncode, 2)
        self.assertEqual(run("gate.py", "run").returncode, 2)
        bad = self.home.write("bad.json", {"repo": "o/r", "pr": 7, "checks": [{"check": "magic"}]})
        self.assertEqual(run("gate.py", "run", bad, env=self.env).returncode, 2)


if __name__ == "__main__":
    unittest.main()
