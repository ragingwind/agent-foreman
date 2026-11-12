#!/usr/bin/env python3
"""Status files: what each lead reports, and what the foreman reads.

A task's status file is `~/.cache/herdr-foreman/runs/<owner>-<repo>/<task>/status.jsonl`
on its machine; launch.py --status hands it to an agent as HF_STATUS_FILE.
The bundle's hooks append `heartbeat` and `turn-end` lines; the lead appends
a `start`, `end` or `progress` line for its stages and a `stop` line at a
stop point.

Usage:
  status.py path --project OWNER/REPO --task TASK
  status.py note --stage ID --event start|end|progress|stop [--round N] [--done TEXT]
                 [--next TEXT] [--blocked TEXT] [--runs JSON] [--file FILE]
  status.py read --project OWNER/REPO [--machine MACHINE] [--stall MINUTES]

`path` prints the path with `~`, for the machine to expand. `note` writes to
--file, or to HF_STATUS_FILE. `read` reads every task's status file on the
project's machines (one SSH call per remote machine) and prints, per task:
the last stage line, the last heartbeat and its agent, the minutes since the
last line, and `stalled` when that is more than --stall minutes (default: the
settings' ops.stall_minutes) and the lead is not at a stop point.

Exit codes: 2 = bad arguments, 1 = a machine could not be read.
"""
import argparse
import calendar
import json
import os
import shlex
import subprocess
import sys
import time

from config import LOCAL, NAME, REPO

RUNS = "~/.cache/herdr-foreman/runs"
EVENTS = ["start", "end", "progress", "stop"]
BEATS = ["heartbeat", "turn-end"]
TAIL = 200

# Runs on the machine: prints {task: [last lines]} for one project.
READER = """
import glob, json, os, sys
root = os.path.expanduser(sys.argv[1])
out = {}
for path in sorted(glob.glob(os.path.join(root, "*", "status.jsonl"))):
    with open(path, encoding="utf-8", errors="replace") as f:
        out[os.path.basename(os.path.dirname(path))] = f.read().splitlines()[-int(sys.argv[2]):]
print(json.dumps(out))
"""


def project_root(repo):
    return f"{RUNS}/{repo.replace('/', '-')}"


def path_for(repo, task):
    return f"{project_root(repo)}/{task}/status.jsonl"


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_time(text):
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def summarize(lines, stall_minutes, now=None):
    """One task's state from its status lines."""
    now = time.time() if now is None else now
    rows = []
    for raw in lines:
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    stage = next((r for r in reversed(rows) if r.get("event") in EVENTS), {})
    beat = next((r for r in reversed(rows) if r.get("event") in BEATS), {})
    last = parse_time(rows[-1].get("time")) if rows else None
    since = None if last is None else round((now - last) / 60, 1)
    stopped = stage.get("event") == "stop"
    return {"stage": stage.get("stage"), "stage_event": stage.get("event"), "round": stage.get("round"),
            "done": stage.get("done"), "next": stage.get("next"), "blocked": stage.get("blocked") or "",
            "last_beat": beat.get("event"), "last_beat_agent": beat.get("agent"), "minutes_since": since,
            "stopped": stopped, "stalled": not stopped and (since is None or since > stall_minutes)}


def read_machine(label, repo, saved):
    """{task: [lines]} from one machine. `saved`: herdr machines, label -> info."""
    root = project_root(repo)
    if label == LOCAL:
        argv = [sys.executable, "-c", READER, root, str(TAIL)]
    else:
        if label not in saved:
            raise ValueError(f"{label} is not a saved herdr machine")
        argv = ["ssh", "-o", "BatchMode=yes", saved[label]["target"],
                "python3 -c " + shlex.quote(READER) + " " + shlex.quote(root) + f" {TAIL}"]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{label}: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout or "{}")


def main(argv):
    ap = argparse.ArgumentParser(prog="status.py", description="herdr-foreman status files")
    ap.add_argument("command", choices=["path", "note", "read"])
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--task")
    ap.add_argument("--machine")
    ap.add_argument("--stall", type=float)
    ap.add_argument("--file")
    ap.add_argument("--stage")
    ap.add_argument("--event", choices=EVENTS)
    ap.add_argument("--round", type=int)
    ap.add_argument("--done", default="")
    ap.add_argument("--next", default="")
    ap.add_argument("--blocked", default="")
    ap.add_argument("--runs", default="[]", help="JSON list of sub-agent runs")
    args = ap.parse_args(argv)
    if args.project and not REPO.match(args.project):
        print(f"status.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2

    if args.command == "path":
        if not (args.project and args.task):
            print("status.py: path needs --project and --task", file=sys.stderr)
            return 2
        if not NAME.match(args.task):
            print(f"status.py: --task may hold letters, digits, '.', '_' and '-' only, not {args.task!r}",
                  file=sys.stderr)
            return 2
        print(path_for(args.project, args.task))
        return 0

    if args.command == "note":
        path = args.file or os.environ.get("HF_STATUS_FILE")
        if not (path and args.stage and args.event):
            print("status.py: note needs --stage, --event and a status file (--file or HF_STATUS_FILE)",
                  file=sys.stderr)
            return 2
        try:
            runs = json.loads(args.runs)
        except ValueError:
            runs = None
        if not isinstance(runs, list):
            print("status.py: --runs must be a JSON list", file=sys.stderr)
            return 2
        row = {"time": now_iso(), "stage": args.stage, "event": args.event, "round": args.round,
               "done": args.done, "next": args.next, "blocked": args.blocked, "runs": runs}
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return 0

    if not args.project:
        print("status.py: read needs --project", file=sys.stderr)
        return 2
    from config import herdr_machines, load
    cfg = load(args.project)
    stall = args.stall if args.stall is not None else cfg["ops"]["stall_minutes"]
    machines = [args.machine] if args.machine else list(cfg.get("machines", {}))
    saved = herdr_machines() if any(m != LOCAL for m in machines) else {}
    report, failed = {}, []
    for label in machines:
        try:
            tasks = read_machine(label, args.project, saved)
        except (ValueError, RuntimeError) as e:
            failed.append(str(e))
            continue
        for task, lines in tasks.items():
            report[task] = {"machine": label, **summarize(lines, stall)}
    print(json.dumps({"stall_minutes": stall, "tasks": report, "unreadable": failed}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
