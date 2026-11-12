"""Claude Code adapter."""
import glob
import json
import os

from .base import NoTranscript, TokenMissing

KIND = "claude"
HERDR_KIND = "claude"
EXECUTABLE = "claude"
PLUGIN = "foreman-kit"
ROLES = ["opus", "sonnet", "haiku"]

# Variables a gateway may set. They are cleared first, so a value inherited
# from the parent shell never leaks into another gateway's agent.
GATEWAY_VARS = [
    "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_MAX_CONTEXT_TOKENS", "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
]


def gateway_env(gateway, profile, environ):
    """Return (variables to set, variable names to clear) for one profile."""
    clear = set(GATEWAY_VARS)
    if gateway.get("kind") == "anthropic":
        return {}, clear
    token = environ.get(gateway["token_env"])
    if not token:
        raise TokenMissing(gateway["token_env"])
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


def command(cfg, profile_name, name=None, session_id=None, worktree=True, bundle=None, environ=None):
    """Return (argv, variables to set, variable names to clear)."""
    profile = cfg["profiles"][profile_name]
    gateway = cfg["gateways"][profile["gateway"]]
    env, clear = gateway_env(gateway, profile, os.environ if environ is None else environ)
    model = profile["model"] if gateway.get("kind") == "anthropic" else gateway["models"][profile["model"]]["id"]
    # `-w` takes an optional name, so it goes first and is followed by an
    # option; otherwise it would swallow the next argument as the worktree name.
    argv = [EXECUTABLE]
    if worktree:
        argv += ["-w"] + ([name] if name else [])
    if name:
        argv += ["--name", name]
    if session_id:
        argv += ["--session-id", session_id]
    argv += ["--model", model]
    if cfg["launch"]["permission"] == "bypass":
        argv.append("--dangerously-skip-permissions")
    if bundle:
        argv += ["--plugin-dir", bundle]
    return argv, env, clear


def skill_name(ref):
    return f"{PLUGIN}:{ref.split(':')[-1]}"


def bundle_layout(skills):
    """A Claude Code plugin that holds the skills; `--plugin-dir` loads it."""
    files = {".claude-plugin/plugin.json": json.dumps({
        "name": PLUGIN,
        "version": "1.0.0",
        "description": "Skills and scripts herdr-foreman gives its agents",
    }, indent=2).encode() + b"\n"}
    for short, contents in skills.items():
        for rel, data in contents.items():
            files[f"skills/{short}/{rel}"] = data
    return files


def _projects(root):
    return root or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "projects")


def _starts_turn(entry):
    if entry.get("isMeta"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        return any(b.get("type") == "text" for b in blocks) and not any(b.get("type") == "tool_result" for b in blocks)
    return False


def turns(lines):
    """The assistant text blocks of each turn, as a list of lists. A turn
    starts at a typed prompt; tool results, meta entries and subagent entries
    do not start one."""
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


def last_answers(session_id, n=1, root=None):
    """The final text of each of the last n answered turns, oldest first, read
    from ~/.claude/projects/*/<session id>.jsonl. Returns (answers, total)."""
    root = _projects(root)
    hits = glob.glob(os.path.join(root, "*", f"{session_id}.jsonl"))
    if not hits:
        raise NoTranscript(f"no transcript for session {session_id} under {root}")
    with open(max(hits, key=os.path.getmtime), encoding="utf-8") as f:
        answered = [t for t in turns(f) if t]
    return [t[-1] for t in answered[-n:]], len(answered)


# Runs on the member's machine with `python3 -c`; argv[1] is the checkout path.
# A worktree session refuses a checkout Claude Code has never been trusted in.
CHECKOUT_PROBE = """
import json, os, sys
path = os.path.expanduser(sys.argv[1])
try:
    with open(os.path.join(os.path.expanduser("~"), ".claude.json"), encoding="utf-8") as f:
        projects = json.load(f).get("projects", {})
except (OSError, ValueError):
    projects = {}
checkout = os.path.isdir(os.path.join(path, ".git"))
trusted = bool(projects.get(path, {}).get("hasTrustDialogAccepted"))
reason = "" if checkout and trusted else (
    "no git checkout at this path" if not checkout else
    "Claude Code is not trusted here: run claude once in this checkout and accept the trust question")
print(json.dumps({"checkout": checkout, "ready": checkout and trusted, "reason": reason}))
"""
