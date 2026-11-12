import json
import os
import unittest

from helpers import TempHome

import adapters
import config
from adapters import claude


class Interface(unittest.TestCase):
    def test_every_adapter_defines_the_interface(self):
        for kind, module in adapters.ADAPTERS.items():
            for name in adapters.REQUIRED:
                self.assertTrue(hasattr(module, name), f"{kind} lacks {name}")
            self.assertEqual(module.KIND, kind)

    def test_every_adapter_has_its_screen_page(self):
        for kind in adapters.KINDS:
            self.assertTrue(os.path.isfile(os.path.join(config.SKILL_DIR, "adapters", f"{kind}.md")), kind)

    def test_unknown_kind(self):
        with self.assertRaises(ValueError):
            adapters.get("nope")
        self.assertEqual(adapters.kind_of({}), "claude")
        self.assertEqual(adapters.kind_of({"agent": "x"}), "x")


class Claude(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_command(self):
        argv, env, clear = claude.command(self.cfg, "sonnet", name="issue-1", session_id="abc",
                                          worktree=True, bundle="/b", environ={})
        self.assertEqual(argv, ["claude", "-w", "issue-1", "--name", "issue-1", "--session-id", "abc",
                                "--model", "sonnet", "--dangerously-skip-permissions", "--plugin-dir", "/b"])
        self.assertEqual(env, {})
        self.assertIn("ANTHROPIC_BASE_URL", clear)
        argv, _, _ = claude.command(self.cfg, "opus", worktree=False, print_mode=True, environ={},
                                    disallowed=["Edit", "Write"])
        self.assertEqual(argv, ["claude", "-p", "--output-format", "json", "--model", "opus",
                                "--dangerously-skip-permissions", "--disallowedTools", "Edit,Write"])

    def test_token_missing(self):
        cfg = config.merge(self.cfg, {
            "gateways": {"gw": {"kind": "anthropic-compatible", "base_url": "https://x", "token_env": "T",
                                "auth": "bearer", "models": {"m": {"id": "m-1", "context": 10}}}},
            "profiles": {"p": {"gateway": "gw", "model": "m", "roles": {"opus": "m", "sonnet": "m", "haiku": "m"}}}})
        with self.assertRaises(adapters.TokenMissing) as e:
            claude.command(cfg, "p", environ={})
        self.assertEqual(e.exception.variable, "T")
        argv, env, _ = claude.command(cfg, "p", worktree=False, environ={"T": "v"})
        self.assertEqual(argv[:3], ["claude", "--model", "m-1"])
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "v")

    def test_skill_name_and_layout(self):
        self.assertEqual(claude.skill_name("local-skills:deep-clean-code"), "foreman-kit:deep-clean-code")
        files = claude.bundle_layout({"tidy": {"SKILL.md": b"x", "scripts/run.py": b"y"}})
        self.assertEqual(sorted(files), [".claude-plugin/plugin.json", "hooks/hooks.json", "skills/tidy/SKILL.md",
                                         "skills/tidy/scripts/run.py"])
        self.assertEqual(json.loads(files[".claude-plugin/plugin.json"])["name"], "foreman-kit")

    def test_last_answers(self):
        sid = "0123abcd-0000"
        lines = [{"type": "user", "message": {"content": "q1"}},
                 {"type": "assistant", "message": {"content": [{"type": "text", "text": "a1"}]}},
                 {"type": "user", "message": {"content": "q2"}},
                 {"type": "assistant", "message": {"content": [{"type": "text", "text": "a2"}]}}]
        self.home.write(f"projects/x/{sid}.jsonl", "\n".join(json.dumps(x) for x in lines))
        root = os.path.join(self.home.root, "projects")
        self.assertEqual(claude.last_answers(sid, 1, root=root), (["a2"], 2))
        self.assertEqual(claude.last_answers(sid, 5, root=root), (["a1", "a2"], 2))
        with self.assertRaises(adapters.NoTranscript):
            claude.last_answers("ffff0000-1111", 1, root=root)


if __name__ == "__main__":
    unittest.main()
