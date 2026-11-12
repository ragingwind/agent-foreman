import json
import unittest

from helpers import TempHome, run

SID = "43183aac-9bea-4a75-a187-3d86a4639c28"


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(*blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "message": {"role": "assistant", "content": list(blocks)}}


def text(t):
    return {"type": "text", "text": t}


class Transcript(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        entries = [
            user("first prompt"),
            assistant(text("first answer")),
            user("second prompt"),
            assistant(text("working on it"), {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}),
            {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}},
            {"type": "user", "isMeta": True, "message": {"content": "caveat"}},
            assistant(text("subagent text"), sidechain=True),
            assistant(text("L1\nL2\nREPORT: done — all good")),
        ]
        lines = "\n".join(json.dumps(e) for e in entries) + "\nnot json\n"
        self.home.write(f"projects/-home-x-repo/{SID}.jsonl", lines)
        self.projects = f"{self.home.root}/projects"

    def tearDown(self):
        self.home.close()

    def test_last_answer_whole(self):
        r = run("transcript.py", SID, "--projects", self.projects)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "L1\nL2\nREPORT: done — all good\n")

    def test_last_two_turns(self):
        r = run("transcript.py", SID, "--last", "2", "--projects", self.projects)
        self.assertEqual(r.stdout.splitlines(), ["--- turn 1 of 2 ---", "first answer", "--- turn 2 of 2 ---",
                                                 "L1", "L2", "REPORT: done — all good"])

    def test_missing_and_bad_ids(self):
        self.assertEqual(run("transcript.py", "deadbeef-0000", "--projects", self.projects).returncode, 1)
        self.assertEqual(run("transcript.py", "../../etc", "--projects", self.projects).returncode, 2)
        self.assertEqual(run("transcript.py", SID, "--last", "0", "--projects", self.projects).returncode, 2)


if __name__ == "__main__":
    unittest.main()
