"""ARCHITECTURE.md's pictures against the code: the work and check loops
(Mermaid) against the standard loop, the picture of who does what against
the manage loop and the roles, and the picture of how a step moves against
what `status.py note` does."""
import json
import os
import re
import unittest

from helpers import ROOT, TempHome, run, task_loop

import config
import loop
import status

DOC = os.path.join(ROOT, "plugins", "agent-foreman", "ARCHITECTURE.md")
EDGE = re.compile(r"^\s*(\w+)\s*-->\|([\w-]+)\|\s*(\w+)\s*$", re.M)
NODE = re.compile(r'^\s*(\w+)\["([^"]*)"\]\s*$', re.M)


def doc():
    with open(DOC, encoding="utf-8") as f:
        return f.read()


def block(fence, marker):
    """The one block fenced as `fence` that holds `marker`."""
    found = [b for b in re.findall(rf"```{fence}\n(.*?)```", doc(), re.S) if marker in b]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} ```{fence} blocks hold {marker!r} in ARCHITECTURE.md")
    return found[0]


def step_id(node):
    """A node's step id: `redteam_review` is redteam-review; `stop` and
    `stop_<anything>` are stop."""
    return "stop" if re.fullmatch(r"stop(_\w+)?", node) else node.replace("_", "-")


def drawn(name):
    """A loop's Mermaid picture: its outcome edges {(step, outcome, to)}, each
    node's label lines {step: [lines]}, and the steps drawn as trivial-skipped."""
    text = block("mermaid", f"%% loop: {name}")
    edges = {(step_id(a), outcome, step_id(b)) for a, outcome, b in EDGE.findall(text)}
    labels = {step_id(n): label.split("<br/>") for n, label in NODE.findall(text)}
    m = re.search(r"^\s*class ([\w,]+) trivial\s*$", text, re.M)
    skipped = {step_id(n) for n in m.group(1).split(",")} if m else set()
    return edges, labels, skipped


class LoopPictures(unittest.TestCase):
    def setUp(self):
        self.std = config.standard()["loop"]

    def check_loop(self, name):
        edges, labels, _ = drawn(name)
        steps = self.std[name]
        self.assertEqual(edges, {(s["id"], k, v) for s in steps for k, v in s["next"].items()})
        for s in steps:
            self.assertEqual(labels.get(s["id"]), [s["id"], s["actor"]], f"node {s['id']}")

    def test_work_loop(self):
        self.check_loop("work")

    def test_check_loop(self):
        self.check_loop("check")

    def test_trivial_steps(self):
        ids = {s["id"] for s in self.std["work"]}
        skipped = {d: ids - {s["id"] for s in loop.plan(self.std, d, trivial=True)} for d in loop.LEVELS}
        self.assertEqual(len({frozenset(v) for v in skipped.values()}), 1, skipped)  # one picture fits all
        self.assertEqual(drawn("work")[2], skipped["mid"])


class WhoDoesWhat(unittest.TestCase):
    def test_manage_steps_in_order(self):
        text, at = block("text", "FOREMAN"), 0
        for s in config.standard()["loop"]["manage"]:
            m = re.compile(rf"\b{re.escape(s['id'])}\b").search(text, at)
            self.assertIsNotNone(m, f"manage step {s['id']} is not drawn after the one before it")
            at = m.end()

    def test_prompt_roles(self):
        text = block("text", "FOREMAN").replace(" ", "")
        for name, role in config.standard()["loop"]["roles"].items():
            if role.get("mode") == "prompt":
                self.assertIn(name.upper().replace("-", ""), text, name)


class StepPicture(unittest.TestCase):
    """What the picture says `status.py note` does, done for real."""

    def setUp(self):
        self.home = TempHome()
        self.text = block("text", "status.py note")
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

    def test_a_right_outcome(self):
        self.assertIn('prints "next: Y"', self.text)
        for outcome, to in self.verify["next"].items():
            r = self.note("--event", "end", "--outcome", outcome)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith(f"next: {to}"), r.stdout)
            self.assertEqual((self.rows()[-1]["outcome"], self.rows()[-1]["to"]), (outcome, to))
        finalize = next(s for s in task_loop()["work"] if s["id"] == "finalize")
        r = run("status.py", "note", "--file", self.status, "--stage", finalize["stage"], "--step", "finalize",
                "--event", "end", "--outcome", "done")
        self.assertIn("(Y = stop: a stop point)", self.text)
        self.assertTrue(r.stdout.startswith("next: stop"), r.stdout)


if __name__ == "__main__":
    unittest.main()
