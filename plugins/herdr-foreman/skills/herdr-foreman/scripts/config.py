#!/usr/bin/env python3
"""Settings of herdr-foreman: standard values, user settings and group settings.

Three levels, each laid over the one before:

  standard  defaults.json in this skill's directory
  user      $XDG_CONFIG_HOME/herdr-foreman/config.json   (~/.config/...)
  group     $XDG_STATE_HOME/herdr-foreman/groups/<owner>-<repo>/group.json

The user and group files hold only the values that differ from the level
below; a missing key falls back. Settings hold token variable names only,
never token values.

Usage:
  config.py paths [--group OWNER/REPO]
  config.py show [--group OWNER/REPO]
  config.py check [--group OWNER/REPO]
  config.py save user|group [--group OWNER/REPO] [--dry-run]   (full settings as JSON on stdin)
  config.py stages --group OWNER/REPO --task TASK [--agent KIND]
  config.py member MACHINE PATH [--agent KIND]   (is the checkout there and ready for that agent kind)
  config.py profiles | groups | machines | skills

`plugin_dirs` in the settings lists plugin directories the person loads with
`--plugin-dir` (often through a `claude` shell wrapper). Skill lookups pass
them to `claude plugin list`, so their skills count as available.
"""
import argparse
import copy
import json
import os
import re
import shlex
import string
import subprocess
import sys
import tempfile

import adapters

APP = "herdr-foreman"
KINDS = ["anthropic", "anthropic-compatible"]
AUTHS = ["bearer", "x-api-key"]
ROLES = ["opus", "sonnet", "haiku"]
PERMISSIONS = ["bypass", "default"]
PLACEMENTS = ["least-busy", "ask"]
# Events the foreman handles. Only the ones that rename a tab take a label.
EVENTS = ["started", "stage", "done", "blocked", "stalled", "exited",
          "owner-decision", "approved", "merged", "all-approved"]
LABEL_EVENTS = ["blocked", "exited", "owner-decision"]
PLACEHOLDERS = ["task", "stage", "round", "machine", "profile", "group"]
SECTIONS = ["plugin_dirs", "gateways", "profiles", "launch", "bundle", "loop", "labels", "report", "ops"]
GROUP_KEYS = ["repo", "workspace", "members"]
LOCAL = "local"
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

# Exit codes shared by the scripts, so the foreman can tell the cases apart.
EXIT_SETUP_NEEDED = 3
EXIT_TOKEN_MISSING = 4

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)


def _xdg(var, fallback):
    return os.environ.get(var) or os.path.join(os.path.expanduser("~"), fallback)


def defaults_path():
    return os.path.join(SKILL_DIR, "defaults.json")


def user_path():
    return os.path.join(_xdg("XDG_CONFIG_HOME", ".config"), APP, "config.json")


def state_dir():
    return os.path.join(_xdg("XDG_STATE_HOME", os.path.join(".local", "state")), APP)


def cache_dir():
    return os.path.join(_xdg("XDG_CACHE_HOME", ".cache"), APP)


def group_dir(repo):
    return os.path.join(state_dir(), "groups", repo.replace("/", "-"))


def group_path(repo):
    return os.path.join(group_dir(repo), "group.json")


def ledger_path(repo):
    return os.path.join(group_dir(repo), "ledger.md")


def read_json(path, default=None):
    if not os.path.exists(path):
        return copy.deepcopy(default) if default is not None else {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp.", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def merge(base, over):
    """`over` laid on `base`: dicts merge key by key, anything else replaces."""
    out = copy.deepcopy(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def diff(base, full):
    """The part of `full` that differs from `base`, so that merge(base, diff) == full
    for every key `full` has."""
    out = {}
    for key, value in full.items():
        if key not in base:
            out[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(base[key], dict):
            sub = diff(base[key], value)
            if sub:
                out[key] = sub
        elif value != base[key]:
            out[key] = copy.deepcopy(value)
    return out


def standard():
    return read_json(defaults_path())


def load(repo=None):
    """Settings in effect: standard, then user, then the group's when `repo` is given."""
    cfg = merge(standard(), read_json(user_path()))
    if repo:
        cfg = merge(cfg, read_json(group_path(repo)))
        cfg.setdefault("repo", repo)
        cfg.setdefault("workspace", repo.split("/", 1)[1])
    return cfg


def _placeholders(fmt):
    return [field for _, field, _, _ in string.Formatter().parse(fmt) if field is not None]


def validate_launch(cfg):
    """Problems in the settings launch.py needs: gateways, profiles, launch."""
    problems = []
    gateways = cfg.get("gateways", {})
    profiles = cfg.get("profiles", {})
    for name, g in gateways.items():
        if g.get("kind") not in KINDS:
            problems.append(f"gateway {name}: unknown kind {g.get('kind')!r}")
            continue
        if g["kind"] == "anthropic":
            continue
        if not str(g.get("base_url", "")).startswith(("http://", "https://")):
            problems.append(f"gateway {name}: base_url must start with http:// or https://")
        if not ENV_NAME.match(str(g.get("token_env", ""))):
            problems.append(f"gateway {name}: token_env must be an environment variable name")
        if g.get("auth") not in AUTHS:
            problems.append(f"gateway {name}: auth must be one of {', '.join(AUTHS)}")
        for alias, m in g.get("models", {}).items():
            if not m.get("id"):
                problems.append(f"gateway {name}: model {alias} has no id")
            if not isinstance(m.get("context"), int) or m["context"] <= 0:
                problems.append(f"gateway {name}: model {alias} needs a positive context size")
    for name, p in profiles.items():
        if adapters.kind_of(p) not in adapters.KINDS:
            problems.append(f"profile {name}: agent {adapters.kind_of(p)!r} is not supported; "
                            f"supported: {', '.join(adapters.KINDS)}")
        g = gateways.get(p.get("gateway"))
        if g is None:
            problems.append(f"profile {name}: gateway {p.get('gateway')!r} does not exist")
            continue
        if g.get("kind") == "anthropic":
            if not p.get("model"):
                problems.append(f"profile {name}: model is empty")
            continue
        models = g.get("models", {})
        if p.get("model") not in models:
            problems.append(f"profile {name}: model {p.get('model')!r} is not on gateway {p['gateway']}")
        for role in ROLES:
            if p.get("roles", {}).get(role) not in models:
                problems.append(f"profile {name}: role {role} has no model of gateway {p['gateway']}")

    launch = cfg.get("launch", {})
    if launch.get("profile") not in profiles:
        problems.append(f"launch: profile {launch.get('profile')!r} does not exist")
    if launch.get("permission") not in PERMISSIONS:
        problems.append(f"launch: permission must be one of {', '.join(PERMISSIONS)}")
    if not isinstance(launch.get("worktree"), bool):
        problems.append("launch: worktree must be true or false")
    return problems


def validate(cfg, machines=None, skills=None, group=False):
    """Problems in merged settings, as lines. `machines` (label -> info) and
    `skills` (ref -> path) are checked against when given."""
    problems = []
    allowed = SECTIONS + (GROUP_KEYS if group else [])
    for key in cfg:
        if key not in allowed:
            problems.append(f"unknown setting {key!r}")
    problems += validate_launch(cfg)
    profiles = cfg.get("profiles", {})

    dirs = cfg.get("plugin_dirs", [])
    if not isinstance(dirs, list) or not all(isinstance(d, str) for d in dirs):
        problems.append("plugin_dirs must be a list of directory paths")
    else:
        for d in dirs:
            if not os.path.isfile(os.path.join(os.path.expanduser(d), ".claude-plugin", "plugin.json")):
                problems.append(f"plugin_dirs: {d} has no .claude-plugin/plugin.json")

    loop = cfg.get("loop", {})
    stages = loop.get("stages")
    stage_names = []
    if not isinstance(stages, list) or not stages:
        problems.append("loop: stages must be a non-empty list")
        stages = []
    for i, s in enumerate(stages):
        name = s.get("name", "") if isinstance(s, dict) else ""
        if not NAME.match(str(name)):
            problems.append(f"loop: stage {i + 1} needs a name of letters, digits, '.', '_' or '-'")
            continue
        if name in stage_names:
            problems.append(f"loop: stage {name} appears twice")
        stage_names.append(name)
        if not str(s.get("method", "")).strip():
            problems.append(f"loop: stage {name} has no method")
        if not isinstance(s.get("skills", []), list):
            problems.append(f"loop: stage {name}: skills must be a list")
    for tier, profile in loop.get("tier_profiles", {}).items():
        if profile not in profiles:
            problems.append(f"loop: tier {tier} uses profile {profile!r}, which does not exist")

    refs = list(cfg.get("bundle", {}).get("skills", []))
    if not isinstance(cfg.get("bundle", {}).get("skills", []), list):
        problems.append("bundle: skills must be a list")
        refs = []
    for s in stages:
        if isinstance(s, dict) and isinstance(s.get("skills", []), list):
            refs += s.get("skills", [])
    seen = {}
    for ref in refs:
        short = str(ref).split(":")[-1]
        if seen.get(short, ref) != ref:
            problems.append(f"skills {seen[short]} and {ref} would share the name {short} in the bundle")
        seen[short] = ref
        if skills is not None and ref not in skills:
            problems.append(f"skill {ref!r} is not available on this machine")

    labels = cfg.get("labels", {})
    formats = {"default": labels.get("default", "")}
    for event, fmt in labels.get("events", {}).items():
        if event not in stage_names and event not in LABEL_EVENTS:
            problems.append(f"labels: {event!r} is neither a stage nor one of {', '.join(LABEL_EVENTS)}")
        formats[event] = fmt
    for event, fmt in formats.items():
        if not str(fmt).strip():
            problems.append(f"labels: {event} is empty")
            continue
        try:
            fields = _placeholders(str(fmt))
        except ValueError as e:
            problems.append(f"labels: {event}: {e}")
            continue
        for field in fields:
            if field not in PLACEHOLDERS:
                problems.append(f"labels: {event} uses {{{field}}}; use only "
                                + ", ".join("{" + p + "}" for p in PLACEHOLDERS))

    report = cfg.get("report", {})
    if not str(report.get("template", "")).strip():
        problems.append("report: template is empty")
    for key in ("language", "address"):
        if not isinstance(report.get(key, ""), str):
            problems.append(f"report: {key} must be text")

    ops = cfg.get("ops", {})
    if not isinstance(ops.get("check_minutes"), int) or ops["check_minutes"] <= 0:
        problems.append("ops: check_minutes must be a positive whole number")
    backoff = ops.get("backoff", {})
    if not isinstance(backoff.get("first_hours"), (int, float)) or backoff["first_hours"] <= 0:
        problems.append("ops: backoff.first_hours must be a positive number")
    if not isinstance(backoff.get("factor"), (int, float)) or backoff["factor"] < 1:
        problems.append("ops: backoff.factor must be 1 or more")
    batch = ops.get("batch")
    if batch is not None and (not isinstance(batch, int) or isinstance(batch, bool) or batch <= 0):
        problems.append("ops: batch must be a positive whole number or null")
    if ops.get("placement") not in PLACEMENTS:
        problems.append(f"ops: placement must be one of {', '.join(PLACEMENTS)}")
    if not isinstance(ops.get("disk_check"), bool):
        problems.append("ops: disk_check must be true or false")
    if not isinstance(ops.get("after_merge", []), list):
        problems.append("ops: after_merge must be a list of steps")

    if group:
        if not REPO.match(str(cfg.get("repo", ""))):
            problems.append("group: repo must look like owner/name")
        if not str(cfg.get("workspace", "")).strip():
            problems.append("group: workspace label is empty")
        members = cfg.get("members")
        if not isinstance(members, dict) or not members:
            problems.append("group: members must name at least one machine and its checkout path")
            members = {}
        for label, path in members.items():
            if not str(path).startswith(("/", "~")):
                problems.append(f"group: member {label}: checkout path must start with / or ~")
            if label == LOCAL or machines is None:
                continue
            if label not in machines:
                problems.append(f"group: member {label} is not a saved herdr machine (herdr machine list)")
            elif not machines[label]["enabled"]:
                problems.append(f"group: member {label} is disabled in herdr")
    return problems


def herdr_machines():
    """Saved herdr machines: label -> {"target": ssh target, "enabled": bool}."""
    out = subprocess.run(["herdr", "machine", "list"], capture_output=True, text=True, check=True)
    machines = {}
    for line in out.stdout.splitlines():
        cols = line.split("\t")
        if len(cols) >= 5:
            machines[cols[1]] = {"target": cols[2], "enabled": cols[4].strip() == "enabled"}
    return machines


def member_state(label, path, machines=None, kind=adapters.DEFAULT):
    """Whether a member's checkout is there and ready for that agent kind:
    {"checkout": bool, "ready": bool, "reason": text}. The check itself is the
    adapter's CHECKOUT_PROBE, run on the member's machine."""
    probe = adapters.get(kind).CHECKOUT_PROBE
    if label == LOCAL:
        argv = [sys.executable, "-c", probe, path]
    else:
        machines = herdr_machines() if machines is None else machines
        if label not in machines:
            raise ValueError(f"{label} is not a saved herdr machine")
        argv = ["ssh", "-o", "BatchMode=yes", machines[label]["target"],
                "python3 -c " + shlex.quote(probe) + " " + shlex.quote(path)]
    out = subprocess.run(argv, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{label}: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def plugin_list(plugin_dirs=()):
    """Claude Code's plugin list, with the settings' `plugin_dirs` loaded the
    way `claude --plugin-dir` loads them for a session."""
    argv = ["claude"]
    for d in plugin_dirs:
        argv += ["--plugin-dir", os.path.expanduser(d)]
    out = subprocess.run(argv + ["plugin", "list", "--json"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def local_skills(plugins=None, user_skills_dir=None):
    """Skills this machine's Claude Code can load: ref -> skill directory.

    A plugin skill is `plugin:skill`; a user skill in ~/.claude/skills is
    `skill`. A link that points nowhere is left out.
    """
    plugins = plugin_list() if plugins is None else plugins
    user_skills_dir = user_skills_dir or os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude"), "skills")
    found = {}
    for p in plugins:
        if not p.get("enabled") or not p.get("installPath"):
            continue
        name = p["id"].split("@", 1)[0]
        root = os.path.join(p["installPath"], "skills")
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            if os.path.isfile(os.path.join(root, entry, "SKILL.md")):
                found[f"{name}:{entry}"] = os.path.join(root, entry)
    if os.path.isdir(user_skills_dir):
        for entry in sorted(os.listdir(user_skills_dir)):
            if os.path.isfile(os.path.join(user_skills_dir, entry, "SKILL.md")):
                found[entry] = os.path.realpath(os.path.join(user_skills_dir, entry))
    return found


def group_skills(cfg, extra=()):
    """Every skill ref a group's bundle carries: bundle.skills, each stage's
    skills, then `extra`, without repeats, in that order."""
    refs = list(cfg.get("bundle", {}).get("skills", []))
    for s in cfg.get("loop", {}).get("stages", []):
        refs += s.get("skills", [])
    refs += list(extra)
    seen = []
    for ref in refs:
        if ref not in seen:
            seen.append(ref)
    return seen


def label(cfg, event, **values):
    """Tab label for an event or a stage, from the group's label formats."""
    fmt = cfg["labels"].get("events", {}).get(event) or cfg["labels"]["default"]
    fields = {p: "" for p in PLACEHOLDERS}
    fields.update({k: str(v) for k, v in values.items()})
    return " ".join(fmt.format(**fields).split())


def stages_markdown(cfg, task, kind=adapters.DEFAULT):
    """The stage table a brief carries, with skills named the way that agent kind calls them."""
    lines = ["| Stage | Tab label | Skills | Method |", "| --- | --- | --- | --- |"]
    for s in cfg["loop"]["stages"]:
        stage = s["name"] + (" <N>" if s["name"] in ("review", "fix") else "")
        tab = label(cfg, s["name"], task=task, stage=stage, round="<N>" if "<N>" in stage else "",
                    group=cfg.get("workspace", ""))
        skills = ", ".join(adapters.get(kind).skill_name(r) for r in s.get("skills", [])) or "-"
        lines.append(f"| {s['name']} | `{tab}` | {skills} | {s['method'].replace('|', '/')} |")
    return "\n".join(lines)


def save(level, full, repo=None, machines=None, skills=None, dry_run=False):
    """Write the part of `full` (settings as they should be in effect at that
    level) that differs from the level below. Returns (path, written, problems)."""
    base = standard()
    if level == "group":
        base = merge(base, read_json(user_path()))
        path = group_path(repo)
    else:
        path = user_path()
    effective = merge(base, full)
    if level == "group":
        effective.setdefault("repo", repo)
        effective.setdefault("workspace", repo.split("/", 1)[1])
    problems = validate(effective, machines=machines, skills=skills, group=level == "group")
    written = diff(base, full)
    if level == "group":
        written["repo"] = repo
    if not problems and not dry_run:
        write_json(path, written)
    return path, written, problems


def plugin_dirs(cfg):
    """The settings' plugin directories that exist; a wrong entry is reported by
    validate(), and left out here so the rest of the lookup still works."""
    dirs = cfg.get("plugin_dirs", [])
    if not isinstance(dirs, list):
        return []
    return [d for d in dirs if isinstance(d, str) and os.path.isdir(os.path.expanduser(d))]


def _cli(argv):
    ap = argparse.ArgumentParser(prog="config.py", description="herdr-foreman settings")
    ap.add_argument("command", choices=["paths", "show", "check", "save", "stages", "member", "profiles",
                                        "groups", "machines", "skills"])
    ap.add_argument("rest", nargs="*", help="save: user or group; member: MACHINE PATH")
    ap.add_argument("--group", metavar="OWNER/REPO")
    ap.add_argument("--task", default="<task>")
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.group and not REPO.match(args.group):
        print(f"config.py: --group must look like owner/name, not {args.group!r}", file=sys.stderr)
        return 2

    if args.command == "paths":
        info = {"standard": defaults_path(), "user": user_path(), "state": state_dir(), "cache": cache_dir()}
        if args.group:
            info.update(group=group_path(args.group), ledger=ledger_path(args.group))
        print(json.dumps(info, indent=2))
    elif args.command == "show":
        print(json.dumps(load(args.group), indent=2, ensure_ascii=False))
    elif args.command == "check":
        cfg = load(args.group)
        problems = validate(cfg, machines=herdr_machines(), group=bool(args.group),
                            skills=local_skills(plugin_list(plugin_dirs(cfg))))
        if args.group and not os.path.exists(group_path(args.group)):
            problems.insert(0, f"group {args.group} has no settings yet ({group_path(args.group)})")
        for p in problems:
            print(p)
        if problems:
            return EXIT_SETUP_NEEDED
        print("ok")
    elif args.command == "save":
        level = args.rest[0] if len(args.rest) == 1 else None
        if level not in ("user", "group") or (level == "group" and not args.group):
            print("config.py: save needs user, or group with --group OWNER/REPO", file=sys.stderr)
            return 2
        full = json.load(sys.stdin)
        dirs = plugin_dirs(full) if "plugin_dirs" in full else plugin_dirs(load(args.group))
        path, written, problems = save(level, full, repo=args.group, machines=herdr_machines(),
                                       skills=local_skills(plugin_list(dirs)), dry_run=args.dry_run)
        for p in problems:
            print(p)
        if problems:
            return EXIT_SETUP_NEEDED
        print(json.dumps({"path": path, "written": written, "dry_run": args.dry_run}, indent=2,
                         ensure_ascii=False))
    elif args.command == "stages":
        if not args.group:
            print("config.py: stages needs --group OWNER/REPO", file=sys.stderr)
            return 2
        print(stages_markdown(load(args.group), args.task, args.agent))
    elif args.command == "member":
        if len(args.rest) != 2:
            print("config.py: member needs MACHINE PATH", file=sys.stderr)
            return 2
        try:
            state = member_state(*args.rest, kind=args.agent)
        except (ValueError, RuntimeError) as e:
            print(f"config.py: {e}", file=sys.stderr)
            return 1
        print(json.dumps(state))
        return 0 if state["ready"] else EXIT_SETUP_NEEDED
    elif args.command == "profiles":
        cfg = load(args.group)
        default = cfg["launch"].get("profile")
        for name, p in cfg["profiles"].items():
            roles = p.get("roles")
            role_text = "  roles " + "/".join(roles[r] for r in ROLES) if roles else ""
            mark = "*" if name == default else " "
            print(f"{mark}{name:12} {p['gateway']:24} {p['model']}{role_text}")
    elif args.command == "groups":
        root = os.path.join(state_dir(), "groups")
        for entry in sorted(os.listdir(root)) if os.path.isdir(root) else []:
            g = read_json(os.path.join(root, entry, "group.json"))
            if g.get("repo"):
                print(f"{g['repo']:40} {' '.join(g.get('members', {}))}")
    elif args.command == "machines":
        for name, m in herdr_machines().items():
            print(f"{name:24} {m['target']:32} {'enabled' if m['enabled'] else 'disabled'}")
    elif args.command == "skills":
        for ref, path in local_skills(plugin_list(plugin_dirs(load(args.group)))).items():
            print(f"{ref:44} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
