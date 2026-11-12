import io
import json
import os
import unittest
import zipfile
from unittest import mock

from helpers import TempHome, run

import bundle
import config


class Bundle(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.skill = os.path.dirname(self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy."))
        self.home.write("skills/tidy/scripts/run.py", "print('hi')")
        self.home.write("skills/tidy/__pycache__/x.pyc", "junk")
        self.home.write("state/herdr-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": "/src/r"}, "bundle": {"skills": ["p:tidy"]}})
        patcher = mock.patch.object(bundle, "local_skills", return_value={"p:tidy": self.skill})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.home.close()

    def test_same_content_same_hash_and_change_makes_new(self):
        h1, files, skills, _ = bundle.build("o/r", [])
        h2, _, _, _ = bundle.build("o/r", [])
        self.assertEqual(h1, h2)
        self.assertEqual(skills, ["foreman-kit:tidy"])
        self.assertIn("skills/tidy/scripts/run.py", files)
        self.assertNotIn("skills/tidy/__pycache__/x.pyc", files)
        for rel in ("bundle.json", ".claude-plugin/plugin.json", "config.json", "lead.md", "scripts/launch.py",
                    "scripts/config.py", "scripts/transcript.py", "scripts/adapters/__init__.py",
                    "scripts/adapters/base.py", "scripts/adapters/claude.py"):
            self.assertIn(rel, files)
        self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy more.")
        h3, _, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h3)

    def test_every_script_starts_from_the_bundle(self):
        h, files, _, _ = bundle.build("o/r", [])
        path, _ = bundle.write_local(h, files)
        for name in bundle.BUNDLED:
            if name == "heartbeat.py":
                continue  # a hook command with no --help; test_status runs it
            r = run(name, "--help", cwd=os.path.join(path, "scripts"))
            self.assertEqual(r.returncode, 0, f"{name}: {r.stderr[-300:]}")

    def test_heartbeat_hooks_point_at_the_bundled_script(self):
        _, files, _, _ = bundle.build("o/r", [])
        hooks = json.loads(files["hooks/hooks.json"])["hooks"]
        commands = [h["command"] for event in ("PostToolUse", "Stop") for group in hooks[event] for h in group["hooks"]]
        self.assertEqual(commands, ['python3 "${CLAUDE_PLUGIN_ROOT}/scripts/heartbeat.py" post',
                                    'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/heartbeat.py" stop'])
        self.assertIn("scripts/heartbeat.py", files)
        self.assertIn(".claude-plugin/plugin.json", files)  # the bundle root is the plugin root

    def test_settings_change_makes_new_hash(self):
        h1, _, _, _ = bundle.build("o/r", [])
        self.home.write("config/herdr-foreman/config.json", {"launch": {"profile": "opus"}})
        h2, _, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h2)

    def test_written_once_then_cached(self):
        h, files, _, _ = bundle.build("o/r", [])
        path, status = bundle.write_local(h, files)
        self.assertEqual(status, "built")
        self.assertTrue(os.path.isfile(os.path.join(path, "skills", "tidy", "SKILL.md")))
        self.assertEqual(bundle.write_local(h, files), (path, "cached"))

    def test_zip_holds_every_file(self):
        _, files, _, _ = bundle.build("o/r", [])
        with zipfile.ZipFile(io.BytesIO(bundle.zipped(files))) as z:
            self.assertEqual({n: z.read(n) for n in z.namelist()}, files)

    def test_unknown_skill_stops(self):
        with self.assertRaises(SystemExit) as e:
            bundle.build("o/r", ["p:gone"])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_two_skills_with_one_name_stop(self):
        with mock.patch.object(bundle, "local_skills", return_value={"p:tidy": self.skill, "tidy": self.skill}):
            with self.assertRaises(SystemExit) as e:
                bundle.build("o/r", ["tidy"])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_project_without_settings_stops(self):
        with self.assertRaises(SystemExit) as e:
            bundle.build("o/other", [])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_loop_skills_project_first_then_bundle_then_warning(self):
        self.home.write("config/herdr-foreman/config.json",
                        {"loop": {"work": [{"id": "refactor", "skills": ["tidy", "scenario", "ghost"]}]}})
        _, files, skills, warnings = bundle.build("o/r", [], project_names=["scenario"])
        self.assertEqual(skills, ["foreman-kit:tidy"])          # bundle.skills and the loop name the same skill
        self.assertFalse(any(rel.startswith("skills/scenario/") for rel in files))  # a project skill stays put
        self.assertEqual(len(warnings), 1)
        self.assertIn("ghost", warnings[0])

    def test_unknown_or_disabled_machine(self):
        machines = {"off": {"target": "h", "enabled": False}}
        with mock.patch.object(bundle, "herdr_machines", return_value=machines):
            for label in ("ghost", "off"):
                with self.assertRaises(SystemExit) as e:
                    bundle.main(["push", label, "--project", "o/r"])
                self.assertEqual(e.exception.code, 2)

    def test_bad_arguments(self):
        for argv in (["push", "--project", "o/r"], ["build", "--project", "bad"]):
            with self.assertRaises(SystemExit) as e:
                bundle.main(argv)
            self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
