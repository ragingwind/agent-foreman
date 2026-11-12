import json
import os
import subprocess
import unittest

from helpers import TempHome, run

import config
import score

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


class Repo:
    """A throwaway repository with a `main` branch and a feature branch."""

    def __init__(self, home):
        self.dir = os.path.join(home.root, "repo")
        os.makedirs(self.dir)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", "hello\n")
        self.write("src/app.py", "x = 1\n")
        self.commit("init")
        self.git("checkout", "-q", "-b", "feature")

    def git(self, *args):
        return subprocess.run(GIT + ["-C", self.dir, *args], capture_output=True, text=True, check=True).stdout

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def score(self, *extra):
        r = run("score.py", "diff", "--base", "main", "--cwd", self.dir, *extra)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)


class Pure(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()["difficulty"]

    def tearDown(self):
        self.home.close()

    def test_globs_match_at_the_top_too(self):
        self.assertTrue(score.matches("auth/login.py", "**/auth/**"))
        self.assertTrue(score.matches("src/auth/login.py", "**/auth/**"))
        self.assertTrue(score.matches("README.md", "**/*.md"))
        self.assertFalse(score.matches("src/author.py", "**/auth/**"))

    def test_impact(self):
        self.assertEqual(score.impact(["src/auth/x.py", "README.md"], self.cfg)[0], 3)
        self.assertEqual(score.impact(["src/api/routes.py"], self.cfg)[0], 2)
        self.assertEqual(score.impact(["src/app.py"], self.cfg)[0], 1)
        level, reasons, docs_only = score.impact(["README.md", "tests/test_app.py"], self.cfg)
        self.assertEqual((level, docs_only), (0, False))
        self.assertTrue(score.impact(["docs/guide.md", "README.md"], self.cfg)[2])

    def test_level_rule(self):
        r = score.result(1, [], 2, [], False, None, {}, [])
        self.assertEqual((r["level"], r["difficulty"]), (2, "high"))
        r = score.result(2, [], 1, [], False, None, {}, [])
        self.assertEqual((r["level"], r["difficulty"], r["person_approves_merge"]), (2, "high", True))
        r = score.result(3, [], 3, [], False, None, {}, [])
        self.assertEqual(r["level"], 3)
        r = score.result(0, [], 0, [], True, None, {}, [])
        self.assertEqual((r["difficulty"], r["trivial_candidate"]), ("low", True))

    def test_never_goes_down(self):
        r = score.result(0, [], 1, [], False, "high", {}, [])
        self.assertEqual(r["difficulty"], "high")
        self.assertIn("kept high", r["judge"][-1])


class Diff(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.repo = Repo(self.home)

    def tearDown(self):
        self.home.close()

    def test_small_runtime_change_is_mid(self):
        self.repo.write("src/app.py", "x = 2\n")
        self.repo.commit("change x")
        r = self.repo.score()
        self.assertEqual((r["likelihood"], r["impact"], r["difficulty"]), (0, 1, "mid"))
        self.assertEqual(r["metrics"]["lines"], 2)

    def test_docs_only_change_is_a_trivial_candidate(self):
        self.repo.write("README.md", "hello there\n")
        self.repo.commit("reword readme")
        r = self.repo.score()
        self.assertEqual((r["difficulty"], r["trivial_candidate"]), ("low", True))

    def test_large_spread_fix_on_critical_path_is_high(self):
        for i in range(12):
            self.repo.write(f"pkg{i % 4}/m{i}.py", "\n".join(f"v{j} = {j}" for j in range(40)) + "\n")
        self.repo.write("src/auth/token.py", "secret = 1\n")
        self.repo.commit("fix login token refresh")
        r = self.repo.score()
        self.assertEqual(r["likelihood"], 3)
        self.assertEqual(r["impact"], 3)
        self.assertEqual((r["level"], r["difficulty"]), (3, "high"))
        self.assertTrue(any("a bug fix" in x for x in r["likelihood_reasons"]))

    def test_recent_fix_on_touched_file_counts(self):
        self.repo.git("checkout", "-q", "main")
        self.repo.write("src/app.py", "x = 3\n")
        self.repo.commit("fix x overflow")
        self.repo.git("checkout", "-q", "feature")
        self.repo.git("rebase", "-q", "main")
        self.repo.write("src/app.py", "x = 4\n")
        self.repo.commit("tune x")
        r = self.repo.score()
        self.assertEqual(len(r["metrics"]["recent_fixes"]), 1)
        self.assertEqual(r["likelihood"], 1)

    def test_previous_and_bad_base(self):
        self.repo.write("README.md", "hi\n")
        self.repo.commit("docs")
        self.assertEqual(self.repo.score("--previous", "mid")["difficulty"], "mid")
        r = run("score.py", "diff", "--base", "nope", "--cwd", self.repo.dir)
        self.assertEqual(r.returncode, 1)


class Estimate(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_estimate_from_paths_and_size(self):
        r = run("score.py", "estimate", "--project", "o/r", "--paths", "src/api/routes.py,src/app.py",
                "--lines", "600", "--bug")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["likelihood"], out["impact"], out["level"], out["difficulty"]), (2, 2, 3, "high"))
        self.assertIn("estimate mode", out["judge"][-1])

    def test_estimate_needs_project(self):
        self.assertEqual(run("score.py", "estimate").returncode, 2)


if __name__ == "__main__":
    unittest.main()
