#!/usr/bin/env python3
"""Start a coding agent (claude) from a herdr-foreman profile.

Usage:
  python3 launch.py [PROFILE] [--name NAME] [--session-id UUID] [--group OWNER/REPO]
                    [--no-worktree] [--dry-run]

Run from a bundle (a directory that holds `.claude-plugin/plugin.json` and
`config.json` next to `scripts/`), it uses the bundle's settings and loads the
bundle as a plugin with `--plugin-dir`, so the agent gets the bundle's skills
as `foreman-kit:<skill>`. Run from the skill, it uses the merged settings
(`--group` adds the group's).

PROFILE defaults to the settings' launch profile. The script sets the
gateway's environment for this process only and replaces itself with
`claude`, so it runs the same in any shell.

--dry-run prints the command and the names of the variables it sets or
clears, never their values.

Exit codes: 3 = setup needed, 4 = the gateway's token variable is not set,
2 = bad arguments.
"""
import argparse
import os
import shutil
import sys

from config import (EXIT_SETUP_NEEDED, EXIT_TOKEN_MISSING, REPO, ROLES, load, read_json, user_path,
                    validate_launch)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Variables a gateway may set. They are cleared first, so a value inherited
# from the parent shell never leaks into another gateway's agent.
GATEWAY_VARS = [
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
]


def fail(code, message):
    print(f"launch.py: {message}", file=sys.stderr)
    sys.exit(code)


def bundle_root():
    """The bundle this script runs from, or None when it runs from the skill."""
    if os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json")) and \
            os.path.isfile(os.path.join(ROOT, "config.json")):
        return ROOT
    return None


def gateway_env(gateway, profile):
    """Return (variables to set, variables to clear) for one profile."""
    clear = set(GATEWAY_VARS)
    if gateway.get("kind") == "anthropic":
        return {}, clear
    token = os.environ.get(gateway["token_env"])
    if not token:
        fail(EXIT_TOKEN_MISSING, f"token variable {gateway['token_env']} is not set in this environment")
    models = gateway["models"]
    main = models[profile["model"]]
    env = {
        "ANTHROPIC_BASE_URL": gateway["base_url"],
        "ANTHROPIC_MODEL": main["id"],
        "CLAUDE_CODE_MAX_CONTEXT_TOKENS": str(main["context"]),
        "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(main["context"]),
    }
    for role in ROLES:
        env[f"ANTHROPIC_DEFAULT_{role.upper()}_MODEL"] = models[profile["roles"][role]]["id"]
    if gateway["auth"] == "bearer":
        env["ANTHROPIC_AUTH_TOKEN"] = token
    else:
        env["ANTHROPIC_API_KEY"] = token
        clear.discard("ANTHROPIC_API_KEY")
    clear -= set(env)
    return env, clear


def build(args, cfg, bundle):
    profile_name = args.profile or cfg["launch"]["profile"]
    profile = cfg["profiles"].get(profile_name)
    if profile is None:
        fail(EXIT_SETUP_NEEDED, f"profile {profile_name!r} does not exist")
    gateway = cfg["gateways"][profile["gateway"]]
    env, clear = gateway_env(gateway, profile)
    model = profile["model"] if gateway.get("kind") == "anthropic" else gateway["models"][profile["model"]]["id"]

    # `-w` takes an optional name, so it goes first and is followed by an
    # option; otherwise it would swallow the next argument as the worktree name.
    argv = ["claude"]
    if cfg["launch"]["worktree"] and not args.no_worktree:
        argv += ["-w"] + ([args.name] if args.name else [])
    if args.name:
        argv += ["--name", args.name]
    if args.session_id:
        argv += ["--session-id", args.session_id]
    argv += ["--model", model]
    if cfg["launch"]["permission"] == "bypass":
        argv.append("--dangerously-skip-permissions")
    if bundle:
        argv += ["--plugin-dir", bundle]
    return profile_name, profile["gateway"], argv, env, clear


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

    bundle = bundle_root()
    if bundle:
        cfg = read_json(os.path.join(bundle, "config.json"))
        where = os.path.join(bundle, "config.json")
    else:
        cfg = load(args.group)
        where = user_path()
    problems = validate_launch(cfg)
    if problems:
        fail(EXIT_SETUP_NEEDED, f"settings problem ({where}): {problems[0]}")
    profile_name, gateway_name, argv, env, clear = build(args, cfg, bundle)

    if args.dry_run:
        print(f"profile: {profile_name}")
        print(f"gateway: {gateway_name}")
        print(f"set:     {' '.join(sorted(env)) or '-'}")
        print(f"clear:   {' '.join(sorted(clear)) or '-'}")
        print("command: " + " ".join(repr(a) if " " in a else a for a in argv))
        return 0
    if shutil.which("claude") is None:
        fail(EXIT_SETUP_NEEDED, "claude is not on PATH")
    child = {k: v for k, v in os.environ.items() if k not in clear}
    child.update(env)
    os.execvpe("claude", argv, child)


if __name__ == "__main__":
    sys.exit(main())
