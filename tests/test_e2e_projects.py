"""End to end on made-up projects of different forms (tests/e2e/README.md).

Each project is set up the way its expected setup result says
(tests/e2e/expected/<name>.json), then the real scripts run on it as the
foreman and a lead would: the skills a step finds, the task's loop, the
bundle, the launch command, the machine check, the gate, and the retro's
facts. `claude` and `gh` are fakes: no network, no model.
"""
import json
import os
import shutil
import subprocess
import unittest

from helpers import ROOT, TempHome, run
from test_gate import HANDOFF, PLAN, SCENARIO, fake_gh, pr

import config
import loop

E2E = os.path.join(ROOT, "tests", "e2e")
DENY = "--disallowedTools 'Bash(gh pr merge:*)'"
GIT = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
# `claude plugin list --json`: each --plugin-dir, as Claude Code lists one: by its manifest's name, scope session.
FAKE_CLAUDE = ("#!/usr/bin/env python3\nimport json, os, sys\na = sys.argv[1:]\n"
               "dirs = [a[i + 1] for i, x in enumerate(a) if x == '--plugin-dir']\n"
               "name = lambda d: json.load(open(os.path.join(d, '.claude-plugin', 'plugin.json')))['name']\n"
               "print(json.dumps([{'id': name(d) + '@inline', 'scope': 'session', 'enabled': True,"
               " 'installPath': d} for d in dirs]))\n")


def materialize(src, dest):
    """Copy a fixture tree. A folder named `dot-x` becomes `.x` and `.fixture`
    leaves a file's name, so the fixtures' `.claude` folders and guides stay
    out of the way of an agent working in this repository."""
    for folder, _, names in os.walk(src):
        rel = os.path.relpath(folder, src)
        parts = [] if rel == "." else ["." + p[4:] if p.startswith("dot-") else p for p in rel.split(os.sep)]
        os.makedirs(os.path.join(dest, *parts), exist_ok=True)
        for name in names:
            shutil.copy2(os.path.join(folder, name), os.path.join(dest, *parts, name.replace(".fixture", "")))
    return dest


def git(cwd, *args):
    return subprocess.run([*GIT, "-C", cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


def commit(cwd, subject, body=None, path="NOTES.txt"):
    with open(os.path.join(cwd, path), "a", encoding="utf-8") as f:
        f.write(subject + "\n")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", subject, *(["-m", body] if body else []))
    return git(cwd, "rev-parse", "HEAD")


class Projects(unittest.TestCase):
    def check(self, name):
        with open(os.path.join(E2E, "expected", name + ".json"), encoding="utf-8") as f:
            fit = json.load(f)
        lacking = [t for t in fit.get("needs", []) if shutil.which(t) is None]
        if lacking:
            self.skipTest(f"{name} needs {', '.join(lacking)}")
        home = TempHome()
        self.addCleanup(home.close)
        root = home.root
        plugins = os.path.join(root, "plugins")
        for p in os.listdir(os.path.join(E2E, "plugins")):
            materialize(os.path.join(E2E, "plugins", p), os.path.join(plugins, p))
        fit = json.loads(json.dumps(fit).replace("{plugins}", plugins))
        expect, repo = fit["expect"], f"o/{name}"
        carried = expect.get("plugins", [])

        # The person's skills, the fakes, and the project with its origin.
        cc = os.path.join(root, "cc")
        materialize(os.path.join(E2E, "user-skills"), os.path.join(cc, "skills"))
        env, _ = fake_gh(home, pr())
        with open(os.path.join(root, "bin", "claude"), "w") as f:
            f.write(FAKE_CLAUDE)
        os.chmod(os.path.join(root, "bin", "claude"), 0o755)
        env["CLAUDE_CONFIG_DIR"] = cc
        checkout = materialize(os.path.join(E2E, "projects", name), os.path.join(root, "work", name))
        origin = os.path.join(root, "origin", "o", name + ".git")  # the machine check reads o/<name> from it
        subprocess.run(["git", "init", "-q", "--bare", origin], check=True)
        git(checkout, "init", "-q", "-b", "main")
        git(checkout, "config", "user.email", "e2e@example.invalid")
        git(checkout, "config", "user.name", "e2e")
        git(checkout, "add", "-A")
        git(checkout, "commit", "-q", "-m", "add: the project")
        git(checkout, "remote", "add", "origin", origin)
        git(checkout, "push", "-q", "-u", "origin", "main")
        base = git(checkout, "rev-parse", "HEAD")  # the base branch's head, as GitHub reports it
        head = commit(checkout, "add: notes for task 1", "Refs #1")

        # The settings setup should have saved.
        home.write(f"state/agent-foreman/projects/o-{name}/project.json",
                   {"repo": repo, "machines": {"local": checkout}, **fit["settings"]})
        self.assertEqual(config.settings_problems(config.load(repo), repo=repo, project=True), [])

        # Where each step's skill comes from.
        r = run("loop.py", "skills", "--project", repo, "--machine", "local", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        listed = json.loads(r.stdout)
        found = listed["skills"]
        for skill, (source, value) in expect.get("sources", {}).items():
            self.assertEqual(found[skill]["source"], source, skill)
            self.assertIn(value, found[skill]["value"], skill)

        # The task's loop: each step's skills as the lead reads them.
        args = ["--project", repo, "--task", "1", "--difficulty", "mid", "--machine", "local", "--lead", "sonnet"]
        r = run("loop.py", "render", *args, "--base", "main", "--json", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        task_loop = json.loads(r.stdout)
        steps = {s["id"]: s["skills"] for w in ("work", "check") for s in task_loop[w]}
        for step, want in expect.get("steps", {}).items():
            self.assertEqual(steps[step], want, step)
        named = " ".join(x for skills in steps.values() for x in skills)
        for skill in expect.get("unbound", []):  # there to be bound, and bound to no step
            there = (skill in listed["project_skills"] or os.path.isfile(os.path.join(checkout, ".claude", "agents", skill + ".md"))
                     or any(os.path.isfile(os.path.join(plugins, p, "skills", skill, "SKILL.md")) for p in os.listdir(plugins)))
            self.assertTrue(there, skill)
            self.assertNotIn(skill, named)
        self.assertEqual(task_loop["gate"], fit["settings"].get("gate", []))
        missing = {line.split("missing skill: ")[1].split()[0] for line in r.stderr.splitlines()
                   if "missing skill: " in line}
        self.assertEqual(missing, set(expect.get("missing", [])))
        brief = run("loop.py", "render", *args, env=env).stdout  # the lead's, and the foreman's check loop
        tables = brief + run("loop.py", "render", *args, "--loop", "check", env=env).stdout
        for want in expect.get("steps", {}).values():
            self.assertIn(", ".join(want), tables)
        self.assertEqual("**Missing skills**" in brief, bool(missing))
        task = os.path.dirname(home.write("task/loop.json", r.stdout))

        # The bundle: a person's skill is copied; a plugin_dirs plugin is carried whole.
        r = run("bundle.py", "build", "--project", repo, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        bundle = json.loads(r.stdout)["path"]
        copied = sorted(s for s in os.listdir(os.path.join(bundle, "skills")) if s not in loop.KIT)
        self.assertEqual(copied, sorted(expect.get("copied", [])))
        with open(os.path.join(bundle, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["plugins"], carried)
        for p in carried:  # with its agents and scripts, so no machine needs it installed
            self.assertEqual(sorted(os.listdir(os.path.join(bundle, "plugins", p))),
                             sorted(os.listdir(os.path.join(plugins, p))))

        # The lead's command: never a merge, and the carried plugins whole.
        scripts = os.path.join(bundle, "scripts")
        r = run("launch.py", "sonnet", "--name", "1", "--dry-run", cwd=scripts, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(DENY, r.stdout)
        for p in carried:
            self.assertIn(f"--plugin-dir {os.path.join(bundle, 'plugins', p)}", r.stdout)
        if carried:
            shutil.rmtree(os.path.join(plugins, carried[0]))  # the person's copy is not what the agent loads
            self.assertEqual(run("launch.py", "sonnet", "--dry-run", cwd=scripts, env=env).returncode, 0)

        # The machine check.
        r = run("config.py", "check-machine", "local", checkout, "--project", repo, env=env)
        state = json.loads(r.stdout)
        self.assertEqual((r.returncode, state["problems"]), (0, []), r.stderr)

        # The lead's records, and evidence at every step: each end line names them, and the foreman checks them.
        short = git(checkout, "rev-parse", "--short", "HEAD")
        home.write("task/plan.md", PLAN.replace("abc1234", short) + "\n## Checks\n\n### Tests near the change: all\n"
                   "```\nok\n```\n\n### Smoke: it runs\n```\nok\n```\n")
        home.write("task/scenario.md", SCENARIO)
        home.write("task/handoff.md", HANDOFF)
        home.write("task/reviews/pair-1-1.json", {"result": "must-fix: none\nVerdict: approved"})
        home.write("task/reviews/pair-1-1.meta.json", {"role": "pair", "agent": "pair-1", "profile": "opus",
                                                        "head": head, "ended": "2026-11-15T02:00:00Z", "ok": True})
        work = task_loop["work"]
        rows = []
        for i, s in enumerate(work):
            outcome, to = list(s["next"].items())[-1]
            rows += [{"time": f"2026-11-15T01:{i:02d}:00Z", "stage": s["stage"], "step": s["id"], "event": "start"},
                     {"time": f"2026-11-15T01:{i:02d}:30Z", "stage": s["stage"], "step": s["id"], "event": "end",
                      "outcome": outcome, "to": to, "done": f"{', '.join(s['skills']) or s['id']}: in the task folder"}]
        home.write("task/status.jsonl", "".join(json.dumps(row) + "\n" for row in rows))
        for s in work:
            r = run("gate.py", "record", "--step", s["id"], "--task-dir", task, "--cwd", checkout)
            self.assertEqual(r.returncode, 0, (s["id"], r.stdout + r.stderr))
        with open(os.path.join(task, "plan.md"), encoding="utf-8") as f:
            honest = f.read()
        home.write("task/plan.md", honest.replace(short, "0badc0d"))  # a done row whose commit is nowhere
        r = run("gate.py", "record", "--step", "build", "--task-dir", task, "--cwd", checkout)
        self.assertEqual(r.returncode, 6, r.stdout)
        self.assertIn("W1's commit 0badc0d is not in the clone's history", r.stdout)
        home.write("task/plan.md", honest)

        # The gate, as the lead runs it in finalize: the standard checks and the project's.
        r = run("gate.py", "template", "--loop", os.path.join(task, "loop.json"), "--pr", "7")
        self.assertEqual(r.returncode, 0, r.stderr)
        gate_file = home.write("gate.json", r.stdout)

        runs = []

        def gate(at, before_ready=True, labels=None):
            view = pr(headRefOid=at, baseRefOid=base, labels=fit.get("labels", []) if labels is None else labels)
            env.update(fake_gh(home, view)[0])
            r = run("gate.py", "run", gate_file, "--task-dir", task, "--cwd", checkout,
                    *(["--before-ready"] if before_ready else []), env=env)
            runs.append(r.returncode)
            return r, json.loads(r.stdout)

        # As the lead runs it before ready: checks marked for the merge wait.
        r, report = gate(head)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        by = {c["check"]: c for c in report["checks"]}
        self.assertTrue(by["command"]["ok"], by["command"])  # the project's full tests ran in its checkout
        for check in expect["gate"]["ok"]:
            self.assertTrue(by[check]["ok"], by[check])
        for check in expect["gate"].get("warned", []):
            self.assertEqual((by[check]["ok"], by[check]["severity"]), (False, "warn"), by[check])
        at_merge = [c["name"] for c in fit["settings"].get("gate", []) if c.get("at") == "merge"]
        self.assertFalse(set(at_merge) & set(by))

        # As the foreman runs it before the merge: the red team's and QA's verdicts, and every check.
        for role, verdict in (("redteam", "approved"), ("qa", "pass")):
            home.write(f"task/reviews/{role}-1-1.json", {"result": f"Verdict: {verdict}"})
            home.write(f"task/reviews/{role}-1-1.meta.json", {"role": role, "agent": f"{role}-1", "profile": "opus",
                                                               "head": head, "ended": "2026-11-15T03:00:00Z", "ok": True})
        r, report = gate(head, before_ready=False, labels=fit.get("labels_at_merge"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        by = {c["check"]: c for c in report["checks"]}
        for check in expect["gate"].get("merge_ok", []):
            self.assertTrue(by[check]["ok"], by[check])

        failing = expect.get("gate_fail")
        if failing:
            r, report = gate(commit(checkout, failing["commit"]), before_ready=False)
            self.assertEqual(r.returncode, 6, r.stdout)
            for check in failing["blocked"]:
                self.assertIn(check, report["blocked"])
            from_base = [c for c in fit["settings"].get("gate", []) if c.get("from_base")]
            for c in from_base:  # the lead weakens the script and moves its own origin ref: still the base's script
                with open(os.path.join(checkout, c["from_base"]), "w", encoding="utf-8") as f:
                    f.write("#!/bin/sh\nexit 0\n")
                at = commit(checkout, "change: a gentler check", path="NOTES.txt")
                git(checkout, "update-ref", "refs/remotes/origin/main", at)
                r, report = gate(at, before_ready=False)
                self.assertIn(c["name"], report["blocked"])

        # The retro's facts, once the task folder is archived.
        shutil.copytree(task, os.path.join(config.project_dir(repo), "tasks", "1"))
        r = run("retro.py", "facts", "--project", repo, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        facts = json.loads(r.stdout)
        self.assertEqual(len(facts["tasks"][0]["gate_runs"]), len(runs))
        self.assertEqual(facts["steps"]["build"]["ran"], 1)
        for check in (failing or {}).get("blocked", []):
            self.assertEqual(facts["gate"][check]["blocked"], runs.count(6))


for _name in sorted(n[:-len(".json")] for n in os.listdir(os.path.join(E2E, "expected")) if n.endswith(".json")):
    setattr(Projects, "test_" + _name.replace("-", "_"), lambda self, n=_name: self.check(n))


if __name__ == "__main__":
    unittest.main()
