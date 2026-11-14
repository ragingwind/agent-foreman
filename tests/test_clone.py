import json
import os
import subprocess
import sys
import unittest

from helpers import SCRIPTS, TempHome, run

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def put(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def git(cwd, *args):
    return subprocess.run(G + ["-C", cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


class Clone(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.origin = os.path.join(self.home.root, "origin.git")
        self.checkout = os.path.join(self.home.root, "checkout")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.checkout], check=True, capture_output=True)
        put(os.path.join(self.checkout, "a.txt"), "a\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "init")
        git(self.checkout, "push", "-q", "origin", "HEAD:main")
        # The person's checkout sits on a local branch with a commit no remote has.
        git(self.checkout, "checkout", "-q", "-b", "mine")
        put(os.path.join(self.checkout, "b.txt"), "b\n")
        git(self.checkout, "add", "-A")
        git(self.checkout, "commit", "-q", "-m", "local only")
        self.env = {"HOME": self.home.root}
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": self.checkout}})

    def tearDown(self):
        self.home.close()

    def clone(self, *args, cwd=None):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "clone.py"), *args], capture_output=True,
                           text=True, env={**os.environ, **self.env}, cwd=cwd)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {}), r.stderr

    def make(self, agent="lead", *extra):
        return self.clone("make", "--project", "o/r", "--task", "t1", "--agent", agent, "--ref", "origin/main", *extra)

    def test_make_points_origin_at_github_and_starts_clean(self):
        code, out, err = self.make()
        self.assertEqual(code, 0, err)
        path = out["path"]
        self.assertEqual(out["status"], "made")
        self.assertTrue(path.endswith(os.path.join(".cache", "agent-foreman", "work", "o-r", "t1", "lead")))
        self.assertEqual(git(path, "remote", "get-url", "origin"), self.origin)  # not the checkout
        self.assertEqual(git(path, "rev-parse", "HEAD"), git(self.origin, "rev-parse", "main"))
        self.assertEqual(git(path, "for-each-ref", "refs/heads/"), "")  # no branch of the person's
        self.assertNotIn("origin/mine", git(path, "branch", "-r"))
        self.assertEqual(self.make()[1]["status"], "exists")
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead")
        self.assertEqual((code, out["removed"]), (0, [path]))  # the person's local commit is not the clone's

    def test_role_clone_from_the_lead_clone_reaches_github_too(self):
        lead = self.make()[1]["path"]
        git(lead, "switch", "-q", "-c", "fix-1")
        put(os.path.join(lead, "c.txt"), "c\n")
        git(lead, "add", "-A")
        git(lead, "commit", "-q", "-m", "fix")
        git(lead, "push", "-q", "origin", "fix-1")
        head = git(lead, "rev-parse", "HEAD")
        code, out, err = self.clone("make", "--project", "o/r", "--task", "t1", "--agent", "code-reviewer-1",
                                    "--from", lead, "--ref", head, "--no-push")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(out["path"], "remote", "get-url", "origin"), self.origin)
        self.assertEqual((out["head"], out["push"]), (head, False))
        push = subprocess.run(["git", "-C", out["path"], "push", "origin", "HEAD:refs/heads/sneaky"],
                              capture_output=True, text=True)
        self.assertNotEqual(push.returncode, 0)
        self.assertNotIn("sneaky", git(self.origin, "branch", "--list"))
        self.assertEqual(git(lead, "remote", "get-url", "--push", "origin"), self.origin)  # the lead pushes

    def test_check_knows_only_its_own_clones(self):
        path = self.make()[1]["path"]
        self.assertTrue(self.clone("check", path)[1]["ours"])
        self.assertTrue(self.clone("check", path + "/../lead")[1]["ours"])
        self.assertFalse(self.clone("check", self.checkout)[1]["ours"])
        stray = os.path.join(os.path.dirname(path), "stray")
        os.makedirs(os.path.join(stray, ".git"))
        out = self.clone("check", stray)[1]
        self.assertEqual((out["ours"], out["reason"]), (False, "no agent-foreman marker in .git"))

    def test_remove_refuses_to_lose_work_unless_forced(self):
        path = self.make()[1]["path"]
        put(os.path.join(path, "a.txt"), "changed\n")
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead")
        self.assertEqual(code, 1)
        self.assertIn("changes to tracked files: a.txt", out["refused"][0]["reason"])
        git(path, "commit", "-q", "-am", "unpushed")
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead")
        self.assertIn("commits on no remote", out["refused"][0]["reason"])
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead", cwd=path)
        self.assertIn("working directory is inside it", out["refused"][0]["reason"])
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead", "--force")
        self.assertEqual((code, out["removed"]), (0, [path]))

    def test_a_judging_clone_of_unpushed_work_is_removed(self):
        lead = self.make()[1]["path"]
        git(lead, "switch", "-q", "-c", "fix-1")
        put(os.path.join(lead, "c.txt"), "c\n")
        git(lead, "add", "-A")
        git(lead, "commit", "-q", "-m", "not pushed yet")
        head = git(lead, "rev-parse", "HEAD")
        pair = self.clone("make", "--project", "o/r", "--task", "t1", "--agent", "pair-1", "--from", lead,
                          "--ref", head, "--no-push")[1]["path"]
        put(os.path.join(pair, "c.txt"), "probe\n")
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "pair-1")
        self.assertIn("changes to tracked files: c.txt", out["refused"][0]["reason"])
        git(pair, "checkout", "--", "c.txt")
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "pair-1")
        self.assertEqual((code, out["removed"]), (0, [pair]))  # its commits live in the lead's clone
        code, out, _ = self.clone("remove", "--project", "o/r", "--task", "t1", "--agent", "lead")
        self.assertIn("commits on no remote", out["refused"][0]["reason"])  # the lead's own are kept

    def test_remove_task_takes_clones_and_task_folder(self):
        lead = self.make()[1]["path"]
        self.make("qa-1")
        runs = self.home.write(".local/state/agent-foreman/tasks/o-r/t1/status.jsonl", "{}\n")
        code, out, err = self.clone("remove", "--project", "o/r", "--task", "t1")
        self.assertEqual(code, 0, err)
        self.assertEqual(len(out["removed"]), 3)
        self.assertFalse(os.path.exists(os.path.dirname(os.path.dirname(lead))))  # no empty folders left
        self.assertFalse(os.path.exists(runs))

    def test_remove_task_keeps_the_task_folder_when_a_clone_is_refused(self):
        lead = self.make()[1]["path"]
        put(os.path.join(lead, "a.txt"), "changed\n")
        runs = self.home.write(".local/state/agent-foreman/tasks/o-r/t1/status.jsonl", "{}\n")
        self.assertEqual(self.clone("remove", "--project", "o/r", "--task", "t1")[0], 1)
        self.assertTrue(os.path.exists(runs))

    def test_archive_copies_the_task_folder_to_the_foreman(self):
        self.home.write(".local/state/agent-foreman/tasks/o-r/t1/plan.md", "# Plan\n")
        self.home.write(".local/state/agent-foreman/tasks/o-r/t1/reviews/qa-1.json", "{}\n")
        code, out, err = self.clone("archive", "--project", "o/r", "--task", "t1")
        self.assertEqual(code, 0, err)
        self.assertEqual(out["files"], 2)
        dest = os.path.join(self.home.root, "state", "agent-foreman", "projects", "o-r", "tasks", "t1")
        self.assertEqual(out["archived"], dest)
        self.assertTrue(os.path.isfile(os.path.join(dest, "reviews", "qa-1.json")))
        code, out, _ = self.clone("archive", "--project", "o/r", "--task", "none")
        self.assertEqual(code, 1)
        self.assertIn("no task folder", out["error"])

    def test_fresh_replaces_a_clean_clone_only(self):
        first = self.make()[1]
        self.assertEqual(self.make("lead", "--fresh")[1]["status"], "made")
        put(os.path.join(first["path"], "a.txt"), "changed\n")
        code, out, _ = self.make("lead", "--fresh")
        self.assertEqual(code, 1)
        self.assertIn("cannot replace", out["error"])
        self.assertEqual(self.make("lead", "--fresh", "--force")[1]["status"], "made")

    def test_failures_leave_nothing_behind(self):
        code, out, _ = self.clone("make", "--project", "o/r", "--task", "t1", "--agent", "lead", "--ref", "no-such-ref")
        self.assertEqual(code, 1)
        self.assertIn("git checkout", out["error"])
        self.assertFalse(os.path.exists(os.path.join(self.home.root, ".cache", "agent-foreman", "work", "o-r", "t1", "lead")))
        plain = os.path.join(self.home.root, "plain")
        os.makedirs(plain)
        self.assertIn("not a git checkout", self.clone("make", "--project", "o/r", "--task", "t1", "--agent", "x",
                                                       "--ref", "main", "--from", plain)[1]["error"])
        git(self.checkout, "remote", "remove", "origin")
        self.assertIn("no origin remote", self.make()[1]["error"])

    def test_bad_arguments_and_setup(self):
        for args in (["make", "--project", "bad", "--task", "t", "--agent", "a", "--ref", "r"],
                     ["make", "--project", "o/r", "--task", "../x", "--agent", "a", "--ref", "r"],
                     ["make", "--project", "o/r", "--task", "t", "--agent", "a/b", "--ref", "r"],
                     ["make", "--project", "o/r", "--task", "t", "--agent", "a"],
                     ["check"]):
            self.assertEqual(self.clone(*args)[0], 2, args)
        code, _, err = self.clone("make", "--project", "o/other", "--task", "t", "--agent", "a", "--ref", "main")
        self.assertEqual(code, 3, err)
        self.assertEqual(self.clone("check", "/x", "--machine", "ghost")[0], 1)

    def test_runs_alone_as_it_does_on_a_remote_machine(self):
        path = self.make()[1]["path"]
        with open(os.path.join(SCRIPTS, "clone.py"), encoding="utf-8") as f:
            source = f.read()
        r = subprocess.run([sys.executable, "-", "_run", json.dumps({"op": "check", "path": path})], input=source,
                           capture_output=True, text=True, env={**os.environ, **self.env}, cwd=self.home.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["ours"])


if __name__ == "__main__":
    unittest.main()
