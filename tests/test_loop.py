import copy
import os
import unittest

from helpers import TempHome, run

import config
import loop

WORK = ["start", "implement", "test", "refactor", "regression", "scenario", "pull-request", "code-review",
        "scenario-retrace", "ready"]


def stage(id, actor="lead", nxt=None, **kw):
    s = {"id": id, "actor": actor, "does": f"do {id}", "skills": [], "next": nxt or {"done": "stop"}}
    s.update(kw)
    return s


class Validate(unittest.TestCase):
    def test_standard_loops_are_valid(self):
        self.assertEqual(loop.validate_loop(config.standard()["loop"]), [])
        self.assertEqual(loop.stage_ids(config.standard()["loop"]), WORK)

    def test_problems(self):
        bad = {"roles": {"lead": {"mode": "tab"}, "r": {"mode": "prompt", "prompt": "none", "deny_tools": "Edit"}},
               "prompts": {"x": " "},
               "work": [stage("a", nxt={"done": "nowhere"}), stage("a", actor="ghost"),
                        stage("b", run={"huge": "always", "mid": "if-user-visible"}, count={"high": 0}),
                        {"id": "c", "actor": "lead", "does": "", "skills": "x", "next": {}}]}
        p = "\n".join(loop.validate_loop(bad))
        for words in ("prompt x is empty", "role name 'lead' is not allowed", "mode must be one of",
                      "prompt 'none' does not exist", "deny_tools must be a list", "goes to 'nowhere'",
                      "stage a appears twice", "actor 'ghost'", "names 'huge'", "run for mid", "count for high",
                      "says nothing", "skills must be a list", "next must name"):
            self.assertIn(words, p)


class Plan(unittest.TestCase):
    def setUp(self):
        self.loop = config.standard()["loop"]

    def ids(self, difficulty, trivial=False):
        return [s["id"] for s in loop.plan(self.loop, difficulty, trivial)]

    def test_every_non_trivial_change_gets_a_scenario(self):
        self.assertEqual(self.ids("mid"), WORK)
        self.assertEqual(self.ids("high"), WORK)
        self.assertEqual(self.ids("low"), [s for s in WORK if s != "scenario-retrace"])

    def test_trivial_change_skips_scenario_and_retrace(self):
        trivial = {s["id"]: s for s in loop.plan(self.loop, "mid", trivial=True)}
        self.assertNotIn("scenario", trivial)
        self.assertNotIn("scenario-retrace", trivial)
        self.assertEqual(trivial["regression"]["next"], {"done": "pull-request"})
        self.assertEqual(trivial["code-review"]["next"], {"changes": "implement", "approved": "ready"})

    def test_high_counts_and_extras(self):
        high = {s["id"]: s for s in loop.plan(self.loop, "high")}
        self.assertEqual(high["code-review"]["count"], 2)
        self.assertIn("main branch", high["regression"]["extra"])
        self.assertEqual(high["scenario-retrace"]["next"], {"code": "implement", "scenario": "scenario", "pass": "ready"})

    def test_chained_skips(self):
        l = {"roles": {}, "prompts": {}, "work": [stage("a", nxt={"done": "b"}), stage("b", nxt={"done": "c"}, run={"low": "never"}),
                                                    stage("c", nxt={"done": "d"}, run={"low": "never"}), stage("d")]}
        self.assertEqual([(s["id"], s["next"]["done"]) for s in loop.plan(l, "low")], [("a", "d"), ("d", "stop")])


class Skills(unittest.TestCase):
    LOCAL = {"local-skills:tidy": "/a", "pstack:how": "/b", "x:how": "/c", "scenario": "/d"}

    def test_project_first(self):
        self.assertEqual(loop.resolve_skill("scenario", ["scenario"], self.LOCAL), ("project", "scenario"))
        self.assertEqual(loop.resolve_skill("tidy", [], self.LOCAL), ("bundle", "local-skills:tidy"))
        self.assertEqual(loop.resolve_skill("local-skills:tidy", ["tidy"], self.LOCAL), ("bundle", "local-skills:tidy"))

    def test_ambiguous_and_missing(self):
        self.assertEqual(loop.resolve_skill("how", [], self.LOCAL)[0], "missing")
        self.assertIn("pstack:how", loop.resolve_skill("how", [], self.LOCAL)[1])
        self.assertEqual(loop.resolve_skill("ghost", [], self.LOCAL)[0], "missing")

    def test_project_skill_names_local(self):
        home = TempHome()
        try:
            home.write("repo/.claude/skills/scenario/SKILL.md", "x")
            home.write("repo/.claude/skills/notes/README.md", "x")
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "repo")), ["scenario"])
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "none")), [])
        finally:
            home.close()


class Render(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = copy.deepcopy(config.load("o/r"))
        work = {s["id"]: s for s in self.cfg["loop"]["work"]}
        work["refactor"]["skills"] = ["tidy", "ghost"]
        work["scenario"]["skills"] = ["scenario"]

    def tearDown(self):
        self.home.close()

    def render(self, difficulty, trivial=False, profiles=None):
        resolved = {"tidy": ("bundle", "local-skills:tidy"), "ghost": ("missing", "ghost is nowhere"),
                    "scenario": ("project", "scenario")}
        profiles = profiles or {"code-reviewer": ["opus", "sonnet", "haiku"], "retracer": ["opus", "sonnet"]}
        return loop.render(self.cfg, "634", difficulty, trivial, resolved, profiles,
                           lambda src, v: v if src == "project" else "foreman-kit:" + v.split(":")[-1])

    def test_mid_task(self):
        out = self.render("mid")
        self.assertIn("**Missing skills**", out)
        self.assertIn("- ghost is nowhere", out)
        self.assertIn("| 4 | refactor | lead | `634 refactor` |", out)
        self.assertIn("| foreman-kit:tidy |", out)
        self.assertIn("| 6 | scenario | lead | `634 scenario` |", out)
        self.assertIn("approved → scenario-retrace", out)
        self.assertIn("| code-reviewer | prompt | agent 1: opus | sonnet, haiku | `--disallow Edit,Write,NotebookEdit` |", out)
        self.assertIn("## Prompt for retracer", out)

    def test_trivial_task(self):
        out = self.render("mid", trivial=True)
        self.assertIn("(difficulty mid, trivial)", out)
        self.assertNotIn("| scenario |", out)
        self.assertIn("approved → ready", out)
        self.assertNotIn("## Prompt for retracer", out)

    def test_high_task_reviewers_on_different_models(self):
        out = self.render("high")
        self.assertIn("code-reviewer × 2", out)
        self.assertIn("agent 1: opus; agent 2: sonnet | haiku |", out)
        self.assertIn("`634 code-review <N>`", out)
        one = self.render("high", profiles={"code-reviewer": ["opus"], "retracer": ["opus"]})
        self.assertIn("agent 1: opus; agent 2: opus (only 1 different profile(s) for 2 agents", one)

    def test_assign(self):
        self.assertEqual(loop.assign(["a", "b", "c"], 2), (["a", "b"], ""))
        self.assertEqual(loop.assign(["a"], 1), (["a"], ""))
        self.assertIn("only 1", loop.assign(["a"], 2)[1])
        self.assertEqual(loop.assign([], 1), ([], "no profile for this role"))


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_show_and_bad_arguments(self):
        r = run("loop.py", "show")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| scenario-retrace | retracer |", r.stdout)
        self.assertIn("never | if-not-trivial | if-not-trivial", r.stdout)
        self.assertEqual(run("loop.py", "render").returncode, 2)
        self.assertEqual(run("loop.py", "show", "--project", "bad").returncode, 2)

    def test_render_local_machine(self):
        repo = os.path.join(self.home.root, "repo")
        self.home.write("repo/.claude/skills/scenario/SKILL.md", "x")
        self.home.write("state/herdr-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": repo},
                         "loop": {"work": [{"id": "scenario", "skills": ["scenario"]}]}})
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "high", "--machine", "local")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| 6 | scenario | lead | `9 scenario` |", r.stdout)
        self.assertIn("| scenario |", r.stdout)
        self.assertIn("agent 1: opus; agent 2: sonnet", r.stdout)  # high reviewers fall back to the next tier
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "local",
                "--trivial")
        self.assertNotIn("| scenario |", r.stdout)
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "ghost")
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
