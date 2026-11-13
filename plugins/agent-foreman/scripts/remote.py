#!/usr/bin/env python3
"""Run a command on a project machine inside that machine's login shell.

Usage: remote.py MACHINE [--cwd DIR] -- COMMAND [ARG...]

MACHINE is a saved herdr machine label (its SSH target is used) or `local`.
A plain `ssh <target> '<command>'` runs without the login shell's setup, so
PATH and the gateways' token variables are missing there (checked on two
Ubuntu machines with zsh on 2026-11-13). This runs
`exec "$SHELL" -lic '<command>'` on the machine instead. The command's own
output and exit code come back unchanged; a login shell may print its own
lines first, so a caller that wants one result reads the last line.

Exit codes: the command's, 255 = SSH failed, 2 = bad arguments.
"""
import argparse
import shlex
import subprocess
import sys

from config import LOCAL, herdr_machines


def remote_argv(target, command, cwd=None):
    """The ssh argv that runs `command` (a list) in `target`'s login shell."""
    line = shlex.join(command)
    if cwd:
        line = f"cd {shlex.quote(cwd)} && {line}"
    return ["ssh", "-o", "BatchMode=yes", target, f'exec "$SHELL" -lic {shlex.quote(line)}']


def main(argv):
    if "--" not in argv:
        print("usage: remote.py MACHINE [--cwd DIR] -- COMMAND [ARG...]", file=sys.stderr)
        return 2
    split = argv.index("--")
    ap = argparse.ArgumentParser(prog="remote.py")
    ap.add_argument("machine")
    ap.add_argument("--cwd")
    args = ap.parse_args(argv[:split])
    command = argv[split + 1:]
    if not command:
        print("remote.py: no command after --", file=sys.stderr)
        return 2
    if args.machine == LOCAL:
        return subprocess.run(command, cwd=args.cwd).returncode
    machines = herdr_machines()
    if args.machine not in machines:
        print(f"remote.py: {args.machine!r} is not a saved herdr machine", file=sys.stderr)
        return 2
    return subprocess.run(remote_argv(machines[args.machine]["target"], command, args.cwd)).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
