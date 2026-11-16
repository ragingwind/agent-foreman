import json
import os
import unittest

from helpers import TempHome, run

import config
import errors

REPO = "o/r"


class ErrorReports(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)

    def errors(self, *args, **env):
        return run("errors.py", *args[:1], "--project", REPO, *args[1:], env={"HOME": self.home.root, **env})

    def report(self, rid):
        with open(os.path.join(config.project_dir(REPO), "error-reports", f"{rid}.json")) as f:
            return json.load(f)

    def test_new_numbers_reports_and_fills_the_form(self):
        r = self.errors("new", "--title", "No verdict", "--severity", "high", "--owner", "outside", "--task", "775",
                        "--step", "redteam-review", "--observed", "ended with no Verdict line")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["id"], "E1")
        e1 = self.report("E1")
        self.assertEqual((e1["severity"], e1["owner"], e1["status"], e1["task"], e1["step"], e1["observed"]),
                         ("high", "outside", "open", "775", "redteam-review", "ended with no Verdict line"))
        self.assertEqual(e1["repro"], {"steps": [], "fixture": None, "reproduced": None})
        self.assertEqual(e1["versions"]["plugin"], "0.1.0")
        self.assertEqual(errors.problems(e1), [])
        self.assertEqual(json.loads(self.errors("new", "--title", "Second").stdout)["id"], "E2")
        self.assertEqual(self.errors("new").returncode, 2)

    def test_the_rules_hold_and_a_broken_change_is_not_written(self):
        self.errors("new", "--title", "Gate blocked")
        refused = [
            ('{"severity": "huge"}', "severity must be one of"),
            ('{"cause": {"text": "disk", "confidence": "confirmed", "evidence": []}}', "a confirmed cause names"),
            ('{"cause": {"text": "disk", "confidence": "guessed", "evidence": [3]}}', "not in evidence"),
            ('{"status": "analyzed"}', "analyzed needs a cause"),
            ('{"status": "fixed"}', "fixed needs an applied fix"),
            ('{"status": "duplicate", "links": ["E1"]}', "duplicate needs a link to another report"),
            ('{"colour": "red"}', "unknown field 'colour'"),
        ]
        for value, words in refused:
            r = self.errors("set", "--id", "E1", "--json", value)
            self.assertEqual(r.returncode, 2, value)
            self.assertIn(words, r.stderr)
        self.assertEqual(self.report("E1")["status"], "open")  # nothing was written
        self.assertEqual(self.errors("set", "--id", "E1", "--json", '{"id": "E9"}').returncode, 2)
        self.assertEqual(self.errors("set", "--id", "E1", "--json", "not json").returncode, 2)
        self.assertEqual(self.errors("set", "--id", "E7", "--json", "{}").returncode, 1)

        ok = [("add", "--to", "evidence", "--json", '{"kind": "gate", "path": "E1/gates.jsonl", "note": "exit 75"}'),
              ("set", "--json", '{"cause": {"text": "the disk was full", "confidence": "confirmed", "evidence": [0]},'
                                ' "status": "analyzed"}'),
              ("add", "--to", "repro", "--json", '"run the gate with 1 GB free"'),
              ("add", "--to", "fix", "--json", '{"text": "free disk first", "owner": "foreman", "status": "applied",'
                                               ' "commit": "abc1234"}'),
              ("set", "--json", '{"status": "fixed"}'),
              ("add", "--to", "links", "--json", '"https://github.com/o/r/issues/9"')]
        for command, *rest in ok:
            r = self.errors(command, "--id", "E1", *rest)
            self.assertEqual(r.returncode, 0, (rest, r.stderr))
        e1 = self.report("E1")
        self.assertEqual((e1["status"], e1["repro"]["steps"], e1["links"]),
                         ("fixed", ["run the gate with 1 GB free"], ["https://github.com/o/r/issues/9"]))
        self.assertEqual(self.errors("check").stdout.strip(), "ok")

    def test_list_and_show(self):
        self.errors("new", "--title", "One", "--owner", "project", "--task", "7")
        self.errors("new", "--title", "Two", "--severity", "low")
        self.errors("add", "--id", "E2", "--to", "evidence", "--json", '{"kind": "file", "path": "/tmp/x", "note": "n"}')
        self.errors("set", "--id", "E2", "--json", '{"cause": {"text": "it", "confidence": "guessed", "evidence": [0]}}')
        out = self.errors("list").stdout
        self.assertIn("| E1 | medium | project | open | 7 | One |", out)
        self.assertIn("| E2 | low | foreman | open |  | Two |", out)
        self.assertNotIn("E2", self.errors("list", "--owner", "project").stdout)
        shown = self.errors("show", "--id", "E2").stdout
        self.assertTrue(shown.startswith("## E2. Two (low, foreman, open)\n"))
        self.assertIn("- **Cause (guessed)**: it Evidence: [0].", shown)
        self.assertIn("  - [0] file: `/tmp/x` — n", shown)
        self.assertEqual(self.errors("show", "--id", "E3").returncode, 1)
        self.assertEqual(self.errors("show", "--id", "x1").returncode, 1)

    def test_collect_copies_the_task_folder_and_its_log_lines(self):
        self.errors("new", "--title", "Stalled", "--task", "7")
        task = os.path.join(self.home.root, ".local", "state", "agent-foreman", "tasks", "o-r", "7")
        self.home.write(".local/state/agent-foreman/tasks/o-r/7/status.jsonl", '{"event": "end"}\n')
        self.home.write(".local/state/agent-foreman/tasks/o-r/7/reviews/qa-1-1.meta.json", {"ok": False})
        log = config.log_path(REPO)
        os.makedirs(os.path.dirname(log), exist_ok=True)
        with open(log, "w") as f:
            f.write('{"event": "brief", "task": "7"}\n{"event": "brief", "task": "8"}\nnot json\n')
        self.errors("add", "--id", "E1", "--to", "evidence", "--json", '{"kind": "pane", "path": "pane.txt"}')
        self.errors("set", "--id", "E1", "--json", '{"cause": {"text": "x", "confidence": "confirmed", "evidence": [0]}}')
        r = self.errors("collect", "--id", "E1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["log_lines"], 1)
        copy = os.path.join(config.project_dir(REPO), "error-reports", "E1")
        self.assertTrue(os.path.exists(os.path.join(copy, "task", "reviews", "qa-1-1.meta.json")))
        with open(os.path.join(copy, "log.jsonl")) as f:
            self.assertEqual(f.read(), '{"event": "brief", "task": "7"}\n')
        e1 = self.report("E1")
        self.assertEqual([e["kind"] for e in e1["evidence"]], ["pane", "status", "log", "meta"])
        self.assertEqual(e1["cause"]["evidence"], [0])  # the earlier evidence keeps its index
        self.errors("collect", "--id", "E1")
        self.assertEqual(len(self.report("E1")["evidence"]), 4)  # collected twice, listed once

        os.rename(task, os.path.join(self.home.root, "gone"))
        r = self.errors("collect", "--id", "E1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no task folder", r.stderr)
        archived = os.path.join(config.project_dir(REPO), "tasks", "7")
        os.makedirs(archived)
        with open(os.path.join(archived, "status.jsonl"), "w") as f:
            f.write("{}\n")
        r = self.errors("collect", "--id", "E1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("the foreman's archive", json.loads(r.stdout)["from"])
        self.errors("new", "--title", "No task")
        self.assertEqual(self.errors("collect", "--id", "E2").returncode, 1)


if __name__ == "__main__":
    unittest.main()
