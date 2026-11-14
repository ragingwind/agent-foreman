import copy
import json
import os
import unittest

from helpers import TempHome, run

import config
import loop

WORK = ["plan", "build", "verify", "review", "simplify", "fix", "recheck", "finalize"]
STAGES = ["plan", "build", "verify", "review", "finalize"]
CHECK = ["redteam-review", "test"]


def stage(id, actor="lead", nxt=None, **kw):
    s = {"id": id, "actor": actor, "does": f"do {id}", "skills": [], "next": nxt or {"done": "stop"}}
    s.update(kw)
    return s


class Validate(unittest.TestCase):
    def test_standard_loops_are_valid(self):
        std = config.standard()["loop"]
        self.assertEqual(loop.validate_loop(std), [])
        self.assertEqual(loop.step_ids(std), WORK)
        self.assertEqual(loop.stage_ids(std), STAGES)
        self.assertEqual(loop.step_ids(std, "check"), CHECK)
        self.assertEqual(loop.stage_ids(std, "check"), CHECK)
        self.assertEqual(loop.stage_ids(std, "manage"), loop.step_ids(std, "manage"))  # a step without a stage is one

    def test_every_default_skill_is_used(self):
        std = config.standard()["loop"]
        used = {n for w in loop.LOOPS for s in std.get(w, []) for n in s.get("skills", [])}
        self.assertEqual(used, set(loop.KIT))

    def test_check_steps_may_send_the_task_back_to_a_work_step(self):
        base = {"roles": {"r": {"mode": "prompt"}}, "prompts": {}, "work": [stage("build")]}
        ok = dict(base, check=[stage("x", actor="r", nxt={"changes": "build", "pass": "stop"})])
        self.assertEqual(loop.validate_loop(ok), [])
        bad = dict(base, check=[stage("x", actor="r", nxt={"changes": "nowhere"})])
        self.assertIn("goes to 'nowhere'", "\n".join(loop.validate_loop(bad)))
        back = dict(base, work=[stage("a", nxt={"done": "x"})], check=[stage("x", actor="r")])
        self.assertIn("goes to 'x'", "\n".join(loop.validate_loop(back)))  # a work step cannot jump into the check loop

    def test_stage_problems(self):
        base = {"roles": {}, "prompts": {}}
        apart = dict(base, work=[stage("a", stage="s1", nxt={"done": "b"}), stage("b", stage="s2", nxt={"done": "c"}),
                                 stage("c", stage="s1")])
        self.assertIn("loop: work stage s1: its steps must come one after another", loop.validate_loop(apart))
        clash = dict(base, work=[stage("a", stage="b", nxt={"done": "b"}), stage("b", stage="s2")])
        self.assertIn("loop: work stage b has the name of step b, which is in stage s2", loop.validate_loop(clash))
        own = dict(base, work=[stage("a", stage="a", nxt={"done": "b"}), stage("b")])
        self.assertEqual(loop.validate_loop(own), [])
        bad = dict(base, work=[stage("a", stage="no spaces")])
        self.assertTrue(any("stage must be a name" in p for p in loop.validate_loop(bad)))

    def test_problems(self):
        bad = {"roles": {"lead": {"mode": "tab"}, "r": {"mode": "prompt", "prompt": "none", "deny_tools": "Edit"}},
               "prompts": {"x": " "},
               "work": [stage("a", nxt={"done": "nowhere"}), stage("a", actor="ghost"),
                        stage("b", run={"huge": "always", "mid": "if-user-visible"}, count={"high": 0}),
                        {"id": "c", "actor": "lead", "does": "", "skills": "x", "next": {}}]}
        p = "\n".join(loop.validate_loop(bad))
        for words in ("prompt x is empty", "role name 'lead' is not allowed", "mode must be one of",
                      "prompt 'none' does not exist", "deny_tools must be a list", "goes to 'nowhere'",
                      "step a appears twice", "actor 'ghost'", "names 'huge'", "run for mid", "count for high",
                      "says nothing", "skills must be a list", "next must name"):
            self.assertIn(words, p)


class Plan(unittest.TestCase):
    def setUp(self):
        self.loop = config.standard()["loop"]

    def ids(self, difficulty, trivial=False, which="work"):
        return [s["id"] for s in loop.plan(self.loop, difficulty, trivial, which)]

    def test_every_difficulty_runs_the_whole_build_session(self):
        for level in loop.LEVELS:
            self.assertEqual(self.ids(level), WORK)
            self.assertEqual(self.ids(level, which="check"), CHECK)

    def test_trivial_task_skips_the_review_stage(self):
        trivial = {s["id"]: s for s in loop.plan(self.loop, "mid", trivial=True)}
        self.assertEqual(list(trivial), ["plan", "build", "verify", "finalize"])
        self.assertEqual(trivial["verify"]["next"], {"fail": "build", "done": "finalize"})
        self.assertEqual(self.ids("mid", True, "check"), CHECK)  # QA always runs

    def test_review_stage_repeats_and_check_goes_back_to_work(self):
        mid = {s["id"]: s for s in loop.plan(self.loop, "mid")}
        self.assertEqual(mid["recheck"]["next"], {"changes": "fix", "approved": "finalize"})
        steps = loop.plan(self.loop, "mid")
        self.assertTrue(loop.has_rounds(steps, "review"))
        self.assertFalse(loop.has_rounds(steps, "plan"))
        check = {s["id"]: s for s in loop.plan(self.loop, "mid", which="check")}
        self.assertEqual(check["test"]["next"], {"fail": "build", "script": "verify", "pass": "stop"})

    def test_steps_carry_their_stage_and_an_empty_stage_drops(self):
        self.assertEqual([(s["stage"], s["id"]) for s in loop.plan(self.loop, "mid")][3:5],
                         [("review", "review"), ("review", "simplify")])
        l = {"roles": {}, "prompts": {}, "work": [stage("a", stage="s1", nxt={"done": "b"}),
                                                    stage("b", stage="s2", nxt={"done": "c"}, run={"low": "never"}),
                                                    stage("c", stage="s3")]}
        self.assertEqual([s["stage"] for s in loop.plan(l, "low")], ["s1", "s3"])

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

    def test_default_skill_unless_replaced(self):
        self.assertEqual(loop.resolve("review", [], self.LOCAL), ("kit", "review"))
        self.assertEqual(loop.resolve("simplify", [], self.LOCAL, {"simplify": "tidy"}), ("bundle", "local-skills:tidy"))
        self.assertEqual(loop.resolve("cross-check", ["scenario"], self.LOCAL, {"cross-check": "scenario"}),
                         ("project", "scenario"))
        self.assertEqual(loop.resolve("smoke", [], self.LOCAL, {"smoke": "ghost"})[0], "missing")
        self.assertEqual(loop.resolve("tidy", [], self.LOCAL), ("bundle", "local-skills:tidy"))  # not a default skill

    def test_project_skill_names_local(self):
        home = TempHome()
        try:
            home.write("repo/.claude/skills/scenario/SKILL.md", "x")
            home.write("repo/.claude/skills/notes/README.md", "x")
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "repo")), ["scenario"])
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "none")), [])
        finally:
            home.close()


def kit_name(src, v):
    return v if src == "project" else "foreman-kit:" + v.split(":")[-1]


class Render(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = copy.deepcopy(config.load("o/r"))
        self.resolved = {n: ("kit", n) for n in loop.KIT}
        self.resolved["simplify"] = ("bundle", "local-skills:tidy")
        self.profiles = {"pair": ["sonnet", "opus"], "redteam": ["opus", "sonnet"], "qa": ["opus"]}

    def tearDown(self):
        self.home.close()

    def render(self, difficulty, trivial=False, which="work", profiles=None):
        return loop.render(self.cfg, "634", difficulty, trivial, self.resolved, profiles or self.profiles, kit_name,
                           which)

    def test_mid_task(self):
        out = self.render("mid")
        self.assertIn("| 1 | plan | `634 plan` | plan | lead |", out)
        self.assertIn("| foreman-kit:work-breakdown, foreman-kit:cross-check | done → build (build) |", out)
        self.assertIn("| 4 | review | `634 review <N>` | review | pair |", out)
        self.assertIn("| foreman-kit:tidy | done → fix |", out)  # a replaced default skill
        self.assertIn("changes → fix; approved → finalize (finalize)", out)
        self.assertIn("| pair | prompt | agent 1: sonnet | opus | `--role pair` `--disallow Edit,Write,NotebookEdit` |", out)
        self.assertIn("## Prompt for pair", out)
        self.assertNotIn("Missing skills", out)

    def test_trivial_task(self):
        out = self.render("mid", trivial=True)
        self.assertIn("(difficulty mid, trivial)", out)
        self.assertNotIn("| recheck |", out)
        self.assertIn("done → finalize (finalize)", out)
        self.assertNotIn("## Prompt for pair", out)

    def test_check_loop_for_the_foreman(self):
        out = self.render("high", which="check")
        self.assertIn("# Verification session for 634", out)
        self.assertIn("| 1 | redteam-review | `634 redteam-review` | redteam-review | redteam |", out)
        self.assertIn("changes → build (build session); approved → stop", out)
        self.assertIn("script → verify (build session)", out)
        self.assertIn("## Prompt for qa", out)

    def test_as_data(self):
        data = loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name)
        self.assertEqual([s["id"] for s in data["work"]], WORK)
        self.assertEqual([s["id"] for s in data["check"]], CHECK)
        recheck = next(s for s in data["work"] if s["id"] == "recheck")
        self.assertEqual((recheck["stage"], recheck["label"], recheck["skills"]),
                         ("review", "634 review <N>", ["foreman-kit:review"]))

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
        self.assertIn("| review | recheck | pair |", r.stdout)
        self.assertIn("if-not-trivial | if-not-trivial | if-not-trivial", r.stdout)
        r = run("loop.py", "show", "--loop", "check")
        self.assertIn("| test | test | qa |", r.stdout)
        self.assertEqual(run("loop.py", "render").returncode, 2)
        self.assertEqual(run("loop.py", "show", "--project", "bad").returncode, 2)

    def test_render_local_machine(self):
        repo = os.path.join(self.home.root, "repo")
        self.home.write("repo/.claude/skills/scenario/SKILL.md", "x")
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": repo}, "skills": {"cross-check": "scenario"}})
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "high", "--machine", "local")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| foreman-kit:work-breakdown, scenario |", r.stdout)  # the project's skill replaces cross-check
        self.assertIn("| pair | prompt | agent 1: sonnet |", r.stdout)  # high: never the lead's opus
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "local",
                "--json")
        data = json.loads(r.stdout)
        self.assertEqual([s["id"] for s in data["check"]], CHECK)
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "ghost")
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
