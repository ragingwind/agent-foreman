"""ARCHITECTURE.md's pictures against the code: the work and check loops,
drawn as sequences with their outcomes listed under them, against the
standard loop; the picture of who does what against the manage loop and the
roles, and README.md's copy of it; and the picture of how a step moves
against what `status.py note` does. Every picture is a ```text block."""
import json
import os
import re
import unittest

from helpers import ROOT, TempHome, run, task_loop

import config
import loop
import status

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
DOC = os.path.join(PLUGIN, "ARCHITECTURE.md")
README = os.path.join(PLUGIN, "README.md")
EDGE = re.compile(r"([a-z][a-z-]*) ─([a-z-]+)─▶ ([a-z][a-z-]*)")
SENT = re.compile(r"^  │ ([a-z][a-z-]*) {2,}", re.M)  # the line a step starts on in a sequence


def block(marker, path=DOC):
    """The one ```text block of the file that holds `marker`."""
    with open(path, encoding="utf-8") as f:
        found = [b for b in re.findall(r"```text\n(.*?)```", f.read(), re.S) if marker in b]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} ```text blocks hold {marker!r} in {os.path.basename(path)}")
    return found[0]


def drawn(name):
    """A loop's picture: the steps in the order the sequence starts them, the
    outcome edges listed under it {(step, outcome, to)}, each step's actor,
    and the steps a trivial task skips."""
    sequence, _, listed = block(f"{name.upper()} LOOP").partition(" outcomes:")
    actors = {}
    for part in re.search(r"^ actors: (.*)$", listed, re.M).group(1).split(" · "):
        who, _, steps = part.partition(" = ")
        actors.update({s: who for s in steps.split(", ")})
    m = re.search(r"^ a trivial task skips: (.*)$", listed, re.M)
    return SENT.findall(sequence), set(EDGE.findall(listed)), actors, set(m.group(1).split(", ")) if m else set()


class LoopPictures(unittest.TestCase):
    def setUp(self):
        self.std = config.standard()["loop"]

    def check_loop(self, name):
        order, edges, actors, _ = drawn(name)
        steps = self.std[name]
        self.assertEqual(order, [s["id"] for s in steps])
        self.assertEqual(edges, {(s["id"], k, v) for s in steps for k, v in s["next"].items()})
        self.assertEqual(actors, {s["id"]: s["actor"] for s in steps})

    def test_work_loop(self):
        self.check_loop("work")

    def test_check_loop(self):
        self.check_loop("check")

    def test_trivial_steps(self):
        ran = lambda d, trivial: {s["id"] for s in loop.plan(self.std, d, trivial=trivial)}
        skipped = {d: ran(d, False) - ran(d, True) for d in loop.LEVELS}
        self.assertEqual(len({frozenset(v) for v in skipped.values()}), 1, skipped)  # one picture fits all
        self.assertEqual(drawn("work")[3], skipped["mid"])

    def test_difficulty_steps(self):
        ids = {s["id"] for s in self.std["work"]}
        listed = set(re.search(r"^ low and mid skip: (.*)$", block("WORK LOOP"), re.M).group(1).split(", "))
        for d in ("low", "mid"):
            self.assertEqual(ids - {s["id"] for s in loop.plan(self.std, d)}, listed)
        self.assertEqual({s["id"] for s in loop.plan(self.std, "high")}, ids)


class WhoDoesWhat(unittest.TestCase):
    def test_manage_steps_in_order(self):
        text, at = block(" PERSON "), 0
        for s in config.standard()["loop"]["manage"]:
            m = re.compile(rf"\b{re.escape(s['id'])}\b").search(text, at)
            self.assertIsNotNone(m, f"manage step {s['id']} is not drawn after the one before it")
            at = m.end()

    def test_readme_shows_the_same_picture(self):
        self.assertEqual(block(" PERSON ", README), block(" PERSON "))

    def test_prompt_roles(self):
        text = block(" PERSON ").replace(" ", "")
        for name, role in config.standard()["loop"]["roles"].items():
            if role.get("mode") == "prompt":
                self.assertIn(name.upper().replace("-", ""), text, name)


class StepPicture(unittest.TestCase):
    """What the picture says `status.py note` does, done for real."""

    def setUp(self):
        self.home = TempHome()
        self.text = block("the agent")
        data = task_loop()
        self.status = self.home.write("task/status.jsonl", "")
        self.home.write("task/loop.json", data)
        self.verify = next(s for s in data["work"] if s["id"] == "verify")

    def tearDown(self):
        self.home.close()

    def note(self, *args):
        return run("status.py", "note", "--file", self.status, "--stage", self.verify["stage"], "--step", "verify",
                   *args)

    def rows(self):
        with open(self.status) as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_flags_and_events_are_status_py_s(self):
        usage = run("status.py", "--help").stdout
        for flag in set(re.findall(r"--[a-z]+", self.text)):
            self.assertIn(flag, usage)
        for event in re.findall(r"--event (\w+)", self.text):
            self.assertIn(event, status.EVENTS)

    def test_a_wrong_outcome(self):
        code = int(re.search(r"exit (\d+), nothing written", self.text).group(1))
        r = self.note("--event", "end", "--outcome", "nope")
        self.assertEqual(r.returncode, code, r.stderr)
        self.assertEqual(self.rows(), [])

    def test_an_end_without_evidence(self):
        self.assertIn("--done holds the evidence", self.text)
        r = self.note("--event", "end", "--outcome", "done")
        self.assertEqual(r.returncode, 2)
        self.assertIn("needs --done", r.stderr)
        self.assertEqual(self.rows(), [])

    def test_a_right_outcome(self):
        self.assertIn('prints "next: Y"', self.text)
        for outcome, to in self.verify["next"].items():
            r = self.note("--event", "end", "--outcome", outcome, "--done", "unit: plan.md Checks 2 entries")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith(f"next: {to}"), r.stdout)
            self.assertEqual((self.rows()[-1]["outcome"], self.rows()[-1]["to"]), (outcome, to))
        finalize = next(s for s in task_loop()["work"] if s["id"] == "finalize")
        r = run("status.py", "note", "--file", self.status, "--stage", finalize["stage"], "--step", "finalize",
                "--event", "end", "--outcome", "done", "--done", "handoff: handoff.md; pull request #7 ready")
        self.assertIn("(Y = stop: a stop point)", self.text)
        self.assertTrue(r.stdout.startswith("next: stop"), r.stdout)


if __name__ == "__main__":
    unittest.main()
