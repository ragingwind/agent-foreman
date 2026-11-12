#!/usr/bin/env python3
"""Start a coding agent from a herdr-foreman profile.

Usage:
  python3 launch.py [PROFILE] [--name NAME] [--session-id UUID] [--group OWNER/REPO]
                    [--no-worktree] [--dry-run]

The profile's `agent` kind (default `claude`) picks the adapter that builds
the command (scripts/adapters/). Run from a bundle (a directory that holds
`bundle.json` and `config.json` next to `scripts/`), it uses the bundle's
settings and loads the bundle's skills into the agent. Run from the skill, it
uses the merged settings (`--group` adds the group's).

PROFILE defaults to the settings' launch profile. The script sets the
gateway's environment for this process only and replaces itself with the
agent, so it runs the same in any shell.

--dry-run prints the command and the names of the variables it sets or
clears, never their values.

Exit codes: 3 = setup needed, 4 = the gateway's token variable is not set,
2 = bad arguments.
"""
import argparse
import os
import shutil
import sys

import adapters
from config import EXIT_SETUP_NEEDED, EXIT_TOKEN_MISSING, REPO, load, read_json, user_path, validate_launch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    parser = argparse.ArgumentParser(description="Start a coding agent from a herdr-foreman profile.")
    parser.add_argument("profile", nargs="?")
    parser.add_argument("--name", help="session name; also the worktree name")
    parser.add_argument("--session-id", help="session id (a UUID) the foreman chose, so it can find the transcript")
    parser.add_argument("--group", help="OWNER/REPO whose settings apply (ignored in a bundle)")
    parser.add_argument("--no-worktree", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.group and not REPO.match(args.group):
        fail(2, f"--group must look like owner/name, not {args.group!r}")

    bundle, bundle_kind = bundle_root()
    if bundle:
        cfg = read_json(os.path.join(bundle, "config.json"))
        where = os.path.join(bundle, "config.json")
    else:
        cfg = load(args.group)
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
                                           bundle=bundle)
    except adapters.TokenMissing as e:
        fail(EXIT_TOKEN_MISSING, f"token variable {e.variable} is not set in this environment")

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
    os.execvpe(adapter.EXECUTABLE, argv, child)


if __name__ == "__main__":
    sys.exit(main())
