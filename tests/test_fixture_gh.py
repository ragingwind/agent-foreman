"""fixture/bin/gh: the local stand-in for GitHub that fixture/run.py gives
the agents. Checked here first, so a live run fails on the agents, not on it."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from helpers import ROOT, TempHome, run, task_loop

GH = os.path.join(ROOT, "fixture", "bin", "gh")
G = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]


def git(cwd, *args):
    return subprocess.run(G + ["-C", cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


class FakeGh(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        root = self.home.root
        self.origin = os.path.join(root, "origin", "o", "r.git")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        self.clone = os.path.join(root, "clone")
        subprocess.run(["git", "clone", "-q", self.origin, self.clone], check=True, capture_output=True)
        git(self.clone, "config", "user.email", "t@example.invalid")
        git(self.clone, "config", "user.name", "t")
        self.home.write("clone/ok.sh", "exit 0\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-q", "-m", "base")
        git(self.clone, "push", "-q", "origin", "HEAD:main")
        self.base = git(self.clone, "rev-parse", "HEAD")
        git(self.clone, "switch", "-q", "-c", "feature")
        self.home.write("clone/a.txt", "one\ntwo\n")
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-q", "-m", "add a")
        git(self.clone, "push", "-q", "origin", "feature")
        self.head = git(self.clone, "rev-parse", "HEAD")
        self.home.write("tasks/3.md", "# Do a thing\n\n## Goal\nA thing.\n")
        self.state = self.home.write("gh.json", {"repo": "o/r", "origin": self.origin, "ci": "sh ok.sh",
                                                 "tasks_dir": os.path.join(root, "tasks"), "prs": {}, "next": 1})
        self.env = {"FAKE_GH_STATE": self.state, "AF_AGENT": "lead"}

    def tearDown(self):
        self.home.close()

    def gh(self, *args, cwd=None):
        return subprocess.run([sys.executable, GH, *args], capture_output=True, text=True, cwd=cwd or self.clone,
                              env={**os.environ, **self.env})

    def read(self):
        with open(self.state) as f:
            return json.load(f)

    def create(self, *extra):
        body = self.home.write("body.md", "Closes #3\n")
        r = self.gh("pr", "create", "--draft", "--base", "main", "--head", "feature", "--title", "Add a",
                    "--body-file", body, *extra)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_a_pull_request_from_create_to_merge(self):
        self.assertEqual(self.create(), "https://fake.github/o/r/pull/1")
        view = json.loads(self.gh("pr", "view", "1", "--json", "isDraft,headRefOid,baseRefOid,body,additions").stdout)
        self.assertEqual(view, {"isDraft": True, "headRefOid": self.head, "baseRefOid": self.base,
                                "body": "Closes #3\n", "additions": 2})
        self.assertEqual(self.gh("pr", "view", "--json", "number", "-q", ".number").stdout.strip(), "1")  # by branch
        r = self.gh("pr", "checks", "1", "--watch")
        self.assertEqual((r.returncode, r.stdout.split("\t")[:2]), (0, ["ci", "pass"]))
        self.assertEqual(self.gh("pr", "merge", "1", "--squash").returncode, 1)  # still a draft
        self.gh("pr", "ready", "1")
        self.assertEqual(self.gh("pr", "view", "1", "--json", "isDraft", "-q", ".isDraft").stdout.strip(), "false")
        self.gh("pr", "ready", "1", "--undo")
        self.assertEqual(self.gh("pr", "view", "1", "--json", "isDraft", "-q", ".isDraft").stdout.strip(), "true")
        self.gh("pr", "ready", "1")
        r = self.gh("pr", "merge", "1", "--squash", "--delete-branch")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(git(self.origin, "log", "-1", "--format=%s", "main"), "Add a (#1)")
        self.assertEqual(git(self.origin, "branch", "--list", "feature"), "")
        view = json.loads(self.gh("pr", "view", "1", "--json", "state,headRefOid,additions").stdout)
        self.assertEqual(view, {"state": "MERGED", "headRefOid": self.head, "additions": 2})

    def test_checks_fail_with_the_ci_command(self):
        state = self.read()
        state["ci"] = "exit 3"
        with open(self.state, "w") as f:
            json.dump(state, f)
        self.create()
        r = self.gh("pr", "checks", "1")
        self.assertEqual((r.returncode, r.stdout.split("\t")[1]), (1, "fail"))
        rollup = json.loads(self.gh("pr", "view", "1", "--json", "statusCheckRollup").stdout)["statusCheckRollup"]
        self.assertEqual(rollup[0]["conclusion"], "FAILURE")

    def test_edit_labels_api_and_issues(self):
        self.create()
        self.gh("pr", "edit", "1", "--add-label", "state:done", "--body", "new body")
        view = json.loads(self.gh("pr", "view", "1", "--json", "labels,body").stdout)
        self.assertEqual(view, {"labels": [{"name": "state:done"}], "body": "new body"})
        files = json.loads(self.gh("api", "--paginate", "repos/o/r/pulls/1/files?per_page=100").stdout)
        self.assertEqual([(f["filename"], f["status"]) for f in files], [("a.txt", "added")])
        self.assertIn("+one", files[0]["patch"])
        compare = json.loads(self.gh("api", f"repos/o/r/compare/main...{self.head}").stdout)
        self.assertEqual((compare["behind_by"], compare["ahead_by"]), (0, 1))
        self.assertEqual(self.gh("api", "repos/o/r/commits/main", "-q", ".sha").stdout.strip(), self.base)
        self.assertEqual(self.gh("issue", "view", "3", "--json", "title", "-q", ".title").stdout.strip(), "Do a thing")
        self.assertEqual(self.gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner").stdout.strip(),
                         "o/r")

    def test_what_it_does_not_know_is_refused_and_logged(self):
        for args in (["release", "list"], ["api", "-X", "PUT", "repos/o/r/pulls/1/merge"]):
            r = self.gh(*args)
            self.assertEqual(r.returncode, 1)
            self.assertIn("unsupported", r.stderr)
        state = self.read()
        self.assertEqual([c["argv"][0] for c in state["unsupported"]], ["release", "api"])
        self.assertEqual({c["agent"] for c in state["log"]}, {"lead"})

    def test_the_foreman_s_gate_reads_it(self):
        """gate.py's own gh calls (pr view, the files and the compare) get what they need."""
        self.create()
        self.gh("pr", "ready", "1")
        task = os.path.join(self.home.root, "task")
        data = task_loop(difficulty="low", trivial=True, repo="o/r")
        self.home.write("task/loop.json", data)
        gate_file = self.home.write("gate.json", json.loads(run("gate.py", "template", "--loop",
                                                                os.path.join(task, "loop.json"), "--pr", "1").stdout))
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir)
        shutil.copy(GH, os.path.join(bindir, "gh"))
        env = {**self.env, "PATH": bindir + os.pathsep + os.environ["PATH"]}
        r = run("gate.py", "run", gate_file, "--task-dir", task, "--cwd", self.clone, env=env)
        report = json.loads(r.stdout)
        by = {c["check"]: c for c in report["checks"]}
        for check in ("pr-open", "ci", "base-fresh", "tests-weakened", "size", "ready"):
            self.assertTrue(by[check]["ok"], by[check])
        self.assertFalse(by["steps"]["ok"])  # no steps ended: the fake changes nothing about the gate


if __name__ == "__main__":
    unittest.main()
