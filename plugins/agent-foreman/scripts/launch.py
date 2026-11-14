#!/usr/bin/env python3
"""Start a coding agent from a agent-foreman profile.

Usage:
  python3 launch.py [PROFILE] [--name NAME] [--session-id UUID] [--project OWNER/REPO]
                    [--no-worktree] [--task-dir DIR] [--status FILE] [--disallow TOOL,...] [--dry-run]
  python3 launch.py [PROFILE] --print --prompt-file FILE --out FILE [--role ROLE] [--name NAME]
                    [--session-id UUID] [--task-dir DIR] [--status FILE] [--disallow TOOL,...] [--dry-run]

--disallow TOOL,... removes tools from the agent (a reviewer gets no edit
tools). It narrows what the agent can do; it is not a sandbox.

--task-dir DIR gives the agent its task folder (`status.py dir`): it sets
AF_TASK_DIR, and AF_STATUS_FILE to the folder's status.jsonl unless --status
names another file. --status FILE sets AF_STATUS_FILE alone. Both expand `~`
on this machine and set AF_AGENT (the --name, or the profile). The bundle's
hooks then append heartbeats there, and `status.py note` writes there. Without
them the variables are cleared, so an agent never writes into the status file
of the agent that started it.

The profile's `agent` kind (default `claude`) picks the adapter that builds
the command (scripts/adapters/). Run from a bundle (a directory that holds
`bundle.json` and `config.json` next to `scripts/`), it uses the bundle's
settings and loads the bundle's skills into the agent. Run from the skill, it
uses the merged settings (`--project` adds the project's).

PROFILE defaults to the settings' launch profile. The script sets the
gateway's environment for this process only and replaces itself with the
agent, so it runs the same in any shell.

--print runs the agent once in prompt mode, where it is started (no
worktree): the prompt comes from --prompt-file, the agent's JSON result goes
to --out, and one line of JSON is printed: ok, session_id, cost, denials, out.
Next to --out it writes `<out without .json>.meta.json`: the role (--role),
the agent's name, the profile and its model, the commit checked out where the
agent ran, and when it started and ended. The gate reads verdicts from there.

--dry-run prints the command and the names of the variables it sets or
clears, never their values.

Exit codes: 3 = setup needed, 4 = the gateway's token variable is not set,
5 = a prompt-mode run failed (a usage limit, a gateway error, no result; try
the tier's next profile), 2 = bad arguments.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import adapters
from config import (EXIT_AGENT_ERROR, EXIT_SETUP_NEEDED, EXIT_TOKEN_MISSING, REPO, load, read_json, user_path,
                    validate_launch)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_VARS = ("AF_STATUS_FILE", "AF_AGENT", "AF_TASK_DIR")


def fail(code, message):
    print(f"launch.py: {message}", file=sys.stderr)
    sys.exit(code)


def bundle_root():
    """(bundle directory, its agent kind), or (None, None) when run from the skill."""
    marker = os.path.join(ROOT, "bundle.json")
    if os.path.isfile(marker) and os.path.isfile(os.path.join(ROOT, "config.json")):
        return ROOT, read_json(marker).get("agent", adapters.DEFAULT)
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Start a coding agent from a agent-foreman profile.")
    parser.add_argument("profile", nargs="?")
    parser.add_argument("--name", help="session name; also the worktree name")
    parser.add_argument("--session-id", help="session id (a UUID) the foreman chose, so it can find the transcript")
    parser.add_argument("--project", help="OWNER/REPO whose settings apply (ignored in a bundle)")
    parser.add_argument("--no-worktree", action="store_true")
    parser.add_argument("--print", dest="print_mode", action="store_true",
                        help="answer one prompt and exit (prompt mode)")
    parser.add_argument("--prompt-file", help="with --print: the prompt")
    parser.add_argument("--out", help="with --print: where the agent's JSON result goes")
    parser.add_argument("--disallow", default="", metavar="TOOL,...", help="tools the agent may not use")
    parser.add_argument("--status", metavar="FILE", help="the task's status file, for heartbeats and stage notes")
    parser.add_argument("--task-dir", metavar="DIR", help="the task folder; sets AF_TASK_DIR and its status file")
    parser.add_argument("--role", help="with --print: the loop role this agent plays, recorded for the gate")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.print_mode and not (args.prompt_file and args.out):
        fail(2, "--print needs --prompt-file and --out")
    if args.print_mode and not os.path.isfile(args.prompt_file):
        fail(2, f"no prompt file at {args.prompt_file}")
    if args.project and not REPO.match(args.project):
        fail(2, f"--project must look like owner/name, not {args.project!r}")

    bundle, bundle_kind = bundle_root()
    if bundle:
        cfg = read_json(os.path.join(bundle, "config.json"))
        where = os.path.join(bundle, "config.json")
    else:
        cfg = load(args.project)
        where = user_path()
    problems = validate_launch(cfg)
    if problems:
        fail(EXIT_SETUP_NEEDED, f"settings problem ({where}): {problems[0]}")

    profile_name = args.profile or cfg["launch"]["profile"]
    profile = cfg["profiles"].get(profile_name)
    if profile is None:
        fail(EXIT_SETUP_NEEDED, f"profile {profile_name!r} does not exist")
    kind = adapters.kind_of(profile)
    if bundle and kind != bundle_kind:
        fail(EXIT_SETUP_NEEDED, f"profile {profile_name} runs {kind}, but this bundle is for {bundle_kind}")
    adapter = adapters.get(kind)
    try:
        argv, env, clear = adapter.command(cfg, profile_name, name=args.name, session_id=args.session_id,
                                           worktree=cfg["launch"]["worktree"] and not args.no_worktree,
                                           bundle=bundle, print_mode=args.print_mode,
                                           disallowed=[t.strip() for t in args.disallow.split(",") if t.strip()])
    except adapters.TokenMissing as e:
        fail(EXIT_TOKEN_MISSING, f"token variable {e.variable} is not set in this environment")
    task_dir = os.path.abspath(os.path.expanduser(args.task_dir)) if args.task_dir else None
    status = args.status or (os.path.join(task_dir, "status.jsonl") if task_dir else None)
    clear = set(clear) | set(STATUS_VARS)
    if status:
        env.update(AF_STATUS_FILE=os.path.abspath(os.path.expanduser(status)), AF_AGENT=args.name or profile_name)
        clear -= {"AF_STATUS_FILE", "AF_AGENT"}
    if task_dir:
        env["AF_TASK_DIR"] = task_dir
        clear.discard("AF_TASK_DIR")

    if args.dry_run:
        print(f"profile: {profile_name}")
        print(f"agent:   {kind}")
        print(f"gateway: {profile['gateway']}")
        print(f"set:     {' '.join(sorted(env)) or '-'}")
        print(f"clear:   {' '.join(sorted(clear)) or '-'}")
        print("command: " + " ".join(repr(a) if " " in a else a for a in argv))
        return 0
    if shutil.which(adapter.EXECUTABLE) is None:
        fail(EXIT_SETUP_NEEDED, f"{adapter.EXECUTABLE} is not on PATH")
    child = {k: v for k, v in os.environ.items() if k not in clear}
    child.update(env)
    if not args.print_mode:
        os.execvpe(adapter.EXECUTABLE, argv, child)
    meta = {"role": args.role, "agent": args.name or profile_name, "profile": profile_name,
            "gateway": profile["gateway"], "model": profile["model"], "head": head_commit()}
    return run_once(adapter, argv, child, args.prompt_file, args.out, meta)


def head_commit():
    """The commit checked out where the agent runs, or None outside a git checkout."""
    r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def now_iso():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def meta_path(out):
    return (out[:-5] if out.endswith(".json") else out) + ".meta.json"


def write_atomic(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".tmp.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def run_once(adapter, argv, env, prompt_file, out, meta=None):
    """Prompt mode: run the agent once, keep its raw result and what ran it,
    print a summary."""
    started = now_iso()
    with open(prompt_file, "rb") as prompt:
        proc = subprocess.run(argv, stdin=prompt, capture_output=True, env=env)
    text = proc.stdout.decode("utf-8", "replace")
    write_atomic(out, text)
    summary = adapter.parse_print(text)
    ok = summary["ok"] and proc.returncode == 0
    write_atomic(meta_path(out), json.dumps({**(meta or {}), "started": started, "ended": now_iso(), "ok": ok,
                                             "session_id": summary["session_id"]}, indent=2) + "\n")
    print(json.dumps({"ok": ok, "session_id": summary["session_id"], "cost": summary["cost"],
                      "denials": len(summary["denials"]), "out": os.path.abspath(out),
                      "error": None if ok else (summary["result"] or proc.stderr.decode("utf-8", "replace"))[-300:]}))
    return 0 if ok else EXIT_AGENT_ERROR


if __name__ == "__main__":
    sys.exit(main())
