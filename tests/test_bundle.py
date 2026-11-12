import io
import os
import unittest
import zipfile
from unittest import mock

from helpers import TempHome

import bundle
import config


class Bundle(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.skill = os.path.dirname(self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy."))
        self.home.write("skills/tidy/scripts/run.py", "print('hi')")
        self.home.write("skills/tidy/__pycache__/x.pyc", "junk")
        self.home.write("state/herdr-foreman/groups/o-r/group.json",
                        {"repo": "o/r", "members": {"local": "/src/r"}, "bundle": {"skills": ["p:tidy"]}})
        patcher = mock.patch.object(bundle, "local_skills", return_value={"p:tidy": self.skill})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.home.close()

    def test_same_content_same_hash_and_change_makes_new(self):
        h1, files, skills = bundle.build("o/r", [])
        h2, _, _ = bundle.build("o/r", [])
        self.assertEqual(h1, h2)
        self.assertEqual(skills, ["foreman-kit:tidy"])
        self.assertIn("skills/tidy/scripts/run.py", files)
        self.assertNotIn("skills/tidy/__pycache__/x.pyc", files)
        for rel in (".claude-plugin/plugin.json", "config.json", "loop.md", "scripts/launch.py",
                    "scripts/config.py", "scripts/transcript.py"):
            self.assertIn(rel, files)
        self.home.write("skills/tidy/SKILL.md", "---\nname: tidy\n---\nTidy more.")
        h3, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h3)

    def test_settings_change_makes_new_hash(self):
        h1, _, _ = bundle.build("o/r", [])
        self.home.write("config/herdr-foreman/config.json", {"launch": {"profile": "opus"}})
        h2, _, _ = bundle.build("o/r", [])
        self.assertNotEqual(h1, h2)

    def test_written_once_then_cached(self):
        h, files, _ = bundle.build("o/r", [])
        path, status = bundle.write_local(h, files)
        self.assertEqual(status, "built")
        self.assertTrue(os.path.isfile(os.path.join(path, "skills", "tidy", "SKILL.md")))
        self.assertEqual(bundle.write_local(h, files), (path, "cached"))

    def test_zip_holds_every_file(self):
        _, files, _ = bundle.build("o/r", [])
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

    def test_group_without_settings_stops(self):
        with self.assertRaises(SystemExit) as e:
            bundle.build("o/other", [])
        self.assertEqual(e.exception.code, config.EXIT_SETUP_NEEDED)

    def test_unknown_or_disabled_machine(self):
        machines = {"off": {"target": "h", "enabled": False}}
        with mock.patch.object(bundle, "herdr_machines", return_value=machines):
            for label in ("ghost", "off"):
                with self.assertRaises(SystemExit) as e:
                    bundle.main(["push", label, "--group", "o/r"])
                self.assertEqual(e.exception.code, 2)

    def test_bad_arguments(self):
        for argv in (["push", "--group", "o/r"], ["build", "--group", "bad"]):
            with self.assertRaises(SystemExit) as e:
                bundle.main(argv)
            self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
