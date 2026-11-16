import fcntl
import json
import os
import subprocess
import sys
import time
import unittest

from helpers import SCRIPTS, TempHome, run

FULLTEST = os.path.join(SCRIPTS, "fulltest.py")


class FullTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.lock = os.path.join(self.home.root, "cache", "agent-foreman", "locks", "full-test.lock")
        self.marker = os.path.join(self.home.root, "ran")

    def test_runs_the_command_and_keeps_its_exit_code(self):
        r = run("fulltest.py", "--", f"touch {self.marker} && exit 3", workdir=self.home.root)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertTrue(os.path.exists(self.marker))
        self.assertTrue(os.path.exists(self.lock))  # under XDG_CACHE_HOME, not the person's home
        with open(self.lock) as f:
            self.assertEqual(json.load(f)["cwd"], os.path.realpath(self.home.root))
        self.assertEqual(run("fulltest.py", "--", "true").returncode, 0)
        self.assertEqual(run("fulltest.py", "sh", "-c", "'exit 4'").returncode, 4)  # several words are one command

    def test_not_run_under_the_disk_floor(self):
        r = run("fulltest.py", "--min-free-gb", "1000000000", "--", f"touch {self.marker}", workdir=self.home.root)
        self.assertEqual(r.returncode, 75)
        self.assertIn("fulltest.py: not run:", r.stderr)
        self.assertIn("under the floor of 1e+09 GB", r.stderr)
        self.assertFalse(os.path.exists(self.marker))

    def test_bad_arguments(self):
        for args in (["--"], [], ["--min-free-gb", "-1", "--", "true"]):
            self.assertEqual(run("fulltest.py", *args).returncode, 2, args)

    def test_waits_while_another_run_holds_the_lock(self):
        os.makedirs(os.path.dirname(self.lock))
        with open(self.lock, "a+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            held.write('{"task": "7"}')
            held.flush()
            proc = subprocess.Popen([sys.executable, FULLTEST, "--", f"touch {self.marker}"], cwd=self.home.root,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            deadline = time.time() + 10
            first = proc.stderr.readline()
            self.assertIn('waiting for the full-test lock on this machine, held by {"task": "7"}', first)
            time.sleep(0.3)
            self.assertFalse(os.path.exists(self.marker))  # not while the lock is held
            self.assertIsNone(proc.poll())
        proc.wait(timeout=max(1, deadline - time.time()))
        proc.stdout.close()
        proc.stderr.close()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
