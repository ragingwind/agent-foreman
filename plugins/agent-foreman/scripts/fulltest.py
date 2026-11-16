#!/usr/bin/env python3
"""Run the project's full test command one at a time on a machine, and only
with enough free disk.

Usage: fulltest.py [--min-free-gb N] [--lock FILE] -- COMMAND

The gate (the `command` check for `tests.full`) and QA (the `<full test
command>` that `loop.py prompt` fills in) run the full tests through this
file. Full builds of several tasks at once can fill a machine's disk, so a
run first takes a lock on this machine (--lock, default
`~/.cache/agent-foreman/locks/full-test.lock`, under $XDG_CACHE_HOME when it
is set). While another run holds it, this prints who holds it and waits.
The lock goes with the process, also when the process is killed.

With the lock held, it checks the free space on the disk of the working
directory. Under --min-free-gb (the settings' ops.disk_min_free_gb), it does
not run the command. Otherwise it runs COMMAND in the shell, in the working
directory, and exits with the command's code. One COMMAND argument is the
whole command; several are joined with spaces.

Exit codes: the command's (128 + N when signal N ended it), 75 = not run:
the disk is under the floor, 2 = bad arguments.
"""
import argparse
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time

from config import cache_dir

EXIT_LOW_DISK = 75


def free_gb(path):
    return round(shutil.disk_usage(path).free / 1024 ** 3, 1)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the full test command under a per-machine lock.")
    parser.add_argument("--min-free-gb", type=float, default=0, help="do not run under this much free disk")
    parser.add_argument("--lock", default=os.path.join(cache_dir(), "locks", "full-test.lock"),
                        help="the lock file")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    words = args.command[1:] if args.command[:1] == ["--"] else args.command
    command = " ".join(words).strip()
    if not command:
        print("fulltest.py: no command; usage: fulltest.py [--min-free-gb N] -- COMMAND", file=sys.stderr)
        return 2
    if args.min_free_gb < 0:
        print("fulltest.py: --min-free-gb must be 0 or more", file=sys.stderr)
        return 2
    path = os.path.expanduser(args.lock)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            holder = lock.read().strip() or "another run"
            print(f"fulltest.py: waiting for the full-test lock on this machine, held by {holder}",
                  file=sys.stderr, flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
        lock.seek(0)
        lock.truncate()
        lock.write(json.dumps({"pid": os.getpid(), "cwd": os.getcwd(),
                               "task": os.environ.get("AF_TASK") or os.environ.get("AF_TASK_DIR") or "",
                               "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}))
        lock.flush()
        free = free_gb(os.getcwd())
        if free < args.min_free_gb:
            print(f"fulltest.py: not run: {free} GB free on the disk of {os.getcwd()}, under the floor of "
                  f"{args.min_free_gb:g} GB", file=sys.stderr)
            return EXIT_LOW_DISK
        code = subprocess.run(command, shell=True).returncode
    return 128 - code if code < 0 else code


if __name__ == "__main__":
    sys.exit(main())
