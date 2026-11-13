import json
import os
import time
import unittest

from helpers import TempHome, run

import config
import loop
import status


def lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f]


class Heartbeat(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.file = os.path.join(self.home.root, "runs", "o-r", "7", "status.jsonl")
        self.env = {"AF_STATUS_FILE": self.file, "AF_AGENT": "issue-7"}

    def tearDown(self):
        self.home.close()

    def beat(self, kind, stdin='{"tool_name": "Bash"}', **env):
        return run("heartbeat.py", kind, env={**self.env, **env}, stdin=stdin)

    def test_writes_at_most_one_heartbeat_a_minute_and_every_turn_end(self):
        self.assertEqual(self.beat("post").returncode, 0)
        self.assertEqual(self.beat("post").returncode, 0)  # within the quiet minute
        self.assertEqual(self.beat("stop", stdin="{}").returncode, 0)
        rows = lines(self.file)
        self.assertEqual([(r["event"], r["agent"], r["tool"]) for r in rows],
                         [("heartbeat", "issue-7", "Bash"), ("turn-end", "issue-7", None)])
        old = time.time() - 120
        os.utime(self.file, (old, old))
        self.beat("post")
        self.assertEqual(len(lines(self.file)), 3)

    def test_silent_without_a_status_file_or_on_any_error(self):
        r = self.beat("post", AF_STATUS_FILE="")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.file))
        r = self.beat("post", stdin="not json")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        blocker = self.home.write("plain-file", "x")
        r = self.beat("stop", AF_STATUS_FILE=os.path.join(blocker, "status.jsonl"))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))


class Note(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.file = os.path.join(self.home.root, "status.jsonl")

    def tearDown(self):
        self.home.close()

    def test_note_appends_a_stage_line(self):
        runs = '[{"role": "code-reviewer", "profile": "opus", "verdict": "approved", "cost": 0.4, "out": "r.json"}]'
        r = run("status.py", "note", "--stage", "review", "--step", "code-review", "--event", "end", "--round", "2",
                "--done", "리뷰 통과", "--next", "scenario-retrace", "--runs", runs, env={"AF_STATUS_FILE": self.file})
        self.assertEqual(r.returncode, 0, r.stderr)
        row = lines(self.file)[0]
        self.assertEqual((row["stage"], row["step"], row["event"], row["round"], row["done"], row["runs"][0]["verdict"]),
                         ("review", "code-review", "end", 2, "리뷰 통과", "approved"))

    def test_bad_notes_are_refused(self):
        for args, env in ((["--event", "end"], {"AF_STATUS_FILE": self.file}),
                          (["--stage", "x", "--event", "end"], {"AF_STATUS_FILE": ""}),
                          (["--stage", "x", "--event", "end", "--runs", "{}"], {"AF_STATUS_FILE": self.file}),
                          (["--stage", "x", "--event", "end", "--runs", "nope"], {"AF_STATUS_FILE": self.file})):
            self.assertEqual(run("status.py", "note", *args, env=env).returncode, 2, args)
        self.assertNotEqual(run("status.py", "note", "--stage", "x", "--event", "done",
                                env={"AF_STATUS_FILE": self.file}).returncode, 0)
        self.assertFalse(os.path.exists(self.file))

    def test_path_is_for_the_machine_to_expand(self):
        r = run("status.py", "path", "--project", "o/r", "--task", "issue-7")
        self.assertEqual(r.stdout.strip(), "~/.cache/agent-foreman/runs/o-r/issue-7/status.jsonl")
        for args in (["--project", "o/r", "--task", "../x"], ["--project", "bad", "--task", "t"], ["--project", "o/r"]):
            self.assertEqual(run("status.py", "path", *args).returncode, 2, args)


def row(minutes_ago, now, **fields):
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - minutes_ago * 60))
    return json.dumps({"time": t, **fields})


class Summarize(unittest.TestCase):
    NOW = 1_800_000_000

    def test_stage_beat_and_stall(self):
        rows = [row(50, self.NOW, stage="build", step="implement", event="start", round=None),
                row(40, self.NOW, event="heartbeat", agent="issue-7", tool="Bash"),
                "not json",
                row(35, self.NOW, event="heartbeat", agent="issue-7-code-reviewer-1", tool="Read")]
        s = status.summarize(rows, 30, now=self.NOW)
        self.assertEqual((s["stage"], s["step"], s["stage_event"], s["last_beat_agent"], s["minutes_since"], s["stalled"]),
                         ("build", "implement", "start", "issue-7-code-reviewer-1", 35.0, True))
        self.assertFalse(status.summarize(rows, 40, now=self.NOW)["stalled"])

    def test_a_stop_point_is_not_a_stall(self):
        rows = [row(90, self.NOW, stage="ready", event="stop", done="REPORT: ready — #12"),
                row(89, self.NOW, event="turn-end", agent="issue-7")]
        s = status.summarize(rows, 30, now=self.NOW)
        self.assertEqual((s["stopped"], s["stalled"], s["done"]), (True, False, "REPORT: ready — #12"))

    def test_no_lines_is_a_stall(self):
        self.assertTrue(status.summarize([], 30, now=self.NOW)["stalled"])


class Read(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.env = {"HOME": self.home.root}
        self.home.write("state/agent-foreman/projects/o-r/project.json", {"repo": "o/r", "machines": {"local": "/src/r"}})

    def tearDown(self):
        self.home.close()

    def test_reads_every_task_on_a_local_machine(self):
        now = time.time()
        self.home.write(".cache/agent-foreman/runs/o-r/issue-7/status.jsonl",
                        row(1, now, stage="test", event="start") + "\n")
        self.home.write(".cache/agent-foreman/runs/o-r/issue-8/status.jsonl",
                        row(45, now, stage="implement", event="progress") + "\n")
        r = run("status.py", "read", "--project", "o/r", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["stall_minutes"], 30)
        self.assertEqual(set(out["disk"]), {"local"})
        self.assertGreater(out["disk"]["local"]["free_gb"], 0)
        self.assertEqual(out["disk"]["local"]["low"], out["disk"]["local"]["free_gb"] < 20)
        self.assertEqual({t: (v["machine"], v["stage"], v["stalled"]) for t, v in out["tasks"].items()},
                         {"issue-7": ("local", "test", False), "issue-8": ("local", "implement", True)})
        r = run("status.py", "read", "--project", "o/r", "--stall", "60", env=self.env)
        self.assertFalse(json.loads(r.stdout)["tasks"]["issue-8"]["stalled"])

    def test_unknown_machine_is_reported(self):
        out = {"stall_minutes": 30, "tasks": {}, "unreadable": []}
        with self.assertRaises(ValueError):
            status.read_machine("ghost", "o/r", {})
        r = run("status.py", "read", "--project", "o/r", env=self.env)
        got = json.loads(r.stdout)
        self.assertEqual({k: got[k] for k in out}, out)  # no runs yet
        self.assertEqual(run("status.py", "read", env=self.env).returncode, 2)


class Settings(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_disk_floor(self):
        cfg = config.load()
        self.assertEqual(cfg["ops"]["disk_min_free_gb"], 20)
        for bad in (-1, "20", True):
            self.assertTrue(any("disk_min_free_gb" in p for p in config.validate(config.merge(cfg, {"ops": {"disk_min_free_gb": bad}}))), bad)
        home = os.path.join(self.home.root, "h")
        os.makedirs(home)
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": "/src/r"}, "ops": {"disk_min_free_gb": 10 ** 9}})
        r = run("status.py", "read", "--project", "o/r", env={"HOME": home})
        self.assertTrue(json.loads(r.stdout)["disk"]["local"]["low"])

    def test_report_and_stall_minutes(self):
        cfg = config.load()
        self.assertEqual((cfg["ops"]["report_minutes"], cfg["ops"]["stall_minutes"]), (15, 30))
        self.assertEqual([p for p in config.validate(cfg) if "minutes" in p], [])
        for over, words in (({"report_minutes": 0}, "report_minutes must be"),
                            ({"stall_minutes": "30"}, "stall_minutes must be"),
                            ({"stall_minutes": 15}, "must be more than report_minutes")):
            bad = config.merge(cfg, {"ops": over})
            self.assertTrue(any(words in p for p in config.validate(bad)), over)

    def test_the_brief_says_how_often(self):
        cfg = config.merge(config.load(), {"ops": {"report_minutes": 10, "stall_minutes": 25}})
        text = loop.render(cfg, "issue-7", "low", False, loop.resolve_all(cfg["loop"], [], {}), {}, lambda src, v: v)
        self.assertIn("at least every 10 minutes; 25 minutes without a line counts as a stall", text)


class Log(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_add_and_tail(self):
        for event, task in (("brief", "issue-7"), ("launch", "issue-7"), ("brief", "issue-8")):
            r = run("log.py", "add", "--project", "o/r", "--event", event, "--task", task, "--text", "x",
                    "--data", '{"profile": "opus"}')
            self.assertEqual(r.returncode, 0, r.stderr)
        r = run("log.py", "tail", "--project", "o/r", "--event", "brief")
        self.assertEqual([json.loads(x)["task"] for x in r.stdout.splitlines()], ["issue-7", "issue-8"])
        r = run("log.py", "tail", "--project", "o/r", "--task", "issue-7", "-n", "1")
        self.assertEqual([json.loads(x)["event"] for x in r.stdout.splitlines()], ["launch"])
        self.assertTrue(os.path.isfile(config.log_path("o/r")))

    def test_bad_arguments(self):
        for args in (["add", "--project", "bad", "--event", "x"], ["add", "--project", "o/r"],
                     ["add", "--project", "o/r", "--event", "x", "--data", "{oops"]):
            self.assertEqual(run("log.py", *args).returncode, 2, args)
        self.assertEqual(run("log.py", "tail", "--project", "o/r").stdout, "")


if __name__ == "__main__":
    unittest.main()
