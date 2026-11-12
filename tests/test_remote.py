import shlex
import subprocess
import unittest

from helpers import run

import remote


class Remote(unittest.TestCase):
    def test_runs_in_the_login_shell_with_quoting_kept(self):
        argv = remote.remote_argv("host-1", ["python3", "launch.py", "--out", "runs/a b.json", "it's"], cwd="/w d")
        self.assertEqual(argv[:4], ["ssh", "-o", "BatchMode=yes", "host-1"])
        self.assertTrue(argv[4].startswith('exec "$SHELL" -lic '))
        # What the login shell receives as its -c argument, after the remote shell's own parsing:
        inner = shlex.split(argv[4])[-1]
        self.assertEqual(inner, "cd '/w d' && python3 launch.py --out 'runs/a b.json' 'it'\"'\"'s'")
        self.assertEqual(shlex.split(inner)[3:], ["python3", "launch.py", "--out", "runs/a b.json", "it's"])

    def test_local_runs_directly_and_passes_the_exit_code(self):
        self.assertEqual(run("remote.py", "local", "--", "sh", "-c", "exit 7").returncode, 7)

    def test_bad_arguments(self):
        self.assertEqual(run("remote.py", "local").returncode, 2)
        self.assertEqual(run("remote.py", "local", "--").returncode, 2)


if __name__ == "__main__":
    unittest.main()
