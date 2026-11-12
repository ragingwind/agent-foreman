#!/usr/bin/env python3
"""The project's log: every event, instruction, report and decision, one
JSON line each, appended and never rewritten.

Usage:
  log.py add --project OWNER/REPO --event EVENT [--task TASK] [--text TEXT] [--data JSON]
  log.py tail --project OWNER/REPO [-n N] [--event EVENT] [--task TASK]

Events are free words such as `brief`, `launch`, `prompt`, `report`,
`decision`, `difficulty`, `gate`, `merge`, `cleanup`, `stall`. Put no secret
value in --text or --data. Exit code 2 = bad arguments.
"""
import argparse
import json
import os
import sys
import time

from config import REPO, log_path


def add(repo, event, task="", text="", data=None):
    row = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, "task": task,
           "text": text, "data": data or {}}
    path = log_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def tail(repo, n=30, event=None, task=None):
    path = log_path(repo)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if (event is None or row.get("event") == event) and (task is None or row.get("task") == task):
                rows.append(row)
    return rows[-n:]


def main(argv):
    ap = argparse.ArgumentParser(prog="log.py", description="herdr-foreman project log")
    ap.add_argument("command", choices=["add", "tail"])
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--event")
    ap.add_argument("--task", default=None)
    ap.add_argument("--text", default="")
    ap.add_argument("--data", default="{}")
    ap.add_argument("-n", type=int, default=30)
    args = ap.parse_args(argv)
    if not REPO.match(args.project):
        print(f"log.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2
    if args.command == "add":
        if not args.event:
            print("log.py: add needs --event", file=sys.stderr)
            return 2
        try:
            data = json.loads(args.data)
        except ValueError:
            print("log.py: --data must be JSON", file=sys.stderr)
            return 2
        print(json.dumps(add(args.project, args.event, args.task or "", args.text, data), ensure_ascii=False))
        return 0
    for row in tail(args.project, args.n, args.event, args.task):
        print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
