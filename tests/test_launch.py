import json
import os
import shutil
import unittest

from helpers import SCRIPTS, TempHome, run

GATEWAY = {
    "kind": "anthropic-compatible", "base_url": "https://gw.example/anthropic", "token_env": "HF_TEST_TOKEN",
    "auth": "bearer", "models": {"m": {"id": "model-1", "context": 100000}},
}
PROFILE = {"gateway": "gw", "model": "m", "roles": {"opus": "m", "sonnet": "m", "haiku": "m"}}


class Launch(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_skill_mode_dry_run(self):
        r = run("launch.py", "--name", "issue-1", "--session-id", "abc-123", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("command: claude -w issue-1 --name issue-1 --session-id abc-123 --model sonnet "
                      "--dangerously-skip-permissions", r.stdout)
        self.assertNotIn("--plugin-dir", r.stdout)

    def test_bundle_mode_adds_plugin_dir_and_uses_bundle_settings(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/bundle.json", {"agent": "claude"})
        self.home.write("bundle/config.json", {"gateways": {"anthropic": {"kind": "anthropic"}},
                                               "profiles": {"opus": {"gateway": "anthropic", "model": "opus"}},
                                               "launch": {"profile": "opus", "permission": "default",
                                                          "worktree": False}})
        r = run("launch.py", "--dry-run", cwd=os.path.join(root, "scripts"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"command: claude --model opus --plugin-dir {root}", r.stdout)

    def test_profile_for_another_agent_than_the_bundle_is_setup(self):
        root = os.path.join(self.home.root, "bundle")
        shutil.copytree(SCRIPTS, os.path.join(root, "scripts"))
        self.home.write("bundle/bundle.json", {"agent": "elsewhere"})
        self.home.write("bundle/config.json", {"gateways": {"anthropic": {"kind": "anthropic"}},
                                               "profiles": {"opus": {"gateway": "anthropic", "model": "opus"}},
                                               "launch": {"profile": "opus", "permission": "default",
                                                          "worktree": False}})
        r = run("launch.py", "--dry-run", cwd=os.path.join(root, "scripts"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("this bundle is for elsewhere", r.stderr)

    def test_unknown_agent_kind_is_setup(self):
        self.home.write("config/herdr-foreman/config.json", {"profiles": {"sonnet": {"agent": "nope"}}})
        r = run("launch.py", "--dry-run")
        self.assertEqual(r.returncode, 3)
        self.assertIn("agent 'nope' is not supported", r.stderr)

    def test_unknown_profile_is_setup(self):
        self.assertEqual(run("launch.py", "nope", "--dry-run").returncode, 3)

    def test_bad_settings_is_setup(self):
        self.home.write("config/herdr-foreman/config.json", {"launch": {"permission": "maybe"}})
        r = run("launch.py", "--dry-run")
        self.assertEqual(r.returncode, 3)
        self.assertIn("permission", r.stderr)

    def test_gateway_token_missing_then_set_without_printing_it(self):
        self.home.write("config/herdr-foreman/config.json", {"gateways": {"gw": GATEWAY}, "profiles": {"p": PROFILE}})
        env = {"HF_TEST_TOKEN": ""}
        r = run("launch.py", "p", "--dry-run", env=env)
        self.assertEqual(r.returncode, 4)
        self.assertIn("HF_TEST_TOKEN", r.stderr)
        r = run("launch.py", "p", "--dry-run", env={"HF_TEST_TOKEN": "secret-value-xyz"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ANTHROPIC_AUTH_TOKEN", r.stdout)
        self.assertNotIn("secret-value-xyz", r.stdout + r.stderr)

    def test_bad_project_argument(self):
        self.assertEqual(run("launch.py", "--project", "bad", "--dry-run").returncode, 2)


if __name__ == "__main__":
    unittest.main()
