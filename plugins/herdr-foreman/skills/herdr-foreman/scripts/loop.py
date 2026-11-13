#!/usr/bin/env python3
"""Loops: stages made of steps, the roles that act in them, their skills, and
how they change with a task's difficulty.

Settings shape (`loop` in the settings):

  roles    name -> {"mode": "prompt"|"pane", "step": 0|1, "prompt": key, "deny_tools": [...],
                   "verdict_title": title of its verdict comment, "accept": [passing verdicts]}
  prompts  key -> fixed prompt text a role gets, filled in
  work     the work loop's steps (one issue, one pull request), run by a lead
  manage   the foreman's loop
  epic     the batch loop before an epic goes to main

A loop is a list of steps. A step: {"id", "stage", "actor", "does",
"skills": [...], "next": {outcome: step id or "stop"}, and optionally "run":
{difficulty: "always"|"never"|"if-not-trivial"}, "count": {difficulty: n},
"extra": {difficulty: text}}. "if-not-trivial" runs unless the foreman
marked the task trivial: docs or text only, a typo, or a rename that changes
no behavior. The last outcome in "next" is the success path; a step that
does not run for a task passes straight to it.

A stage is a run of consecutive steps with the same "stage"; a step without
one is a stage of its own. Tab labels, status lines and reports follow the
stages; the rules above stay on the steps. A stage whose steps all do not
run for a task is skipped.

Usage:
  loop.py show [--project OWNER/REPO] [--loop work|manage|epic]
  loop.py skills --project OWNER/REPO --machine MACHINE
  loop.py render --project OWNER/REPO --task N --difficulty low|mid|high
                 --machine MACHINE [--trivial] [--agent KIND]

Exit codes: 2 = bad arguments, 3 = setup needed.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

LEVELS = ["low", "mid", "high"]
LOOPS = ["work", "manage", "epic"]
PEOPLE = ["lead", "foreman", "person"]
MODES = ["prompt", "pane"]
RUNS = ["always", "never", "if-not-trivial"]
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STOP = "stop"


def validate_loop(loop):
    """Problems in the `loop` settings, as lines."""
    problems = []
    if not isinstance(loop, dict):
        return ["loop must be an object"]
    roles = loop.get("roles", {})
    prompts = loop.get("prompts", {})
    if not isinstance(roles, dict) or not isinstance(prompts, dict):
        return ["loop: roles and prompts must be objects"]
    for key, text in prompts.items():
        if not isinstance(text, str) or not text.strip():
            problems.append(f"loop: prompt {key} is empty")
    for name, role in roles.items():
        if not NAME.match(name) or name in PEOPLE:
            problems.append(f"loop: role name {name!r} is not allowed")
        if role.get("mode") not in MODES:
            problems.append(f"loop: role {name}: mode must be one of {', '.join(MODES)}")
        if not isinstance(role.get("step", 0), int) or role.get("step", 0) < 0:
            problems.append(f"loop: role {name}: step must be 0 or more")
        if "prompt" in role and role["prompt"] not in prompts:
            problems.append(f"loop: role {name}: prompt {role['prompt']!r} does not exist")
        if "verdict_title" in role and not (isinstance(role["verdict_title"], str) and role["verdict_title"].strip()):
            problems.append(f"loop: role {name}: verdict_title must be text")
        accept = role.get("accept", [])
        if not isinstance(accept, list) or not all(isinstance(x, str) and x for x in accept):
            problems.append(f"loop: role {name}: accept must be a list of verdicts")
        deny = role.get("deny_tools", [])
        if not isinstance(deny, list) or not all(isinstance(t, str) and t for t in deny):
            problems.append(f"loop: role {name}: deny_tools must be a list of tool names")
    if not loop.get("work"):
        problems.append("loop: the work loop has no steps")
    for which in LOOPS:
        steps = loop.get(which, [])
        if not isinstance(steps, list):
            problems.append(f"loop: {which} must be a list of steps")
            continue
        ids = [s.get("id") for s in steps if isinstance(s, dict)]
        problems += _stage_problems(which, [s for s in steps if isinstance(s, dict) and NAME.match(str(s.get("id", "")))])
        for i, s in enumerate(steps):
            where = f"loop: {which} step {i + 1}"
            if not isinstance(s, dict) or not NAME.match(str(s.get("id", ""))):
                problems.append(f"{where} needs an id of letters, digits, '.', '_' or '-'")
                continue
            where = f"loop: {which} step {s['id']}"
            if ids.count(s["id"]) > 1:
                problems.append(f"{where} appears twice")
            actor = s.get("actor")
            if actor not in PEOPLE and actor not in roles:
                problems.append(f"{where}: actor {actor!r} is neither {', '.join(PEOPLE)} nor a role")
            if not str(s.get("does", "")).strip():
                problems.append(f"{where} says nothing it does")
            if not isinstance(s.get("skills", []), list) or not all(isinstance(x, str) for x in s.get("skills", [])):
                problems.append(f"{where}: skills must be a list of names")
            nxt = s.get("next")
            if not isinstance(nxt, dict) or not nxt:
                problems.append(f"{where}: next must name at least one outcome")
            else:
                for outcome, target in nxt.items():
                    if target != STOP and target not in ids:
                        problems.append(f"{where}: outcome {outcome} goes to {target!r}, which is not a step")
            for key, allowed in (("run", RUNS), ("count", None), ("extra", None)):
                table = s.get(key, {})
                if not isinstance(table, dict):
                    problems.append(f"{where}: {key} must map difficulties to values")
                    continue
                for level, value in table.items():
                    if level not in LEVELS:
                        problems.append(f"{where}: {key} names {level!r}; use {', '.join(LEVELS)}")
                    elif allowed and value not in allowed:
                        problems.append(f"{where}: run for {level} must be one of {', '.join(allowed)}")
                    elif key == "count" and (not isinstance(value, int) or value < 1):
                        problems.append(f"{where}: count for {level} must be 1 or more")
    return problems


def stage_of(step):
    return step.get("stage") or step["id"]


def _stage_problems(which, steps):
    """A stage's steps must sit together, and a stage may not take the name
    of another stage's step."""
    problems, seen, last = [], [], None
    ids = {s["id"]: stage_of(s) for s in steps}
    for s in steps:
        if "stage" in s and not NAME.match(str(s["stage"])):
            problems.append(f"loop: {which} step {s['id']}: stage must be a name of letters, digits, '.', '_' or '-'")
            continue
        st = stage_of(s)
        if st != last and st in seen:
            problems.append(f"loop: {which} stage {st}: its steps must come one after another")
        if st not in seen:
            if ids.get(st, st) != st:
                problems.append(f"loop: {which} stage {st} has the name of step {st}, which is in stage {ids[st]}")
            seen.append(st)
        last = st
    return problems


def step_ids(loop, which="work"):
    return [s["id"] for s in loop.get(which, []) if isinstance(s, dict) and "id" in s]


def stage_ids(loop, which="work"):
    """The loop's stages in order."""
    out = []
    for s in loop.get(which, []):
        if isinstance(s, dict) and "id" in s and stage_of(s) not in out:
            out.append(stage_of(s))
    return out


def plan(loop, difficulty, trivial=False, which="work"):
    """The steps that run for one task, with `next` rewired past the ones
    that do not run, and each step's stage, count and extra for this
    difficulty."""
    steps = loop.get(which, [])
    runs = {}
    for s in steps:
        rule = s.get("run", {}).get(difficulty, "always")
        runs[s["id"]] = rule == "always" or (rule == "if-not-trivial" and not trivial)
    by_id = {s["id"]: s for s in steps}

    def land(target, seen=()):
        while target != STOP and not runs[target]:
            if target in seen:
                raise ValueError(f"loop: skipped steps form a cycle at {target}")
            seen = seen + (target,)
            target = list(by_id[target]["next"].values())[-1]
        return target

    out = []
    for s in steps:
        if not runs[s["id"]]:
            continue
        item = {k: v for k, v in s.items() if k not in ("run", "count", "extra")}
        item["stage"] = stage_of(s)
        item["next"] = {k: land(v) for k, v in s["next"].items()}
        item["count"] = s.get("count", {}).get(difficulty, 1)
        item["extra"] = s.get("extra", {}).get(difficulty, "")
        out.append(item)
    return out


def project_skill_names(label, path, saved=None):
    """Skills the project's own checkout has on a machine (`.claude/skills/*`)."""
    if label == "local":
        root = os.path.join(os.path.expanduser(path), ".claude", "skills")
        if not os.path.isdir(root):
            return []
        return sorted(e for e in os.listdir(root) if os.path.isfile(os.path.join(root, e, "SKILL.md")))
    if saved is None:
        from config import herdr_machines
        saved = herdr_machines()
    if label not in saved:
        raise ValueError(f"{label} is not a saved herdr machine")
    probe = f"cd {shlex.quote(path)}/.claude/skills 2>/dev/null && for d in */; do test -f \"$d/SKILL.md\" && echo \"${{d%/}}\"; done; true"
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", saved[label]["target"], probe],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{label}: {out.stderr.strip()[:300]}")
    return sorted(x for x in out.stdout.split() if x)


def resolve_skill(name, project_names, local):
    """Where one stage skill comes from: ("project", name), ("bundle", local ref)
    or ("missing", reason). A project skill wins over a user skill."""
    short = name.split(":")[-1]
    if ":" not in name and short in project_names:
        return "project", short
    if name in local:
        return "bundle", name
    matches = [ref for ref in local if ref.split(":")[-1] == short]
    if len(matches) == 1:
        return "bundle", matches[0]
    if len(matches) > 1:
        return "missing", f"{name} matches {', '.join(matches)}; name one of them"
    return "missing", f"{name} is neither a project skill there nor a skill on this machine"


def resolve_all(loop, project_names, local, which=LOOPS):
    """Every stage skill of the given loops: name -> (source, value)."""
    out = {}
    for w in which:
        for s in loop.get(w, []):
            for name in s.get("skills", []):
                out.setdefault(name, resolve_skill(name, project_names, local))
    return out


ROUNDS = ("code-review", "scenario-retrace")


def assign(candidates, count):
    """Give `count` agents of one role a profile each, all different where the
    candidates allow, so two reviewers do not share one model's blind spots.
    Returns (profiles, warning or "")."""
    if not candidates:
        return [], "no profile for this role"
    picks = [candidates[i] if i < len(candidates) else candidates[-1] for i in range(count)]
    short = len(set(picks)) < count
    return picks, (f"only {len(set(picks))} different profile(s) for {count} agents; add a model with setup-foreman"
                   if short else "")


def render(cfg, task, difficulty, trivial, resolved, profiles, call_name):
    """The loop one lead follows, as Markdown for its brief.

    resolved: skill name -> (source, value); profiles: role -> candidate
    profiles in order (the role's tier first, then lower tiers);
    call_name(source, value) -> the name the agent calls it by.
    """
    from config import label
    loop = cfg["loop"]
    steps = plan(loop, difficulty, trivial)
    stage = {s["id"]: s["stage"] for s in steps}
    lines = [f"# Loop for {task} (difficulty {difficulty}{', trivial' if trivial else ''})", ""]
    ops = cfg["ops"]
    lines += [f"**Status**: a line at the start and end of every stage, naming the step, and at least every "
              f"{ops['report_minutes']} minutes; {ops['stall_minutes']} minutes without a line counts as a stall.", ""]
    missing = sorted({v for src, v in resolved.values() if src == "missing"})
    if missing:
        lines += ["**Missing skills** (go on without them and say so in your report):", ""]
        lines += [f"- {m}" for m in missing] + [""]
    lines += ["| # | Stage | Tab label | Step | Actor | Does | Skills | Next |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, s in enumerate(steps, 1):
        st = s["stage"]
        first = i == 1 or steps[i - 2]["stage"] != st
        tab = ""
        if first:
            rounds = any(x["id"] in ROUNDS for x in steps if x["stage"] == st)
            tab = "`" + label(cfg, st, task=task, stage=st + (" <N>" if rounds else ""), round="<N>" if rounds else "",
                              project=cfg.get("workspace", "")) + "`"
        actor = s["actor"] + (f" × {s['count']}" if s["count"] > 1 else "")
        skills = ", ".join(call_name(*resolved[n]) for n in s.get("skills", []) if resolved[n][0] != "missing") or "-"
        does = s["does"] + (f" {s['extra']}" if s["extra"] else "")
        nxt = "; ".join(f"{k} → {v}" + (f" ({stage[v]})" if v != STOP and stage[v] != st else "")
                        for k, v in s["next"].items())
        lines.append(f"| {i} | {st if first else ''} | {tab} | {s['id']} | {actor} | {does.replace('|', '/')} | "
                     f"{skills} | {nxt} |")
    acting = {}
    for s in steps:
        if s["actor"] not in PEOPLE:
            acting[s["actor"]] = max(acting.get(s["actor"], 1), s["count"])
    if acting:
        lines += ["", "| Role | Mode | Agents and profiles | Fallback | `launch.py` adds |", "| --- | --- | --- | --- | --- |"]
        for r, n in acting.items():
            picks, warning = assign(profiles.get(r, []), n)
            agents = "; ".join(f"agent {i}: {p}" for i, p in enumerate(picks, 1)) or "-"
            rest = [p for p in profiles.get(r, []) if p not in picks]
            deny = loop["roles"][r].get("deny_tools", [])
            flags = f"`--disallow {','.join(deny)}`" if deny else "-"
            lines.append(f"| {r} | {loop['roles'][r]['mode']} | {agents}{' (' + warning + ')' if warning else ''} | "
                         f"{', '.join(rest) or '-'} | {flags} |")
        for r in acting:
            key = loop["roles"][r].get("prompt")
            if key:
                lines += ["", f"## Prompt for {r}", "", loop["prompts"][key]]
    return "\n".join(lines) + "\n"


def _cli(argv):
    import adapters
    from config import (EXIT_SETUP_NEEDED, REPO, herdr_machines, load, local_skills, plugin_dirs, plugin_list,
                        role_tier, tier_profiles)
    ap = argparse.ArgumentParser(prog="loop.py", description="herdr-foreman loops")
    ap.add_argument("command", choices=["show", "skills", "render"])
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--loop", default="work", choices=LOOPS)
    ap.add_argument("--machine")
    ap.add_argument("--task")
    ap.add_argument("--difficulty", choices=LEVELS)
    ap.add_argument("--trivial", action="store_true", help="docs or text only, a typo, a rename with no behavior change")
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    args = ap.parse_args(argv)
    if args.project and not REPO.match(args.project):
        print(f"loop.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2
    cfg = load(args.project)
    problems = validate_loop(cfg.get("loop", {}))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return EXIT_SETUP_NEEDED

    if args.command == "show":
        loop = cfg["loop"]
        print("| Stage | Step | Actor | Does | Skills | Next | low | mid | high |\n"
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for s in loop.get(args.loop, []):
            cells = []
            for lv in LEVELS:
                run = s.get("run", {}).get(lv, "always")
                n = s.get("count", {}).get(lv)
                cells.append(run + (f" ×{n}" if n and n > 1 else ""))
            nxt = "; ".join(f"{k} → {v}" for k, v in s["next"].items())
            print(f"| {stage_of(s)} | {s['id']} | {s['actor']} | {s['does'][:60].replace('|', '/')} | "
                  f"{', '.join(s.get('skills', [])) or '-'} | {nxt} | {' | '.join(cells)} |")
        return 0

    if not (args.project and args.machine):
        print("loop.py: skills and render need --project and --machine", file=sys.stderr)
        return 2
    machines = cfg.get("machines", {})
    if args.machine not in machines:
        print(f"loop.py: {args.machine} is not one of the project's machines ({', '.join(machines) or 'none'})",
              file=sys.stderr)
        return EXIT_SETUP_NEEDED
    project_names = project_skill_names(args.machine, machines[args.machine],
                                        None if args.machine == "local" else herdr_machines())
    local = local_skills(plugin_list(plugin_dirs(cfg)))
    resolved = resolve_all(cfg["loop"], project_names, local)
    if args.command == "skills":
        print(json.dumps({"machine": args.machine, "project_skills": project_names,
                          "skills": {k: {"source": v[0], "value": v[1]} for k, v in resolved.items()}}, indent=2))
        return 0

    if not (args.task and args.difficulty):
        print("loop.py: render needs --task and --difficulty", file=sys.stderr)
        return 2
    adapter = adapters.get(args.agent)
    def candidates(role):
        """The role's tier first, then each lower tier, without repeats."""
        from config import TIERS
        top = TIERS.index(role_tier(args.difficulty, role, cfg))
        out = []
        for tier in reversed(TIERS[:top + 1]):
            out += [p for p in tier_profiles(cfg, tier) if p not in out]
        return out

    profiles = {r: candidates(r) for r in cfg["loop"]["roles"]}

    def call_name(source, value):
        return value if source == "project" else adapter.skill_name(value)

    print(render(cfg, args.task, args.difficulty, args.trivial, resolved, profiles, call_name), end="")
    for src, value in resolved.values():
        if src == "missing":
            print(f"loop.py: missing skill: {value}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
