"""retro.py: the facts a retro reads, from archived task folders and the
project's log."""
import json
import unittest

from helpers import TempHome, run, task_loop

import retro

TASKS = "state/agent-foreman/projects/o-r/tasks"
LOG = "state/agent-foreman/projects/o-r/log.jsonl"


def lines(*rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def row(time, step, event, **more):
    return {"time": f"2026-11-15T{time}:00Z", "stage": step, "step": step, "event": event, **more}


class Facts(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.home.write(f"{TASKS}/12/loop.json", task_loop(difficulty="mid", task="12"))
        self.home.write(f"{TASKS}/12/status.jsonl", lines(
            {"event": "heartbeat", "agent": "12"},
            row("01:00", "plan", "start", round=1), row("01:20", "plan", "end", outcome="done", to="build"),
            row("01:20", "build", "start", round=1), row("02:00", "build", "end", outcome="done", to="verify"),
            row("02:00", "verify", "start", round=1), row("02:10", "verify", "end", outcome="fail", to="build"),
            row("02:10", "build", "start", round=1), row("02:20", "build", "end", outcome="done", to="verify"),
            row("02:20", "recheck", "start", round=1), row("02:30", "recheck", "end", outcome="changes", to="fix"),
            row("03:00", "test", "start", round=1), row("03:05", "test", "end", outcome="fail", to="build"),
            row("03:10", "build", "stop", round=2, done="decision: which schema", blocked="the person's choice"))
            + "{a cut line\n")
        self.home.write(f"{TASKS}/12/reviews/pair-1-1.json",
                        {"result": "must-fix: the parser drops a field\n- should-fix: a name\nVerdict: changes"})
        self.home.write(f"{TASKS}/12/reviews/pair-1-1.meta.json", {"role": "pair", "agent": "pair-1", "ok": True,
                                                                  "verdict": "changes"})
        self.home.write(f"{TASKS}/12/reviews/qa-1-1.json",
                        {"result": "mismatch (product): step 2 — the count was 3\nVerdict: fail"})
        self.home.write(f"{TASKS}/12/reviews/qa-1-1.meta.json", {"role": "qa", "agent": "qa-1", "ok": True,
                                                                "verdict": "fail"})
        self.home.write(f"{TASKS}/12/reviews/qa-1-2.meta.json", {"role": "qa", "agent": "qa-1", "ok": False})
        self.home.write(f"{TASKS}/12/gates.jsonl", lines(
            {"before_ready": True, "pass": False, "blocked": ["docs", "pr-body"], "warned": ["size"]},
            {"before_ready": True, "pass": True, "blocked": [], "warned": ["size"]}))
        self.home.write(f"{TASKS}/13/loop.json", task_loop(difficulty="low", task="13"))
        self.home.write(f"{TASKS}/13/status.jsonl", lines(
            {"time": "2026-11-16T01:00:00Z", "stage": "plan", "step": "plan", "event": "start", "round": 1}))
        self.home.write(LOG, lines(
            {"time": "2026-11-14T00:00:00Z", "event": "setup", "task": "", "data": {"open": ["verify: no smoke"]}},
            {"time": "2026-11-15T02:15:00Z", "event": "stall", "task": "12", "text": "no line for 31 minutes"},
            {"time": "2026-11-15T02:16:00Z", "event": "stall", "task": "12", "text": "again"},
            {"time": "2026-11-15T09:00:00Z", "event": "retro", "task": "", "text": "smoke skill swapped",
             "data": {"changes": ["smoke: e2e"], "expect": ["verify fails fewer"]}}))

    def tearDown(self):
        self.home.close()

    def test_one_task(self):
        f = retro.facts("o/r", ["12"])
        t = f["tasks"][0]
        self.assertEqual((t["task"], t["difficulty"], t["round"]), ("12", "mid", 2))
        self.assertEqual(t["minutes"], {"plan": 20.0, "build": 50.0, "verify": 10.0, "recheck": 10.0, "test": 5.0})
        self.assertEqual([(b["from"], b["to"]) for b in t["back"]],
                         [("verify", "build"), ("recheck", "fix"), ("test", "build")])  # verify → build again is not back
        self.assertEqual(t["stops"], [{"step": "build", "done": "decision: which schema",
                                       "blocked": "the person's choice"}])
        self.assertEqual(t["reviews"]["pair"]["findings"], {"must-fix": 1, "should-fix": 1})
        self.assertEqual(t["reviews"]["qa"]["verdicts"], {"fail": 1, "failed run": 1})
        self.assertEqual(t["events"], {"stall": 2})
        self.assertEqual(f["steps"]["build"]["back_to"], 2)
        self.assertEqual(f["steps"]["build"]["back_from"], {"from verify (fail)": 1, "from test (fail)": 1})
        self.assertEqual(f["steps"]["build"]["skills"], ["foreman-kit:commit", "foreman-kit:tdd", "foreman-kit:unit"])
        self.assertEqual(f["roles"]["qa"]["findings"], {"mismatch": 1})
        self.assertEqual(f["roles"]["pair"]["lines"], ["12: must-fix: the parser drops a field", "12: should-fix: a name"])
        self.assertEqual(f["gate"], {"docs": {"blocked": 1, "warned": 0}, "pr-body": {"blocked": 1, "warned": 0},
                                     "size": {"blocked": 0, "warned": 2}})
        self.assertEqual(f["open"], ["verify: no smoke"])
        self.assertEqual(f["previous"]["data"]["expect"], ["verify fails fewer"])
        self.assertEqual(len(f["unreadable"]), 1)  # the line that is not JSON

    def test_every_task_or_since(self):
        self.assertEqual([t["task"] for t in retro.facts("o/r")["tasks"]], ["12", "13"])
        since = retro.since_time("2026-11-16")
        self.assertEqual([t["task"] for t in retro.facts("o/r", since=since)["tasks"]], ["13"])
        f = retro.facts("o/r", since=since)
        self.assertEqual((f["steps"]["plan"]["ran"], f["steps"]["build"]["ran"]), (1, 0))
        self.assertEqual(retro.facts("o/r", ["99"])["unreadable"][0].endswith("(no archived task folder)"), True)

    def test_since_is_when_a_task_finished(self):
        # task 12 started before 03:00 and ended after it: a retro since 03:00 still reads it
        self.assertEqual([t["task"] for t in retro.facts("o/r", since=retro.since_time("2026-11-15T03:00:00Z"))["tasks"]],
                         ["12", "13"])
        self.assertIsNone(retro.since_time("yesterday"))
        self.assertEqual(run("retro.py", "facts", "--project", "o/r", "--since", "yesterday").returncode, 2)

    def test_files_of_the_wrong_shape_are_named_not_fatal(self):
        self.home.write(f"{TASKS}/14/loop.json", [])
        self.home.write(f"{TASKS}/14/status.jsonl", lines(row("01:00", "plan", "start", round="2"),
                                                          row("01:01", "plan", "end", outcome="done", to="build")))
        self.home.write(f"{TASKS}/14/gates.jsonl", lines({"pass": False, "blocked": "ci"},
                                                         {"pass": False, "blocked": [{"x": 1}]},
                                                         {"pass": True, "blocked": [], "warned": []}))
        self.home.write(f"{TASKS}/14/reviews/pair-1-1.meta.json", {"role": "pair", "ok": True})
        self.home.write(f"{TASKS}/14/reviews/pair-1-1.json", {"result": ["not text"]})
        f = retro.facts("o/r", ["14"])
        t = f["tasks"][0]
        self.assertEqual((len(t["gate_runs"]), t["round"]), (1, 0))
        self.assertEqual(len(f["unreadable"]), 4)  # loop.json, one status line, two gate runs
        self.assertEqual(f["gate"], {})

    def test_findings(self):
        text = ("must-fix: real\n- should-fix: a name\n**must-fix**: bold\n1. could: numbered\nmust-fix: none\n"
                "Must-fix: None.\n- mismatch (script): step 3\nVerdict: changes")
        self.assertEqual(retro.findings(text), [("must-fix", "must-fix: real"), ("should-fix", "should-fix: a name"),
                                                ("must-fix", "must-fix: bold"), ("could", "could: numbered"),
                                                ("mismatch", "mismatch (script): step 3")])

    def test_open_items_come_from_the_last_setup_that_named_them(self):
        with open(self.home.root + "/" + LOG, "a") as f:
            f.write(json.dumps({"event": "setup", "task": "", "text": "only a model changed", "data": {}}) + "\n")
        self.assertEqual(retro.facts("o/r")["open"], ["verify: no smoke"])

    def test_a_project_with_nothing_yet(self):
        f = retro.facts("o/empty")
        self.assertEqual((f["tasks"], f["steps"], f["open"], f["previous"]), ([], {}, [], None))

    def test_cli(self):
        r = run("retro.py", "facts", "--project", "o/r", "--task", "12")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["tasks"][0]["task"], "12")
        self.assertEqual(run("retro.py", "facts", "--project", "bad").returncode, 2)
        self.assertEqual(run("retro.py", "facts", "--project", "o/r", "--task", "../x").returncode, 2)
        self.assertEqual(run("retro.py", "facts").returncode, 2)


if __name__ == "__main__":
    unittest.main()
