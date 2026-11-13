#!/usr/bin/env python3
"""Hook command: append a heartbeat to the agent's status file.

The bundle's hooks run it after every tool call (`post`) and at the end of
every turn (`stop`). It writes only when launch.py gave the agent a status
file (AF_STATUS_FILE): at most one `heartbeat` line a minute, and a
`turn-end` line at every turn's end. It never fails the agent's turn: any
error is swallowed and nothing is printed.
"""
import json
import os
import sys
import time

QUIET_SECONDS = 60


def line(event, data):
    return json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event,
                       "agent": os.environ.get("AF_AGENT", ""), "tool": data.get("tool_name")}) + "\n"


def main(argv):
    if not os.environ.get("AF_STATUS_FILE"):
        return 0
    path = os.path.expanduser(os.environ["AF_STATUS_FILE"])
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    kind = argv[0] if argv else "post"
    if kind == "post" and os.path.exists(path) and time.time() - os.path.getmtime(path) < QUIET_SECONDS:
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line("turn-end" if kind == "stop" else "heartbeat", data))
    return 0


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:  # a heartbeat must never break the agent
        pass
    sys.exit(0)
