"""One task walked through the whole loop graph: the scripts the lead and the
foreman run, in the order the loop and status.py's printed next step give,
with a fake claude and gh and a real git repository."""
import json
import os
import re
import shlex
import subprocess
import sys
import unittest

from helpers import SCRIPTS, TempHome

import test_gate as tg

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
if "plugin" in sys.argv[1:]:
    print("[]")
    sys.exit(0)
sys.stdin.read()
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "session_id": "s", "total_cost_usd": 0,
                  "permission_denials": [], "result": "should-fix: x\\nVerdict: " + os.environ["FAKE_VERDICT"]}))
"""
G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
MAX_STEPS = 30


class Walk(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        root = self.home.root
        bindir = os.path.join(root, "bin")
        os.makedirs(bindir)
        for name, text in (("claude", FAKE_CLAUDE), ("gh", tg.FAKE_GH)):
            path = os.path.join(bindir, name)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        self.repo = os.path.join(root, "repo")
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.commit("a")
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": self.repo}})
        self.task = os.path.join(root, ".local", "state", "agent-foreman", "tasks", "o-r", "7")
        os.makedirs(self.task)
        self.status = os.path.join(self.task, "status.jsonl")
        self.env = {**os.environ, "PATH": bindir + os.pathsep + os.environ["PATH"], "HOME": root,
                    "FAKE_GH_DATA": os.path.join(root, "gh.json"), "HERDR_TAB_ID": "", "FAKE_VERDICT": "approved"}
        self.pr()

    def tearDown(self):
        self.home.close()

    def commit(self, text):
        with open(os.path.join(self.repo, "a.txt"), "w") as f:
            f.write(text)
        subprocess.run(G + ["-C", self.repo, "add", "-A"], check=True)
        subprocess.run(G + ["-C", self.repo, "commit", "-q", "-m", text], check=True)
        self.head = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip()
        self.pr()

    def pr(self):
        view = {k: v for k, v in tg.pr(headRefOid=self.head).items() if k not in ("files", "behind_by")}
        self.home.write("gh.json", {"view": view, "files": [], "behind_by": 0})

    def sh(self, script, *args, lead=True, **env):
        """A script run in the lead's clone; `lead` hands it the lead's status file."""
        full = {**self.env, **env}
        if lead:
            full.update(AF_STATUS_FILE=self.status, AF_TASK_DIR=self.task)
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True,
                              text=True, env=full, cwd=self.repo)

    def brief(self, *flags):
        """What the foreman writes into the task folder before the lead starts."""
        r = self.sh("loop.py", "render", "--project", "o/r", "--task", "7", "--difficulty", "mid", "--machine",
                    "local", "--base", "main", "--json", *flags, lead=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.task, "loop.json"), "w") as f:
            f.write(r.stdout)
        r = self.sh("gate.py", "template", "--loop", os.path.join(self.task, "loop.json"), lead=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.task, "gate.json"), "w") as f:
            f.write(r.stdout)
        self.sha = self.sh("gate.py", "hash", os.path.join(self.task, "gate.json"), lead=False).stdout.strip()
        with open(os.path.join(self.task, "loop.json")) as f:
            self.loop = json.load(f)

    def records(self, scenario=True):
        """What the lead's skills write while they work."""
        for name, text in (("plan.md", tg.PLAN), ("handoff.md", tg.HANDOFF)) + ((("scenario.md", tg.SCENARIO),)
                                                                              if scenario else ()):
            with open(os.path.join(self.task, name), "w") as f:
                f.write(text)

    def role(self, step, verdict, lead=True):
        """A role agent's run, the way loop.md and SKILL.md start it: its outcome word."""
        r = self.sh("loop.py", "prompt", "--step", step, *([] if lead else ["--task-dir", self.task]), lead=lead)
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = shlex.split(json.loads(r.stdout)["commands"][0])
        r = subprocess.run([sys.executable] + argv[1:], capture_output=True, text=True, cwd=self.repo,
                           env={**self.env, "FAKE_VERDICT": verdict})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.splitlines()[-1])["verdict"]

    def note(self, step, event, outcome=None, round=1, lead=True):
        s = next(x for w in ("work", "check") for x in self.loop[w] if x["id"] == step)
        args = ["note", "--stage", s["stage"], "--step", step, "--event", event, "--round", str(round)]
        args += ["--outcome", outcome] if outcome else []
        args += [] if lead else ["--file", self.status]
        r = self.sh("status.py", *args, lead=lead)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r"^next: (\S+)", r.stdout, re.M)
        return m.group(1).rstrip(":") if m else None

    def walk(self, start, pair_says, round=1):
        """The lead follows the printed next step from `start` until a stop.
        pair_says: the pair's verdicts, in order. Returns the steps taken."""
        pair_says, taken, step = list(pair_says), [], start
        while step != "stop":
            self.assertLess(len(taken), MAX_STEPS, taken)
            s = next(x for x in self.loop["work"] if x["id"] == step)
            self.note(step, "start", round=round)
            if s["actor"] == "pair":
                verdict = self.role(step, pair_says.pop(0))
                outcome = "done" if step == "review" else verdict
            else:
                outcome = list(s["next"])[-1]
            taken.append(step)
            step = self.note(step, "end", outcome, round=round)
        return taken

    def gate(self, *extra):
        r = self.sh("gate.py", "run", os.path.join(self.task, "gate.json"), "--pr", "7", "--cwd", self.repo,
                    "--task-dir", self.task, "--sha", self.sha, *extra, lead=False)
        self.assertIn(r.returncode, (0, 6), r.stderr)
        return r.returncode, json.loads(r.stdout)["blocked"]

    def summary(self):
        r = self.sh("status.py", "read", "--project", "o/r", lead=False)
        return json.loads(r.stdout)["tasks"]["7"]

    def test_whole_loop(self):
        self.brief("--lead", "sonnet")
        self.records()
        self.assertEqual(self.gate("--before-ready"), (6, ["steps", "verdict:pair"]))  # nothing walked yet

        # Build session, round 1: the pair asks for changes twice, then approves.
        taken = self.walk("plan", ["changes", "changes", "approved"])
        self.assertEqual(taken, ["plan", "build", "verify", "review", "simplify", "fix", "recheck", "fix", "recheck",
                                 "finalize"])
        self.assertTrue(self.summary()["stopped"])  # the finalize end line is the stop line
        with open(os.path.join(self.task, "reviews", "pair-1-3.prompt.md")) as f:  # the second recheck
            self.assertIn("only the fixes and the clean-up since your last review", f.read())
        self.assertEqual(self.gate("--before-ready"), (0, []))
        self.assertEqual(self.gate(), (6, ["verdict:redteam", "verdict:qa"]))

        # Verification session, round 1: the red team finds something; QA passes.
        for step in ("redteam-review", "test"):
            self.note(step, "start", lead=False)
        back = self.note("redteam-review", "end", self.role("redteam-review", "changes", lead=False), lead=False)
        self.assertEqual(back, "build")
        self.assertEqual(self.note("test", "end", self.role("test", "pass", lead=False), lead=False), "stop")
        self.assertEqual(self.gate(), (6, ["verdict:redteam"]))

        # Back to build: a new head makes every earlier verdict stale.
        self.commit("b")
        self.assertEqual(self.gate("--before-ready"), (6, ["verdict:pair"]))
        taken = self.walk(back, ["approved", "approved"], round=2)
        self.assertEqual(taken, ["build", "verify", "review", "simplify", "fix", "recheck", "finalize"])
        self.assertEqual(self.gate("--before-ready"), (0, []))
        self.assertEqual(self.gate(), (6, ["verdict:redteam", "verdict:qa"]))  # QA's pass was for the old head
        self.assertEqual(self.note("redteam-review", "end", self.role("redteam-review", "approved", lead=False),
                                   lead=False), "stop")
        self.assertEqual(self.note("test", "end", self.role("test", "pass", lead=False), lead=False), "stop")
        self.assertEqual(self.gate(), (0, []))

        r = self.sh("clone.py", "archive", "--project", "o/r", "--task", "7", lead=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dest = json.loads(r.stdout)["archived"]
        for rel in ("loop.json", "gate.json", "status.jsonl", "reviews/qa-1-2.meta.json", "reviews/pair-1-5.json"):
            self.assertTrue(os.path.isfile(os.path.join(dest, rel)), rel)
        with open(os.path.join(dest, "status.jsonl")) as f:
            rows = [json.loads(line) for line in f]
        edges = [(r["step"], r["outcome"], r["to"]) for r in rows if r["event"] == "end"]
        self.assertIn(("redteam-review", "changes", "build"), edges)
        self.assertEqual([r["step"] for r in rows if r["event"] == "start" and r["round"] == 2][0], "build")

    def test_trivial_loop(self):
        self.brief("--trivial")
        self.records(scenario=False)
        self.assertNotIn("pair", self.loop["roles"])
        self.assertEqual(self.walk("plan", []), ["plan", "build", "verify", "finalize"])
        self.assertEqual(self.gate("--before-ready"), (0, []))  # no pair, no scenario
        self.assertEqual(self.note("test", "end", self.role("test", "pass", lead=False), lead=False), "stop")
        self.assertEqual(self.gate(), (6, ["verdict:redteam"]))
        with open(os.path.join(self.task, "reviews", "qa-1-1.prompt.md")) as f:
            self.assertIn("Trivial task: yes.", f.read())


if __name__ == "__main__":
    unittest.main()
