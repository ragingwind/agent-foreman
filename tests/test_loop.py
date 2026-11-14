import copy
import json
import os
import re
import subprocess
import unittest

from helpers import SCRIPTS, TempHome, run, task_loop

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

    def test_success_path_must_reach_stop(self):
        base = {"roles": {"r": {"mode": "prompt"}}, "prompts": {}}
        loops = dict(base, work=[stage("a", nxt={"done": "b"}), stage("b", nxt={"fail": "a", "done": "a"})])
        self.assertIn("loop: work: the success path from a (each step's last outcome) does not reach stop",
                      loop.validate_loop(loops))
        back = dict(base, work=[stage("a")], check=[stage("x", actor="r", nxt={"pass": "a"})])
        self.assertIn("loop: check: the success path from x (each step's last outcome) does not reach stop",
                      loop.validate_loop(back))
        self.assertEqual(loop.success_problems(config.standard()["loop"]), [])

    def test_verdict_words_are_outcomes(self):
        """What a judging role may answer is an outcome of each step it runs,
        and its passing verdict is the step's success path."""
        std = config.standard()["loop"]
        for which in ("work", "check"):
            for s in std[which]:
                role = std["roles"].get(s["actor"])
                if not role:
                    continue
                words = set(re.findall(r"`Verdict: (\w+)`", std["prompts"][role["prompt"]]))
                if s["id"] == "review":  # the first pair review goes on to simplify whatever it says
                    self.assertEqual(list(s["next"]), ["done"])
                    continue
                self.assertEqual(set(s["next"]) & words, words, s["id"])
                self.assertEqual(list(s["next"])[-1], role["accept"][0], s["id"])

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
        self.assertIn("| pair | prompt | agent 1: sonnet | opus |", out)
        self.assertIn("`loop.py prompt --step <step>`", out)
        self.assertNotIn("Missing skills", out)

    def test_trivial_task(self):
        out = self.render("mid", trivial=True)
        self.assertIn("(difficulty mid, trivial)", out)
        self.assertNotIn("| recheck |", out)
        self.assertIn("done → finalize (finalize)", out)
        self.assertNotIn("| pair |", out)

    def test_check_loop_for_the_foreman(self):
        out = self.render("high", which="check")
        self.assertIn("# Verification session for 634", out)
        self.assertIn("| 1 | redteam-review | `634 redteam-review` | redteam-review | redteam |", out)
        self.assertIn("changes → build (build session); approved → stop", out)
        self.assertIn("script → verify (build session)", out)
        self.assertIn("| qa | prompt | agent 1: opus |", out)

    def test_as_data(self):
        data = loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                            self.profiles)
        self.assertEqual([s["id"] for s in data["work"]], WORK)
        self.assertEqual([s["id"] for s in data["check"]], CHECK)
        self.assertEqual((data["repo"], data["base"], data["lead_profile"], data["max_lines"]), ("o/r", "main", "sonnet", 400))
        recheck = next(s for s in data["work"] if s["id"] == "recheck")
        self.assertEqual((recheck["stage"], recheck["label"], recheck["actor"], recheck["skills"], recheck["next"]),
                         ("review", "634 review <N>", "pair", ["foreman-kit:review"],
                          {"changes": "fix", "approved": "finalize"}))
        self.assertTrue(all(s["does"] for s in data["work"] + data["check"]))
        self.assertEqual(set(data["roles"]), {"pair", "redteam", "qa"})
        self.assertEqual((data["roles"]["qa"]["accept"], data["roles"]["qa"]["profiles"]), (["pass"], ["opus"]))
        self.assertIn("<full test command>", data["roles"]["qa"]["prompt"])
        trivial = loop.as_data(self.cfg, "634", "mid", True, self.resolved, kit_name, "o/r", "main", "sonnet",
                               self.profiles)
        self.assertEqual([s["id"] for s in trivial["work"]], ["plan", "build", "verify", "finalize"])
        self.assertEqual(next(s for s in trivial["work"] if s["id"] == "verify")["next"]["done"], "finalize")
        self.assertEqual(set(trivial["roles"]), {"redteam", "qa"})

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
        self.assertIn("| pair | prompt | agent 1: sonnet | - |", r.stdout)  # high: never the lead's opus
        self.assertNotIn("opus |", r.stdout.split("| Role |")[1])
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "high", "--machine", "local",
                "--lead", "sonnet")  # the lead fell back to sonnet
        self.assertIn("| pair | prompt | agent 1: opus | - |", r.stdout)
        args = ["loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "local",
                "--json"]
        self.assertEqual(run(*args).returncode, 2)  # needs --base
        data = json.loads(run(*args, "--base", "main", "--trivial").stdout)
        self.assertEqual(([s["id"] for s in data["check"]], data["trivial"], data["base"], data["lead_profile"]),
                         (CHECK, True, "main", "haiku"))
        self.assertEqual(run(*args, "--base", "main", "--lead", "ghost").returncode, 2)
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "ghost")
        self.assertEqual(r.returncode, 3)


def git_clone(home, name="clone"):
    path = os.path.join(home.root, name)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    return path, subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


class Prompt(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.clone, self.head = git_clone(self.home)

    def tearDown(self):
        self.home.close()

    def prompt(self, *args, env=None, workdir=None):
        return run("loop.py", "prompt", *args, env=env, workdir=workdir or self.clone)

    def test_writes_the_filled_prompt_and_prints_the_commands(self):
        r = self.prompt("--step", "review", env={"AF_TASK_DIR": self.task})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["agent"], out["prompt"], out["out"]),
                         ("pair-1", os.path.join(self.task, "reviews", "pair-1-1.prompt.md"),
                          os.path.join(self.task, "reviews", "pair-1-1.json")))
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertNotRegex(text, r"<[a-z ]+>")  # every placeholder is filled in
        for words in ("task 7 of o/r", "skill foreman-kit:review", f"Your clone is at {self.head}",
                      f"The task folder is {self.task}", "Review the diff from origin/main to HEAD"):
            self.assertIn(words, text)
        launch = os.path.join(SCRIPTS, "launch.py")
        self.assertEqual(out["commands"][0].split(), [
            "python3", launch, "opus", "--print", "--role", "pair", "--name", "pair-1", "--task-dir", self.task,
            "--prompt-file", out["prompt"], "--out", out["out"], "--disallow", "Edit,Write,NotebookEdit"])
        self.assertEqual(len(out["commands"]), 1)  # the mid and high tiers hold sonnet and opus; sonnet is the lead
        again = json.loads(self.prompt("--step", "review", "--task-dir", self.task).stdout)
        self.assertEqual(os.path.basename(again["prompt"]), "pair-1-2.prompt.md")  # never over an earlier run

    def test_recheck_reviews_only_what_changed_since_the_last_answer(self):
        r = self.prompt("--step", "recheck", "--task-dir", self.task)
        self.assertEqual(r.returncode, 2)
        self.assertIn("pair-1 has no earlier answer to check against; run step review first", r.stderr)
        self.home.write("task/reviews/pair-1-1.json", {"result": "Verdict: changes"})
        self.home.write("task/reviews/pair-1-1.meta.json", {"role": "pair", "agent": "pair-1", "head": "abc1234",
                                                           "ok": True, "ended": "2026-11-14T01:00:00.000000Z"})
        out = json.loads(self.prompt("--step", "recheck", "--task-dir", self.task).stdout)
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertIn("Review the diff from abc1234 to HEAD: only the fixes and the clean-up since your last review, "
                      f"whose answer is {os.path.join(self.task, 'reviews', 'pair-1-1.json')}", text)

    def test_check_roles_and_a_second_agent(self):
        out = json.loads(self.prompt("--step", "test", "--task-dir", self.task).stdout)
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertIn("full tests: none is set; write `not run: no full test command`", text)
        self.assertIn("Trivial task: no.", text)
        self.assertIn("skills foreman-kit:full, foreman-kit:cross-check say", text)
        self.home.write("task/loop.json", task_loop(difficulty="low"))  # redteam and qa: sonnet, then opus
        out = json.loads(self.prompt("--step", "redteam-review", "--task-dir", self.task, "--agent", "redteam-2").stdout)
        self.assertEqual([c.split()[2] for c in out["commands"]], ["opus", "sonnet"])  # agent 2 starts on the next

    def test_refusals(self):
        for args, words in ((["--step", "build"], "done by the lead, not by a role agent"),
                            (["--step", "nope"], "step 'nope' is not in this task's loop"),
                            (["--step", "review", "--agent", "../x"], "--agent may hold"),
                            (["--step", "review", "--task-dir", os.path.join(self.home.root, "none")], "no readable loop.json"),
                            (["--step", "review", "--task-dir", ""], "needs --step and a task folder")):
            r = self.prompt(*args, **({} if "--task-dir" in args else {"env": {"AF_TASK_DIR": self.task}}))
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(words, r.stderr)
        r = self.prompt("--step", "review", "--task-dir", self.task, workdir=self.home.root)
        self.assertIn("not a git checkout", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.task, "reviews")))


if __name__ == "__main__":
    unittest.main()
