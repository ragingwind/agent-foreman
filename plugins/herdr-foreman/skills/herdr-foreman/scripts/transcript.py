#!/usr/bin/env python3
"""Print the last answers of a Claude Code session from its transcript.

Usage: transcript.py SESSION_ID [--last N] [--projects DIR]

Finds <projects>/*/<SESSION_ID>.jsonl (default ~/.claude/projects, or
$CLAUDE_CONFIG_DIR/projects) and prints the final text of each of the last N
turns (default 1), oldest first. A turn starts at a typed prompt; tool
results and meta entries do not start one. Subagent entries are skipped.

It imports nothing from herdr-foreman, so it runs on any machine:
  ssh <target> python3 <bundle>/scripts/transcript.py <session id>

Exit codes: 1 = no transcript for that session, 2 = bad arguments.
"""
import argparse
import glob
import json
import os
import re
import sys

SESSION = re.compile(r"^[0-9A-Fa-f-]{8,64}$")


def find(session_id, projects):
    hits = glob.glob(os.path.join(projects, "*", f"{session_id}.jsonl"))
    return max(hits, key=os.path.getmtime) if hits else None


def _starts_turn(entry):
    if entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return any(b.get("type") == "text" for b in content if isinstance(b, dict)) and \
            not any(b.get("type") == "tool_result" for b in content if isinstance(b, dict))
    return False


def turns(lines):
    """The assistant text blocks of each turn, as a list of lists."""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("isSidechain"):
            continue
        if entry.get("type") == "user" and _starts_turn(entry):
            out.append([])
        elif entry.get("type") == "assistant":
            for block in entry.get("message", {}).get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                    if not out:
                        out.append([])
                    out[-1].append(block["text"])
    return out


def main(argv):
    ap = argparse.ArgumentParser(prog="transcript.py")
    ap.add_argument("session_id")
    ap.add_argument("--last", type=int, default=1)
    ap.add_argument("--projects")
    args = ap.parse_args(argv)
    if not SESSION.match(args.session_id) or args.last < 1:
        print("transcript.py: give a session id (hex and dashes) and --last of 1 or more", file=sys.stderr)
        return 2
    projects = args.projects or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "projects")
    path = find(args.session_id, projects)
    if not path:
        print(f"transcript.py: no transcript for session {args.session_id} under {projects}", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as f:
        answered = [t for t in turns(f) if t]
    picked = answered[-args.last:]
    for i, texts in enumerate(picked):
        if len(picked) > 1:
            print(f"--- turn {len(answered) - len(picked) + i + 1} of {len(answered)} ---")
        print(texts[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
