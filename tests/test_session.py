"""session.py and the plugin's hooks: a foreman started again gets the last
exchanges of the project's earlier foreman session."""
import json
import os
import subprocess
import unittest

from helpers import ROOT, TempHome, run

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")


def user(text, **extra):
    return {"type": "user", "message": {"role": "user", "content": text}, **extra}


def assistant(*blocks, **extra):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}, **extra}


def text(t):
    return {"type": "text", "text": t}


CONVERSATION = [
    {"type": "custom-title", "customTitle": "foreman acme/api"},
    user("Add a --json flag to the list command."),
    assistant({"type": "thinking", "thinking": "THINKING-NOTE"}, text("I'll check the ledger first.")),
    assistant({"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}),
    user([{"type": "tool_result", "tool_use_id": "t1", "content": "TOOL OUTPUT"}]),
    assistant(text("Started task 7 on local.")),
    user('<channel source="imessage">PING</channel>', isMeta=True),
    user("<task-notification>\n<task-id>x</task-id></task-notification>"),
    user([text("[Request interrupted by user]")]),
    user("SIDE QUESTION", isSidechain=True),
    assistant(text("SIDE ANSWER"), isSidechain=True),
    user([text("What waits on me?"), {"type": "image", "source": {}}]),
    assistant(text("Pull request 12 waits on your merge.")),
]


class Session(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.repo = os.path.join(self.home.root, "api")
        subprocess.run(["git", "init", "-q", self.repo], check=True)
        subprocess.run(["git", "-C", self.repo, "remote", "add", "origin", "git@github.com:acme/api.git"], check=True)
        self.transcript = self.write_transcript("a.jsonl", CONVERSATION)
        self.record = os.path.join(self.home.env["XDG_STATE_HOME"], "agent-foreman", "foreman", "acme-api.json")

    def tearDown(self):
        self.home.close()

    def write_transcript(self, name, entries, tail=""):
        return self.home.write(name, "\n".join(json.dumps(e) for e in entries) + "\n" + tail)

    def hook(self, event, session="A", cwd=None, transcript=None, **fields):
        data = {"session_id": session, "transcript_path": transcript or self.transcript, "cwd": cwd or self.repo,
                "hook_event_name": event, "agent_type": "agent-foreman:agent-foreman", **fields}
        data = {k: v for k, v in data.items() if v is not None}
        r = run("session.py", "stop" if event == "Stop" else "start", stdin=json.dumps(data), workdir=self.repo)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None

    def started(self, **fields):
        return self.hook("SessionStart", session="B", source="startup", **fields)

    def test_other_sessions_do_nothing(self):
        for fields in ({"agent_type": None}, {"agent_type": "Explore"}, {"agent_type": "other:agent-foreman"},
                       {"agent_id": "sub-1"}):
            self.assertIsNone(self.hook("Stop", **fields), fields)
            self.assertFalse(os.path.exists(self.record), fields)
            self.assertIsNone(self.started(**fields), fields)

    def test_each_turn_records_where_the_conversation_is(self):
        for agent in ("agent-foreman", "agent-foreman:agent-foreman"):
            self.hook("Stop", agent_type=agent)
            with open(self.record) as f:
                saved = json.load(f)
            self.assertEqual((saved["session"], saved["transcript"], saved["cwd"]), ("A", self.transcript, self.repo))
            self.assertRegex(saved["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_the_first_start_only_names_the_session(self):
        self.assertEqual(self.started(), {"hookEventName": "SessionStart", "sessionTitle": "foreman acme/api"})

    def test_a_new_start_brings_back_the_last_exchanges(self):
        self.hook("Stop")
        added = self.started()["additionalContext"]
        self.assertIn(self.transcript, added)
        self.assertIn('"Resume"', added)
        order = ["[person] Add a --json flag to the list command.", "[foreman] Started task 7 on local.",
                 "[person] What waits on me?", "[foreman] Pull request 12 waits on your merge."]
        self.assertEqual([added.index(s) for s in order], sorted(added.index(s) for s in order))
        for left_out in ("I'll check the ledger", "TOOL OUTPUT", "PING", "task-notification", "interrupted",
                         "SIDE", "THINKING-NOTE"):
            self.assertNotIn(left_out, added)

    def test_a_named_session_keeps_its_name(self):
        self.hook("Stop")
        out = self.started(session_title="mine")
        self.assertNotIn("sessionTitle", out)
        self.assertIn("additionalContext", out)

    def test_resume_and_clear_add_nothing(self):
        self.hook("Stop")
        for source in ("resume", "clear", "compact"):
            self.assertIsNone(self.hook("SessionStart", session="B", source=source), source)

    def test_a_gone_transcript_or_the_same_session_adds_nothing(self):
        self.hook("Stop")
        self.assertNotIn("additionalContext", self.hook("SessionStart", session="A", source="startup"))
        os.remove(self.transcript)
        self.assertNotIn("additionalContext", self.started())

    def test_a_cut_last_line_is_skipped(self):
        cut = self.write_transcript("cut.jsonl", CONVERSATION, tail='{"type": "user", "mess')
        self.hook("Stop", transcript=cut)
        self.assertIn("Pull request 12", self.started()["additionalContext"])

    def test_a_long_conversation_fits_and_keeps_the_latest(self):
        turns = []
        for i in range(200):
            turns += [user(f"question {i} " + "q" * 900), assistant(text(f"answer {i} " + "a" * 900))]
        turns += [user("last question"), assistant(text("LAST " + "z" * 5000))]
        self.hook("Stop", transcript=self.write_transcript("long.jsonl", turns))
        added = self.started()["additionalContext"]
        self.assertLessEqual(len(added), 10000)
        self.assertIn("[person] last question", added)
        self.assertIn("[foreman] LAST zzz", added)
        self.assertIn(" [...]", added)
        self.assertNotIn("question 0 ", added)

    def test_outside_a_checkout_the_folder_is_the_project(self):
        folder = os.path.join(self.home.root, "plain")
        os.makedirs(folder)
        self.hook("Stop", cwd=folder)
        out = self.hook("SessionStart", session="B", cwd=folder, source="startup")
        self.assertEqual(out["sessionTitle"], f"foreman {folder}")
        self.assertIn("Pull request 12", out["additionalContext"])
        self.assertFalse(os.path.exists(self.record))

    def test_a_wrong_call_is_refused(self):
        self.assertEqual(run("session.py", "save", stdin="{}").returncode, 2)


class Hooks(unittest.TestCase):
    def test_the_plugin_hooks_run_session_py(self):
        with open(os.path.join(PLUGIN, "hooks", "hooks.json")) as f:
            hooks = json.load(f)["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "Stop"})
        self.assertEqual(hooks["SessionStart"][0]["matcher"], "startup")
        for event, arg in (("SessionStart", "start"), ("Stop", "stop")):
            command = hooks[event][0]["hooks"][0]["command"]
            self.assertEqual(command, f'python3 "${{CLAUDE_PLUGIN_ROOT}}/scripts/session.py" {arg}')
        self.assertTrue(os.path.isfile(os.path.join(PLUGIN, "scripts", "session.py")))


if __name__ == "__main__":
    unittest.main()
