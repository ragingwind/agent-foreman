#!/usr/bin/env python3
"""Print the last answers of an agent session from its transcript.

Usage: transcript.py SESSION_ID [--last N] [--agent KIND] [--root DIR]

Prints the final text of each of the last N answered turns (default 1),
oldest first. Where the transcript lives and how it is read is the agent
kind's adapter (default `claude`: ~/.claude/projects/*/<SESSION_ID>.jsonl);
--root overrides that directory.

Every bundle carries it with its adapters, so it runs on the agent's machine:
  ssh <target> python3 <bundle>/scripts/transcript.py <session id>

Exit codes: 1 = no transcript for that session, 2 = bad arguments.
"""
import argparse
import re
import sys

import adapters

SESSION = re.compile(r"^[0-9A-Fa-f-]{8,64}$")


def main(argv):
    ap = argparse.ArgumentParser(prog="transcript.py")
    ap.add_argument("session_id")
    ap.add_argument("--last", type=int, default=1)
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    ap.add_argument("--root", "--projects", dest="root")
    args = ap.parse_args(argv)
    if not SESSION.match(args.session_id) or args.last < 1:
        print("transcript.py: give a session id (hex and dashes) and --last of 1 or more", file=sys.stderr)
        return 2
    try:
        answers, total = adapters.get(args.agent).last_answers(args.session_id, args.last, root=args.root)
    except adapters.NoTranscript as e:
        print(f"transcript.py: {e}", file=sys.stderr)
        return 1
    for i, text in enumerate(answers):
        if len(answers) > 1:
            print(f"--- turn {total - len(answers) + i + 1} of {total} ---")
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
