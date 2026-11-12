import json
import os
import unittest
from unittest import mock

from helpers import TempHome, run

import config

MACHINES = {"m1": {"target": "host-1", "enabled": True}, "off": {"target": "host-2", "enabled": False}}


class Levels(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_standard_alone_is_valid(self):
        cfg = config.load()
        self.assertEqual(cfg["launch"]["profile"], "sonnet")
        self.assertEqual(config.validate(cfg), [])

    def test_user_over_standard_and_project_over_user(self):
        self.home.write("config/herdr-foreman/config.json",
                        {"launch": {"profile": "opus"}, "ops": {"check_minutes": 5}})
        self.home.write("state/herdr-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"m1": "/src/r"}, "ops": {"check_minutes": 20}})
        user = config.load()
        self.assertEqual(user["launch"]["profile"], "opus")
        self.assertEqual(user["launch"]["permission"], "bypass")  # untouched key falls back
        project = config.load("o/r")
        self.assertEqual(project["ops"]["check_minutes"], 20)
        self.assertEqual(project["launch"]["profile"], "opus")
        self.assertEqual(project["workspace"], "r")
        self.assertEqual(config.validate(project, saved=MACHINES, project=True), [])

    def test_diff_then_merge_gives_the_full_settings(self):
        base = config.standard()
        full = config.merge(base, {"ops": {"batch": 2}, "labels": {"default": "{task}/{stage}"}})
        self.assertEqual(config.diff(base, full), {"ops": {"batch": 2}, "labels": {"default": "{task}/{stage}"}})
        self.assertEqual(config.merge(base, config.diff(base, full)), full)


class Problems(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def problems(self, over, project=False, skills=None):
        return config.validate(config.merge(self.cfg, over), saved=MACHINES, skills=skills, project=project)

    def test_unknown_agent_kind(self):
        p = self.problems({"profiles": {"sonnet": {"agent": "nope"}}})
        self.assertTrue(any("agent 'nope' is not supported" in x for x in p))

    def test_unknown_setting(self):
        self.assertIn("unknown setting 'opps'", self.problems({"opps": {}}))

    def test_label_placeholder_and_event(self):
        p = self.problems({"labels": {"default": "{task} {stge}", "events": {"nap": "{task}"}}})
        self.assertTrue(any("{stge}" in x for x in p))
        self.assertTrue(any("'nap'" in x for x in p))

    def test_broken_label_format(self):
        self.assertTrue(any(x.startswith("labels: default") for x in self.problems({"labels": {"default": "{task"}})))

    def test_ops_values(self):
        p = self.problems({"ops": {"check_minutes": 0, "batch": 0, "placement": "random",
                                   "disk_check": "yes", "backoff": {"first_hours": 0, "factor": 0.5}}})
        for word in ("check_minutes", "batch", "placement", "disk_check", "first_hours", "factor"):
            self.assertTrue(any(word in x for x in p), word)

    def test_stage_problems(self):
        stages = [{"name": "a", "method": "x", "skills": []}, {"name": "a", "method": "", "skills": "s"}]
        p = self.problems({"loop": {"stages": stages}})
        self.assertIn("loop: stage a appears twice", p)
        self.assertIn("loop: stage a has no method", p)
        self.assertIn("loop: stage a: skills must be a list", p)

    def test_unknown_skill_and_shared_short_name(self):
        over = {"bundle": {"skills": ["p:clean", "clean", "p:gone"]}}
        p = self.problems(over, skills={"p:clean": "/x", "clean": "/y"})
        self.assertIn("skill 'p:gone' is not available on this machine", p)
        self.assertTrue(any("share the name clean in the bundle" in x for x in p))

    def test_profile_and_gateway(self):
        p = self.problems({"launch": {"profile": "nope"},
                           "gateways": {"g": {"kind": "anthropic-compatible", "base_url": "ftp://x",
                                              "token_env": "BAD NAME", "auth": "basic", "models": {}}},
                           "profiles": {"p": {"gateway": "g", "model": "m", "roles": {}}}})
        for word in ("launch: profile", "base_url", "token_env", "auth", "model 'm'", "role opus"):
            self.assertTrue(any(word in x for x in p), word)

    def test_project_machines(self):
        over = {"repo": "bad", "machines": {"m1": "relative/path", "off": "/x", "ghost": "/y"}}
        p = self.problems(over, project=True)
        self.assertIn("project: repo must look like owner/name", p)
        self.assertIn("project: machine m1: project path must start with / or ~", p)
        self.assertIn("project: machine off is disabled in herdr", p)
        self.assertTrue(any("machine ghost is not a saved herdr machine" in x for x in p))
        self.assertTrue(any("machines must name" in x for x in self.problems({"repo": "o/r"}, project=True)))


class Tiers(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_standard_tiers_are_the_harness_models_without_fable(self):
        tiers = config.load()["tiers"]
        self.assertEqual(tiers, {"low": ["haiku"], "mid": ["sonnet"], "high": ["opus"]})
        self.assertNotIn("fable", json.dumps(tiers))

    def test_role_tier(self):
        self.assertEqual(config.role_tier("low"), "low")
        self.assertEqual(config.role_tier("low", "reviewer"), "mid")
        self.assertEqual(config.role_tier("mid", "retracer"), "high")
        self.assertEqual(config.role_tier("high", "reviewer"), "high")
        self.assertEqual(config.role_tier("mid", "tester"), "mid")
        with self.assertRaises(ValueError):
            config.role_tier("huge")

    def test_order_and_fallback(self):
        cfg = config.merge(config.load(), {"tiers": {"mid": ["sonnet", "haiku"]}})
        self.assertEqual(config.tier_profiles(cfg, "mid"), ["sonnet", "haiku"])
        self.assertEqual(config.tier_profiles(cfg, "mid", skip=["sonnet"]), ["haiku"])

    def test_tier_problems(self):
        cfg = config.load()
        p = config.validate(config.merge(cfg, {"tiers": {"huge": ["opus"], "mid": [], "high": ["ghost"]}}))
        self.assertTrue(any("unknown tier 'huge'" in x for x in p))
        self.assertIn("tiers: mid must list at least one profile", p)
        self.assertIn("tiers: high names profile 'ghost', which does not exist", p)

    def test_tier_cli(self):
        r = run("config.py", "tier", "--difficulty", "mid", "--role", "reviewer")
        self.assertEqual(json.loads(r.stdout), {"tier": "high", "profiles": ["opus"], "pick": "opus"})
        r = run("config.py", "tier", "--difficulty", "mid", "--role", "reviewer", "--skip", "opus")
        self.assertEqual(r.returncode, 3)
        self.assertEqual(run("config.py", "tier").returncode, 2)


class Save(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_user_save_stores_only_differences_and_repeats(self):
        full = config.merge(config.standard(), {"ops": {"batch": 3}})
        path, written, problems = config.save("user", full, saved=MACHINES, skills={})
        self.assertEqual(problems, [])
        self.assertEqual(written, {"ops": {"batch": 3}})
        with open(path) as f:
            first = f.read()
        config.save("user", full, saved=MACHINES, skills={})
        with open(path) as f:
            self.assertEqual(f.read(), first)

    def test_invalid_save_writes_nothing(self):
        full = config.merge(config.standard(), {"ops": {"batch": -1}})
        path, _, problems = config.save("user", full, saved=MACHINES, skills={})
        self.assertTrue(problems)
        self.assertFalse(os.path.exists(path))

    def test_project_save_leaves_out_user_values(self):
        self.home.write("config/herdr-foreman/config.json", {"ops": {"batch": 3}})
        full = config.merge(config.load(), {"machines": {"m1": "/src/r"}, "labels": {"default": "{task}"}})
        _, written, problems = config.save("project", full, repo="o/r", saved=MACHINES, skills={})
        self.assertEqual(problems, [])
        self.assertEqual(written, {"machines": {"m1": "/src/r"}, "labels": {"default": "{task}"}, "repo": "o/r"})
        self.assertEqual(config.load("o/r")["ops"]["batch"], 3)

    def test_dry_run_writes_nothing(self):
        full = config.merge(config.standard(), {"ops": {"batch": 3}})
        path, _, problems = config.save("user", full, saved=MACHINES, skills={}, dry_run=True)
        self.assertEqual(problems, [])
        self.assertFalse(os.path.exists(path))


class Skills(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_plugin_and_user_skills_without_broken_links(self):
        self.home.write("plug/skills/tidy/SKILL.md", "x")
        self.home.write("plug/skills/notaskill/README.md", "x")
        self.home.write("off/skills/hidden/SKILL.md", "x")
        self.home.write("user/real/SKILL.md", "x")
        user = os.path.join(self.home.root, "user")
        os.symlink(os.path.join(self.home.root, "nowhere"), os.path.join(user, "broken"))
        plugins = [{"id": "plug@m", "enabled": True, "installPath": os.path.join(self.home.root, "plug")},
                   {"id": "off@m", "enabled": False, "installPath": os.path.join(self.home.root, "off")}]
        found = config.local_skills(plugins=plugins, user_skills_dir=user)
        self.assertEqual(sorted(found), ["plug:tidy", "real"])

    def test_herdr_foreman_is_never_a_candidate_or_a_skill(self):
        other = os.path.dirname(os.path.dirname(self.home.write("other/.claude-plugin/plugin.json", {"name": "other"})))
        self.home.write("other/skills/tidy/SKILL.md", "x")
        copy = os.path.dirname(os.path.dirname(self.home.write("copy/.claude-plugin/plugin.json",
                                                               {"name": "herdr-foreman"})))
        argv = ["claude", "--plugin-dir", other, f"--plugin-dir={config.SELF_DIR}", "--plugin-dir", copy,
                "--plugin-dir", "/no/such/dir", "--model", "x"]
        self.assertEqual(config.session_plugin_dirs(argv), [other])
        plugins = [{"id": "other@inline", "enabled": True, "installPath": other},
                   {"id": "herdr-foreman@herdr-skills", "enabled": True, "installPath": config.SELF_DIR}]
        found = config.local_skills(plugins, user_skills_dir=os.path.join(self.home.root, "none"))
        self.assertEqual(list(found), ["other:tidy"])
        p = config.validate(config.merge(config.load(), {"plugin_dirs": [config.SELF_DIR, copy]}))
        self.assertEqual(sum("is herdr-foreman itself" in x for x in p), 2)

    def test_plugin_dirs_go_to_claude_plugin_list(self):
        listing = mock.Mock(stdout="[]")
        with mock.patch.object(config.subprocess, "run", return_value=listing) as fake:
            config.plugin_list(["/a", "~/b"])
        self.assertEqual(fake.call_args[0][0], ["claude", "--plugin-dir", "/a", "--plugin-dir",
                                                os.path.expanduser("~/b"), "plugin", "list", "--json"])

    def test_plugin_dirs_settings(self):
        plug = os.path.dirname(os.path.dirname(self.home.write("plug/.claude-plugin/plugin.json", {"name": "plug"})))
        cfg = config.load()
        self.assertEqual(config.validate(config.merge(cfg, {"plugin_dirs": [plug]})), [])
        p = config.validate(config.merge(cfg, {"plugin_dirs": [self.home.root, "/no/such/dir"]}))
        self.assertIn(f"plugin_dirs: {self.home.root} has no .claude-plugin/plugin.json", p)
        self.assertIn("plugin_dirs: /no/such/dir has no .claude-plugin/plugin.json", p)
        self.assertIn("plugin_dirs must be a list of directory paths",
                      config.validate(config.merge(cfg, {"plugin_dirs": "/a"})))
        self.assertEqual(config.plugin_dirs({"plugin_dirs": [plug, "/no/such/dir"]}), [plug])

    def test_project_skills_order_without_repeats(self):
        cfg = config.merge(config.load(), {"bundle": {"skills": ["a"]}})
        cfg["loop"]["stages"][2]["skills"] = ["b", "a"]
        self.assertEqual(config.project_skills(cfg, ["c", "b"]), ["a", "b", "c"])


class Labels(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_default_and_event_labels(self):
        self.assertEqual(config.label(self.cfg, "review", task="634", stage="review 2"), "634 review 2")
        self.assertEqual(config.label(self.cfg, "blocked", task="634"), "634 blocked")

    def test_stage_table(self):
        self.cfg["loop"]["stages"][2]["skills"] = ["local-skills:deep-clean-code"]
        table = config.stages_markdown(self.cfg, "634")
        self.assertIn("| clean | `634 clean` | foreman-kit:deep-clean-code |", table)
        self.assertIn("`634 review <N>`", table)


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_bad_project_name(self):
        r = run("config.py", "show", "--project", "not-a-repo")
        self.assertEqual(r.returncode, 2)

    def test_paths_and_show(self):
        r = run("config.py", "paths", "--project", "o/r")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(json.loads(r.stdout)["ledger"].endswith("projects/o-r/ledger.md"))
        r = run("config.py", "show")
        self.assertEqual(json.loads(r.stdout)["launch"]["profile"], "sonnet")

    def test_save_needs_level(self):
        self.assertEqual(run("config.py", "save", stdin="{}").returncode, 2)
        self.assertEqual(run("config.py", "save", "project", stdin="{}").returncode, 2)
        self.assertEqual(run("config.py", "save", "everyone", stdin="{}").returncode, 2)

    def test_member_state_local(self):
        repo = os.path.join(self.home.root, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        home = os.path.join(self.home.root, "home")
        os.makedirs(home)
        env = {"HOME": home}
        r = run("config.py", "member", "local", repo, env=env)
        state = json.loads(r.stdout)
        self.assertEqual((r.returncode, state["checkout"], state["ready"]), (3, True, False))
        self.assertIn("not trusted", state["reason"])
        self.home.write("home/.claude.json", {"projects": {repo: {"hasTrustDialogAccepted": True}}})
        r = run("config.py", "member", "local", repo, env=env)
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {"checkout": True, "ready": True, "reason": ""}))
        r = run("config.py", "member", "local", os.path.join(self.home.root, "nope"), env=env)
        self.assertEqual(json.loads(r.stdout)["checkout"], False)
        self.assertEqual(run("config.py", "member", "local").returncode, 2)


if __name__ == "__main__":
    unittest.main()
