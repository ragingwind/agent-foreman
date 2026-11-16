"""The default skills that ship in the plugin: each is there, names only steps
and outcomes the standard loop has, and its record shapes fit the gate."""
import os
import re
import unittest

from helpers import ROOT, TempHome

import config
import gate
import loop

KIT = os.path.join(ROOT, "plugins", "agent-foreman", "kit", "skills")


def skill(name):
    with open(os.path.join(KIT, name, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


def record(name, first_line):
    """The ````markdown block in a skill that starts with `first_line`."""
    return next(b for b in re.findall(r"````markdown\n(.*?)````", skill(name), re.S) if b.startswith(first_line))


class RealKit(unittest.TestCase):
    def test_every_default_skill_is_there(self):
        self.assertEqual(sorted(os.listdir(KIT)), sorted(loop.KIT))
        for name in loop.KIT:
            text = skill(name)
            m = re.match(r"---\nname: (\S+)\ndescription: >-\n.+?\n---\n", text, re.S)
            self.assertTrue(m, name)
            self.assertEqual(m.group(1), name)
            for section in ("## Action", "## Flow", "## Record"):
                self.assertIn(section, text, name)
            self.assertNotRegex(text, r"\b([PBVRFT][1-4]|X1)\b", name)  # step ids, not action codes

    def test_answers_are_markdown_a_no_hard_wrap_policy_accepts(self):
        """A project may post answers under a policy that allows a single newline only between list items
        (loop.py post posts the saved answer unchanged). So the answer shapes are list items, a blank line,
        and a plain Verdict line that the gate reads."""
        def wrapped(text):  # two lines in a row outside a fence where one is not a list item
            lines, bad, fenced = text.splitlines(), [], False
            for a, b in zip(lines, lines[1:]):
                fenced = fenced != a.lstrip().startswith("```")
                if not fenced and a.strip() and b.strip() and not b.lstrip().startswith("```") and not (
                        a.startswith("- ") and b.startswith("- ")):
                    bad.append((a, b))
            return bad

        for name, last in (("review", "changes"), ("redteam-review", "changes"), ("full", "fail")):
            block = re.search(r"## Record.*?\n```\n(.*?)```", skill(name), re.S).group(1)
            self.assertEqual(wrapped(block), [], name)
            self.assertEqual(gate.last_verdict(block), last, name)
            self.assertEqual(block.splitlines()[-2:], ["", f"Verdict: {last}"], name)
        self.assertIn("`- mismatch (script|environment|product): step N", skill("cross-check"))
        self.assertEqual(gate.last_verdict("- must-fix: x\n- Verdict: pass"), "")  # a list item is no verdict
        prompts = config.standard()["loop"]["prompts"]
        for role in ("review", "redteam", "qa"):
            self.assertIn("one plain line that is not a list item", prompts[role], role)
        self.assertIn("`- must-fix:`", prompts["redteam"])

    def test_steps_and_outcomes_the_skills_name_are_in_the_loop(self):
        std = config.standard()["loop"]
        steps = {s["id"]: s for w in ("work", "check") for s in std[w]}
        for name in loop.KIT:
            text = skill(name)
            for step in re.findall(r"[Ss]tep `([a-z-]+)`", text):
                self.assertIn(step, steps, f"{name}: step {step}")
            for step, outcome in re.findall(r"[Tt]he ([a-z-]+) step ends with outcome `([a-z-]+)`", text):
                self.assertIn(outcome, steps[step]["next"], f"{name}: {step} ends with {outcome}")
            for skills_of in [s for s in steps.values() if name in s.get("skills", [])]:
                self.assertRegex(text, rf"[Ss]tep `{skills_of['id']}`", f"{name} says nothing of step {skills_of['id']}")


PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
REF = re.compile(r'`([\w/.-]+\.md)` "([^"]+)"')


class Documents(unittest.TestCase):
    def test_every_section_a_document_names_exists(self):
        """A reference such as `setup.md` "4. Save" names a heading of that file."""
        for folder, _, files in os.walk(PLUGIN):
            for name in files:
                if not name.endswith(".md"):
                    continue
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    text = f.read()
                for target, heading in REF.findall(text):
                    path = next((p for p in (os.path.join(folder, target), os.path.join(PLUGIN, target),
                                             os.path.join(PLUGIN, "setup", target)) if os.path.isfile(p)), None)
                    where = os.path.relpath(os.path.join(folder, name), PLUGIN)
                    self.assertIsNotNone(path, f"{where}: no file {target}")
                    with open(path, encoding="utf-8") as f:
                        heads = [h.strip() for h in re.findall(r"^#+ (.+)$", f.read(), re.M)]
                    self.assertIn(heading, heads, f"{where}: {target} has no section {heading!r}")

    def test_the_foreman_agent_loads_its_skill_itself(self):
        with open(os.path.join(PLUGIN, "agents", "agent-foreman.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("initialPrompt", text)  # ignored for a plugin's agent: the session waits for a line
        self.assertIn("/agent-foreman:agent-foreman", text)


class RecordsMeetTheGate(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def docs(self, plan, handoff, scenario):
        for name, text in (("plan.md", plan), ("handoff.md", handoff), ("scenario.md", scenario)):
            self.home.write(f"task/{name}", text)
        return gate.check_docs({}, {"check": "docs"}, {"task_dir": os.path.join(self.home.root, "task")})

    def test_only_when_filled_in(self):
        plan = record("work-breakdown", "# Plan:")
        handoff = record("handoff", "# Handoff:")
        scenario = record("cross-check", "# Scenario:")
        ok, evidence = self.docs(plan, handoff, scenario)
        self.assertFalse(ok)
        self.assertIn("work items not done: W1", evidence)
        self.assertIn("closing verdict is not pass", evidence)  # the template is not a pass
        done = plan.replace("| todo |", "| done |")
        passed = scenario.replace("Verdict: <pass or fail>", "Verdict: pass")
        ok, evidence = self.docs(done, handoff, passed)
        self.assertIn("1 Agent block(s) with no output", evidence)  # the template's Agent block is not output
        ok, evidence = self.docs(done, handoff, passed.replace("<what the last full run printed>", "ok"))
        self.assertTrue(ok, evidence)


if __name__ == "__main__":
    unittest.main()
