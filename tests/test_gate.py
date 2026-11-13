import copy
import json
import os
import stat
import subprocess
import unittest

from helpers import TempHome, run

import config
import gate

HEAD = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
BODY = "## Purpose\nfix x\n\n## Decisions\n- kept y (rather than z)\n\n## Tests\n`make test`: 12 passed\n"


def pr(**over):
    data = {"number": 7, "state": "OPEN", "isDraft": False, "baseRefName": "main", "headRefOid": HEAD,
            "body": BODY, "additions": 30, "deletions": 5, "behind_by": 0,
            "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}],
            "comments": [{"body": f"## Code review of #7 at {HEAD[:7]}\nVerdict: approved\nlooks right"},
                         {"body": "## Manual scenario\n1. run it\n```\nok\n```"}],
            "files": [{"filename": "src/x.py", "status": "modified", "patch": "@@\n-a = 1\n+a = 2"}]}
    data.update(over)
    return data


def check(name, data, **spec):
    return gate.CHECKS[name](data, {"check": name, **spec}, {"cwd": spec.pop("cwd", None)})


class Checks(unittest.TestCase):
    def test_open_sections_ci_fresh_ready(self):
        self.assertTrue(check("pr-open", pr())[0])
        self.assertFalse(check("pr-open", pr(state="MERGED"))[0])
        self.assertTrue(check("sections", pr(), names=["Purpose", "Decisions", "Tests"])[0])
        self.assertIn("Decisions", check("sections", pr(body="## Purpose\nx\n## Tests\ny"), names=["Purpose", "Decisions"])[1])
        self.assertTrue(check("ci", pr())[0])
        pending = [{"name": "e2e", "status": "IN_PROGRESS", "conclusion": None}]
        self.assertFalse(check("ci", pr(statusCheckRollup=pending))[0])
        self.assertFalse(check("ci", pr(statusCheckRollup=[{"context": "lint", "state": "FAILURE"}]))[0])
        self.assertFalse(check("base-fresh", pr(behind_by=2))[0])
        self.assertFalse(check("ready", pr(isDraft=True))[0])

    def test_verdict_at_head_count_and_accept(self):
        self.assertTrue(check("verdict", pr(), title="Code review")[0])
        self.assertFalse(check("verdict", pr(), title="Code review", count=2)[0])
        old = pr(comments=[{"body": "## Code review of #7 at 0000000\nVerdict: approved"}])
        self.assertFalse(check("verdict", old, title="Code review")[0])
        changed = pr(comments=[{"body": f"## Code review of #7 at {HEAD}\nVerdict: approved\n...\nVerdict: changes requested"}])
        self.assertFalse(check("verdict", changed, title="Code review")[0])  # the last verdict line counts
        retrace = pr(comments=[{"body": f"## Scenario retrace of #7 at {HEAD[:9]}\nVerdict: pass"}])
        self.assertTrue(check("verdict", retrace, title="Scenario retrace", accept=["pass"])[0])
        other_pr = pr(comments=[{"body": f"## Code review of #8 at {HEAD}\nVerdict: approved"}])
        self.assertFalse(check("verdict", other_pr, title="Code review")[0])

    def test_scenario_and_trivial_reason(self):
        self.assertTrue(check("scenario", pr())[0])
        self.assertFalse(check("scenario", pr(comments=[{"body": "## Manual scenario\nit worked"}]))[0])
        self.assertFalse(check("scenario", pr(comments=[]))[0])
        trivial = pr(body=BODY + "Trivial change: docs only, no scenario.\n")
        self.assertTrue(check("scenario", trivial, trivial=True)[0])
        self.assertFalse(check("scenario", pr(), trivial=True)[0])

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

    def test_size_and_evaluate_with_warn(self):
        big = pr(additions=500, deletions=20)
        self.assertFalse(check("size", big, max_lines=400)[0])
        report = gate.evaluate(big, {"repo": "o/r", "pr": 7, "checks": [{"check": "size", "max_lines": 400, "severity": "warn"},
                                                                         {"check": "ci"}]})
        self.assertTrue(report["pass"])
        report = gate.evaluate(pr(isDraft=True), {"repo": "o/r", "pr": 7, "checks": [{"check": "ready"}]})
        self.assertEqual((report["pass"], report["blocked"]), (False, ["ready"]))
        report = gate.evaluate(pr(isDraft=True), {"repo": "o/r", "pr": 7, "checks": [{"check": "ready"}]}, skip={"ready"})
        self.assertTrue(report["pass"])

    def test_validate(self):
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": 1, "checks": [{"check": "ci"}]}), [])
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": None, "checks": [{"check": "ci"}]}), [])
        p = gate.validate_gate({"repo": "o/r", "pr": "1", "checks": [{"check": "magic"}, {"check": "verdict"},
                                                                     {"check": "command"}, {"check": "ci", "severity": "x"}]})
        for words in ("pr must be a number", "'magic'", "needs a title", "needs run", "severity must be"):
            self.assertTrue(any(words in x for x in p), words)
        self.assertEqual(gate.validate_gate({"repo": "bad"}), ["gate: repo must look like owner/name"])


class Template(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_follows_the_loop(self):
        high = gate.template(self.cfg, "o/r", 7, "high", False)
        verdicts = [(c["title"], c["count"], c["accept"]) for c in high["checks"] if c["check"] == "verdict"]
        self.assertEqual(verdicts, [("Code review", 2, ["approved"]), ("Scenario retrace", 1, ["pass"])])
        self.assertEqual(gate.validate_gate(high), [])
        low = gate.template(self.cfg, "o/r", 7, "low", True)
        self.assertEqual([c["title"] for c in low["checks"] if c["check"] == "verdict"], ["Code review"])
        self.assertTrue([c for c in low["checks"] if c["check"] == "scenario"][0]["trivial"])
        self.assertEqual([c for c in low["checks"] if c["check"] == "size"][0]["severity"], "warn")


class SameChange(unittest.TestCase):
    def test_clean_rebase_keeps_the_verdict(self):
        home = TempHome()
        try:
            g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            origin, work = os.path.join(home.root, "origin.git"), os.path.join(home.root, "work")
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
            subprocess.run(["git", "clone", "-q", origin, work], check=True, capture_output=True)
            sh = lambda *a: subprocess.run(g + ["-C", work, *a], check=True, capture_output=True, text=True).stdout.strip()
            open(os.path.join(work, "a.txt"), "w").write("a\n")
            sh("add", "-A"); sh("commit", "-q", "-m", "init"); sh("push", "-q", "origin", "HEAD:main")
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
            data = pr(headRefOid=head, comments=[{"body": f"## Code review of #7 at {reviewed[:7]}\nVerdict: approved"}])
            self.assertFalse(check("verdict", data, title="Code review")[0])
            self.assertTrue(check("verdict", data, title="Code review", cwd=work)[0])
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


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir)
        path = os.path.join(bindir, "gh")
        open(path, "w").write(FAKE_GH)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        view = {k: v for k, v in pr().items() if k not in ("files", "behind_by")}
        self.data = self.home.write("gh.json", {"view": view, "files": pr()["files"], "behind_by": 0})
        self.env = {"PATH": bindir + os.pathsep + os.environ["PATH"], "FAKE_GH_DATA": self.data}

    def tearDown(self):
        self.home.close()

    def test_run_passes_and_blocks(self):
        g = self.home.write("gate.json", gate.template(config.load(), "o/r", 7, "low", False))
        r = run("gate.py", "run", g, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["pass"])
        g = self.home.write("gate2.json", gate.template(config.load(), "o/r", 7, "high", False))
        r = run("gate.py", "run", g, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 6)
        self.assertIn("verdict Code review", json.loads(r.stdout)["blocked"])

    def test_pull_request_named_at_run_time(self):
        g = self.home.write("gate.json", gate.template(config.load(), "o/r", None, "low", False))
        self.assertEqual(run("gate.py", "run", g, "--before-ready", env=self.env).returncode, 2)  # no PR yet
        r = run("gate.py", "run", g, "--pr", "7", "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        named = self.home.write("named.json", gate.template(config.load(), "o/r", 7, "low", False))
        self.assertEqual(run("gate.py", "run", named, "--pr", "7", "--before-ready", env=self.env).returncode, 0)
        r = run("gate.py", "run", named, "--pr", "8", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("for #7, not #8", r.stderr)

    def test_template_and_bad_arguments(self):
        r = run("gate.py", "template", "--project", "o/r", "--pr", "7", "--difficulty", "mid")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["pr"], 7)
        self.assertEqual(run("gate.py", "template").returncode, 2)
        self.assertEqual(run("gate.py", "run").returncode, 2)
        bad = self.home.write("bad.json", {"repo": "o/r", "pr": 7, "checks": [{"check": "magic"}]})
        self.assertEqual(run("gate.py", "run", bad, env=self.env).returncode, 2)


if __name__ == "__main__":
    unittest.main()
