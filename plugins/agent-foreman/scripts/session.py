#!/usr/bin/env python3
"""The foreman's place across sessions, kept by the plugin's hooks
(hooks/hooks.json), so a foreman started again picks up where the last one
of the project stopped.

  stop   (Stop hook, at the end of each turn) records where the foreman's
         conversation is: its session id, transcript, folder and time, in
         <state>/foreman/<owner>-<repo>.json. A session that never finishes a
         turn records nothing, so it does not hide the one before it.
  start  (SessionStart hook, a new session only) adds the earlier foreman
         session's last exchanges to the new one, oldest first, and the path
         of its whole conversation; it names the session `foreman <project>`
         when it has no name.

Both read the hook's JSON on stdin and act only in a session started with
`claude --agent agent-foreman`, never in a subagent inside it. The project is
the `owner/repo` of the folder's git origin; outside a checkout, the folder.

Usage:
  session.py stop|start < hook-input.json
"""
import datetime
import json
import os
import re
import subprocess
import sys

from config import state_dir, write_json

AGENT = {"agent-foreman", "agent-foreman:agent-foreman"}  # as a plugin agent, with the plugin's name first
CONTEXT_MAX = 9000  # Claude Code moves a hook's added context over 10,000 characters to a file
MESSAGE_MAX = 1500
SKIP = ("<task-notification", "<command-", "<local-command", "<system-reminder", "[Request interrupted",
        "This session is being continued from a previous conversation")  # notices, not the person


def project(cwd):
    r = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return m.group(1) if m else os.path.abspath(cwd)


def record_path(name):
    return os.path.join(state_dir(), "foreman", name.strip("/").replace("/", "-") + ".json")


def person_text(entry):
    """What the person typed, or None for tool results, notices and meta lines."""
    if entry.get("isMeta"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
    text = (content or "").strip()
    return None if not text or text.startswith(SKIP) else text


def exchanges(transcript):
    """[(person, foreman's last answer)] per turn, from a transcript file."""
    turns = []
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:  # a line cut off by the session's end
                continue
            if entry.get("isSidechain") or entry.get("type") not in ("user", "assistant"):
                continue
            if entry["type"] == "user":
                text = person_text(entry)
                if text:
                    turns.append([text, ""])
            elif turns:
                text = "\n".join(b.get("text", "") for b in (entry.get("message") or {}).get("content") or []
                                 if b.get("type") == "text").strip()
                if text:
                    turns[-1][1] = text
    return turns


def cut(text):
    return text if len(text) <= MESSAGE_MAX else text[:MESSAGE_MAX] + " [...]"


def context(saved, name):
    head = (f"agent-foreman: the earlier foreman session of {name} (session {saved['session']}, last turn "
            f"{saved['at']}, in {saved['cwd']}) has ended. Its last exchanges follow, oldest first; the whole "
            f"conversation is {saved['transcript']}. Follow the skill's \"Resume\" before the person's request.")
    lines, size = [], len(head)
    for person, foreman in reversed(exchanges(saved["transcript"])):
        part = f"\n\n[person] {cut(person)}" + (f"\n\n[foreman] {cut(foreman)}" if foreman else "")
        if size + len(part) > CONTEXT_MAX:
            break
        lines.insert(0, part)
        size += len(part)
    return head + "".join(lines)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("stop", "start"):
        print(__doc__, file=sys.stderr)
        return 2
    data = json.load(sys.stdin)
    if data.get("agent_type") not in AGENT or data.get("agent_id"):
        return 0
    cwd = data.get("cwd") or os.getcwd()
    name = project(cwd)
    path = record_path(name)
    if sys.argv[1] == "stop":
        write_json(path, {"session": data["session_id"], "transcript": data["transcript_path"], "cwd": cwd,
                          "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return 0
    if data.get("source") != "startup":
        return 0
    out = {"hookEventName": "SessionStart"}
    if not data.get("session_title"):
        out["sessionTitle"] = f"foreman {name}"
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except FileNotFoundError:
        saved = None
    if saved and saved["session"] != data["session_id"] and os.path.isfile(saved["transcript"]):
        out["additionalContext"] = context(saved, name)
    if len(out) > 1:
        print(json.dumps({"hookSpecificOutput": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
