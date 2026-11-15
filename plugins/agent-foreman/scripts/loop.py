#!/usr/bin/env python3
"""Loops: stages made of steps, the roles that act in them, their skills, and
how they change with a task's difficulty.

Settings shape (`loop` in the settings):

  roles    name -> {"mode": "prompt"|"pane", "step": 0|1, "prompt": key, "deny_tools": [...],
                   "accept": [passing verdicts]}
  prompts  key -> fixed prompt text a role gets; `loop.py prompt` fills in
           <task>, <repo>, <base>, <head>, <diff>, <task folder>, <skill>,
           <skills>, <full test command> and <trivial>
  work     the build session's steps (one task, one pull request), run by a lead
  check    the verification session's steps, started by the foreman once the
           lead is ready; an outcome may send the task back to a work step
  manage   the foreman's loop
  epic     the batch loop before an epic goes to main

A step's "skills" name what it uses. A default skill (KIT) is the one
agent-foreman ships in the bundle, unless the settings' `skills` map names a
project or local skill that replaces it; the replacement changes only how
the action is done, never the flow or the record.

A loop is a list of steps. A step: {"id", "stage", "actor", "does",
"skills": [...], "next": {outcome: step id or "stop"}, and optionally "run":
{difficulty: "always"|"never"|"if-not-trivial"}}. "if-not-trivial" runs unless the foreman
marked the task trivial: docs or text only, a typo, or a rename that changes
no behavior. The last outcome in "next" is the success path, and from the
work loop's first step and from each check step it must reach "stop"; a step
that does not run for a task passes straight to its success path.

A stage is a run of consecutive steps with the same "stage"; a step without
one is a stage of its own. Tab labels, status lines and reports follow the
stages; the rules above stay on the steps. A stage whose steps all do not
run for a task is skipped.

Usage:
  loop.py show [--project OWNER/REPO] [--loop work|check|manage|epic]
  loop.py skills --project OWNER/REPO --machine MACHINE
  loop.py render --project OWNER/REPO --task N --difficulty low|mid|high --machine MACHINE
                 [--base BRANCH] [--lead PROFILE] [--loop work|check] [--trivial] [--agent KIND] [--json]
  loop.py prompt --step ID [--task-dir DIR] [--agent NAME]

`render --json` prints the task's loop as data: its work and check steps,
the base, the lead's profile (--lead, the one the lead really runs on; by
default the first of its tier), and each role's prompt and profiles. The
foreman saves it as `loop.json` in the task folder; `status.py note` checks
each status line against it, `gate.py template` builds the gate from it, and
`prompt` starts role agents from it, so a task keeps the settings it started
with.

`prompt`, run in a role agent's own clone, writes that agent's next prompt
into the task folder's reviews/ (`<agent>-<n>.prompt.md`), filled in from
loop.json and the clone's head, and prints the launch.py commands that run it:
the first profile, then each fallback for exit 5. --task-dir defaults to
AF_TASK_DIR, --agent to `<role>-1`. A step that follows an earlier step of the
same role (the pair's recheck) gets only the diff since that agent's last
answer.

Exit codes: 2 = bad arguments, 3 = setup needed.
"""
import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys

LEVELS = ["low", "mid", "high"]
LOOPS = ["work", "check", "manage", "epic"]
# The default skills agent-foreman ships (kit/skills/<name>), one per loop action.
KIT = ["work-breakdown", "cross-check", "tdd", "unit", "commit", "smoke", "review", "simplify", "handoff",
       "redteam-review", "full"]
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
        targets = ids + (step_ids(loop) if which == "check" else [])
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
                    if target != STOP and target not in targets:
                        problems.append(f"{where}: outcome {outcome} goes to {target!r}, which is not a step")
            table = s.get("run", {})
            if not isinstance(table, dict):
                problems.append(f"{where}: run must map difficulties to values")
                continue
            for level, value in table.items():
                if level not in LEVELS:
                    problems.append(f"{where}: run names {level!r}; use {', '.join(LEVELS)}")
                elif value not in RUNS:
                    problems.append(f"{where}: run for {level} must be one of {', '.join(RUNS)}")
    return problems or success_problems(loop)


def success_problems(loop):
    """A loop whose success path (each step's last outcome) does not reach
    stop: from the work loop's first step, and from each check step."""
    problems = []
    for which in ("work", "check"):
        steps = {s["id"]: s for s in loop.get(which, [])}
        for start in (list(steps)[:1] if which == "work" else list(steps)):
            at, seen = start, set()
            while at in steps and at not in seen:
                seen.add(at)
                at = list(steps[at]["next"].values())[-1]
            if at != STOP:
                problems.append(f"loop: {which}: the success path from {start} (each step's last outcome) "
                                f"does not reach stop")
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
    that do not run, and each step's stage."""
    steps = loop.get(which, [])
    runs = {}
    for s in steps:
        rule = s.get("run", {}).get(difficulty, "always")
        runs[s["id"]] = rule == "always" or (rule == "if-not-trivial" and not trivial)
    by_id = {s["id"]: s for s in steps}

    def land(target, seen=()):
        while target != STOP and target in runs and not runs[target]:  # a target in another loop stays as it is
            if target in seen:
                raise ValueError(f"loop: skipped steps form a cycle at {target}")
            seen = seen + (target,)
            target = list(by_id[target]["next"].values())[-1]
        return target

    out = []
    for s in steps:
        if not runs[s["id"]]:
            continue
        item = {k: v for k, v in s.items() if k != "run"}
        item["stage"] = stage_of(s)
        item["next"] = {k: land(v) for k, v in s["next"].items()}
        out.append(item)
    return out


def shell_path(path):
    """`path` quoted for a remote shell. A leading `~` stays outside the quotes
    so the remote shell expands it: saved machine paths are written with `~`."""
    if path == "~" or path.startswith("~/"):
        return '"$HOME"' + shlex.quote(path[1:])
    return shlex.quote(path)


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
    probe = f"cd {shell_path(path)}/.claude/skills 2>/dev/null && for d in */; do test -f \"$d/SKILL.md\" && echo \"${{d%/}}\"; done; true"
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


def resolve(name, project_names, local, overrides=None):
    """Where one step skill comes from. A default skill is ("kit", name) unless
    `overrides` (the settings' `skills`) names a skill that replaces it; any
    other name is looked up as resolve_skill does."""
    if name in KIT:
        replacement = (overrides or {}).get(name)
        return resolve_skill(replacement, project_names, local) if replacement else ("kit", name)
    return resolve_skill(name, project_names, local)


def resolve_all(loop, project_names, local, which=LOOPS, overrides=None):
    """Every step skill of the given loops: name -> (source, value)."""
    out = {}
    for w in which:
        for s in loop.get(w, []):
            for name in s.get("skills", []):
                out.setdefault(name, resolve(name, project_names, local, overrides))
    return out


def has_rounds(steps, stage):
    """Whether a stage repeats: one of its steps sends the task back to an
    earlier step."""
    order = [s["id"] for s in steps]
    return any(t != STOP and t in order and order.index(t) < order.index(s["id"])
               for s in steps if s["stage"] == stage for t in s["next"].values())


def stage_labels(cfg, task, steps):
    """The tab label of each stage, with `<N>` for the round where it repeats."""
    from config import label
    out = {}
    for s in steps:
        st = s["stage"]
        if st not in out:
            rounds = has_rounds(steps, st)
            out[st] = label(cfg, st, task=task, stage=st + (" <N>" if rounds else ""), round="<N>" if rounds else "",
                            project=cfg.get("workspace", ""))
    return out


def as_data(cfg, task, difficulty, trivial, resolved, call_name, repo, base, lead, profiles):
    """A task's loop as data, for `loop.json` in its task folder: the work
    and check steps that run, and what the role prompts and the gate need.
    profiles: role -> candidate profiles in order (config.role_candidates)."""
    loop = cfg["loop"]
    out = {"repo": repo, "task": task, "base": base, "difficulty": difficulty, "trivial": trivial,
           "lead_profile": lead, "tests_full": cfg.get("tests", {}).get("full"),
           "max_lines": cfg["difficulty"]["lines"], "roles": {}}
    for which in ("work", "check"):
        steps = plan(loop, difficulty, trivial, which)
        labels = stage_labels(cfg, task, steps)
        out[which] = [{"id": s["id"], "stage": s["stage"], "label": labels[s["stage"]], "actor": s["actor"],
                       "does": s["does"],
                       "skills": [call_name(*resolved[n]) for n in s.get("skills", []) if resolved[n][0] != "missing"],
                       "next": s["next"]} for s in steps]
        for s in steps:
            r = s["actor"]
            if r in loop["roles"] and r not in out["roles"]:
                role = loop["roles"][r]
                out["roles"][r] = {"mode": role["mode"], "prompt": loop["prompts"].get(role.get("prompt"), ""),
                                   "accept": role.get("accept", ["approved"]),
                                   "deny_tools": role.get("deny_tools", []), "profiles": profiles.get(r, [])}
    return out


def last_run(task_dir, agent):
    """(meta, answer file) of an agent's latest finished run in the task
    folder's reviews/, or None."""
    best = None
    for meta_file in glob.glob(os.path.join(task_dir, "reviews", "*.meta.json")):
        try:
            with open(meta_file, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and meta.get("agent") == agent and meta.get("ok") is True and (
                best is None or str(meta.get("ended", "")) > str(best[0].get("ended", ""))):
            best = (meta, meta_file[:-len(".meta.json")] + ".json")
    return best


def role_run(task_loop, task_dir, step_id, agent, head, launch):
    """One run of a role agent: {"agent", "text", "prompt", "out", "commands"},
    the launch commands in the order to try. Raises ValueError for a step no role agent
    runs, a role with no profile, or a re-check with nothing to check against."""
    for which in ("work", "check"):
        steps = task_loop.get(which, [])
        step = next((s for s in steps if s["id"] == step_id), None)
        if step:
            break
    else:
        ids = [s["id"] for w in ("work", "check") for s in task_loop.get(w, [])]
        raise ValueError(f"step {step_id!r} is not in this task's loop; its steps are {', '.join(ids)}")
    r = step["actor"]
    role = task_loop.get("roles", {}).get(r)
    if role is None:
        raise ValueError(f"step {step_id} is done by the {r}, not by a role agent")
    agent = agent or f"{r}-1"
    if not NAME.match(agent):
        raise ValueError(f"--agent may hold letters, digits, '.', '_' and '-' only, not {agent!r}")
    candidates = role.get("profiles", [])
    if not candidates:
        raise ValueError(f"role {r} has no profile other than the lead's; add one with /agent-foreman:agent-foreman setup")
    base = task_loop["base"]
    diff = f"from origin/{base} to HEAD"
    earlier = [s["id"] for s in steps[:steps.index(step)] if s["actor"] == r]
    if earlier:
        found = last_run(task_dir, agent)
        if found is None:
            raise ValueError(f"{agent} has no earlier answer to check against; run step {earlier[-1]} first")
        diff = (f"from {found[0].get('head')} to HEAD: only the fixes and the clean-up since your last review, "
                f"whose answer is {found[1]}")
    values = {"task": task_loop["task"], "repo": task_loop["repo"], "base": base, "head": head, "diff": diff,
              "task folder": task_dir, "skill": ", ".join(step["skills"]), "skills": ", ".join(step["skills"]),
              "full test command": task_loop.get("tests_full") or "none is set; write `not run: no full test command`",
              "trivial": "yes" if task_loop.get("trivial") else "no"}
    text = role["prompt"]
    for key, value in values.items():
        text = text.replace(f"<{key}>", value)
    reviews = os.path.join(task_dir, "reviews")
    taken = [int(m.group(1)) for p in glob.glob(os.path.join(reviews, f"{glob.escape(agent)}-*.prompt.md"))
             for m in [re.search(r"-(\d+)\.prompt\.md$", p)] if m]
    n = max(taken, default=0) + 1
    prompt_file, out = os.path.join(reviews, f"{agent}-{n}.prompt.md"), os.path.join(reviews, f"{agent}-{n}.json")
    m = re.search(r"-(\d+)$", agent)
    first = (int(m.group(1)) - 1) % len(candidates) if m else 0
    deny = role.get("deny_tools", [])
    commands = [shlex.join(["python3", launch, p, "--print", "--role", r, "--name", agent, "--task-dir", task_dir,
                            "--prompt-file", prompt_file, "--out", out] + (["--disallow", ",".join(deny)] if deny else []))
                for p in candidates[first:] + candidates[:first]]
    return {"agent": agent, "text": text, "prompt": prompt_file, "out": out, "commands": commands}


def render(cfg, task, difficulty, trivial, resolved, profiles, call_name, which="work"):
    """One loop of a task, as Markdown: the work loop for the lead's brief, or
    the check loop for the foreman.

    resolved: skill name -> (source, value); profiles: role -> candidate
    profiles in order (config.role_candidates); call_name(source, value) ->
    the name the agent calls it by.
    """
    loop = cfg["loop"]
    steps = plan(loop, difficulty, trivial, which)
    stage = {s["id"]: s["stage"] for s in steps}
    labels = stage_labels(cfg, task, steps)
    title = "Loop" if which == "work" else "Verification session"
    lines = [f"# {title} for {task} (difficulty {difficulty}{', trivial' if trivial else ''})", ""]
    ops = cfg["ops"]
    lines += [f"**Status**: a `start` and an `end` line for every step you run (`status.py note`, as loop.md says), "
              f"and a `progress` line at least every {ops['report_minutes']} minutes in a long step; "
              f"{ops['stall_minutes']} minutes without a line counts as a stall.", ""]
    missing = sorted({v for src, v in resolved.values() if src == "missing"})
    if missing:
        lines += ["**Missing skills** (go on without them and say so in your report):", ""]
        lines += [f"- {m}" for m in missing] + [""]
    lines += ["| # | Stage | Tab label | Step | Actor | Does | Skills | Next |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, s in enumerate(steps, 1):
        st = s["stage"]
        first = i == 1 or steps[i - 2]["stage"] != st
        tab = f"`{labels[st]}`" if first else ""
        skills = ", ".join(call_name(*resolved[n]) for n in s.get("skills", []) if resolved[n][0] != "missing") or "-"
        nxt = "; ".join(f"{k} → {v}" + (f" ({stage[v]})" if v in stage and stage[v] != st else "")
                        + (" (build session)" if v != STOP and v not in stage else "")
                        for k, v in s["next"].items())
        lines.append(f"| {i} | {st if first else ''} | {tab} | {s['id']} | {s['actor']} | {s['does'].replace('|', '/')} | "
                     f"{skills} | {nxt} |")
    acting = list(dict.fromkeys(s["actor"] for s in steps if s["actor"] not in PEOPLE))
    if acting:
        lines += ["", "| Role | Mode | Profile | Fallback (never the lead's) |", "| --- | --- | --- | --- |"]
        for r in acting:
            candidates = profiles.get(r, [])
            lines.append(f"| {r} | {loop['roles'][r]['mode']} | {candidates[0] if candidates else '- (no profile for this role)'} | "
                         f"{', '.join(candidates[1:]) or '-'} |")
        lines += ["", "Start a role's agent with `loop.py prompt --step <step>` from the agent's own clone: it "
                      "writes the prompt from loop.json and prints the commands to run, as loop.md says."]
    return "\n".join(lines) + "\n"


def prompt_cli(args):
    task_dir = args.task_dir or os.environ.get("AF_TASK_DIR")
    if not (args.step and task_dir):
        print("loop.py: prompt needs --step and a task folder (--task-dir or AF_TASK_DIR)", file=sys.stderr)
        return 2
    task_dir = os.path.abspath(os.path.expanduser(task_dir))
    try:
        with open(os.path.join(task_dir, "loop.json"), encoding="utf-8") as f:
            task_loop = json.load(f)
    except (OSError, ValueError) as e:
        print(f"loop.py: no readable loop.json in {task_dir}: {e}", file=sys.stderr)
        return 2
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        print("loop.py: run prompt in the role agent's own clone; this directory is not a git checkout",
              file=sys.stderr)
        return 2
    launch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launch.py")
    try:
        found = role_run(task_loop, task_dir, args.step, args.agent, head.stdout.strip(), launch)
    except (ValueError, KeyError) as e:
        print(f"loop.py: {e}", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(found["prompt"]), exist_ok=True)
    with open(found["prompt"], "w", encoding="utf-8") as f:
        f.write(found.pop("text") + "\n")
    print(json.dumps({"step": args.step, **found}, indent=2))
    return 0


def _cli(argv):
    ap = argparse.ArgumentParser(prog="loop.py", description="agent-foreman loops")
    ap.add_argument("command", choices=["show", "skills", "render", "prompt"])
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--loop", default="work", choices=LOOPS)
    ap.add_argument("--machine")
    ap.add_argument("--task")
    ap.add_argument("--difficulty", choices=LEVELS)
    ap.add_argument("--trivial", action="store_true", help="docs or text only, a typo, a rename with no behavior change")
    ap.add_argument("--base", help="render --json: the branch the task starts from and merges into")
    ap.add_argument("--lead", metavar="PROFILE", help="render: the profile the lead runs on")
    ap.add_argument("--json", action="store_true", help="render: the task's loop as data, for loop.json")
    ap.add_argument("--step", help="prompt: the step a role agent runs")
    ap.add_argument("--task-dir", help="prompt: the task folder (default: AF_TASK_DIR)")
    ap.add_argument("--agent", help="render: the agent kind; prompt: the role agent's name (default <role>-1)")
    args = ap.parse_args(argv)
    if args.command == "prompt":
        return prompt_cli(args)

    import adapters
    from config import (EXIT_SETUP_NEEDED, REPO, herdr_machines, lead_profile, load, local_skills, plugin_dirs,
                        plugin_list, role_candidates)
    kind = args.agent or adapters.DEFAULT
    if kind not in adapters.KINDS:
        print(f"loop.py: --agent must be one of {', '.join(adapters.KINDS)} for {args.command}", file=sys.stderr)
        return 2
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
            cells = [s.get("run", {}).get(lv, "always") for lv in LEVELS]
            nxt = "; ".join(f"{k} → {v}" for k, v in s["next"].items())
            print(f"| {stage_of(s)} | {s['id']} | {s['actor']} | {s['does'].replace('|', '/')} | "
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
    resolved = resolve_all(cfg["loop"], project_names, local, overrides=cfg.get("skills", {}))
    if args.command == "skills":
        print(json.dumps({"machine": args.machine, "project_skills": project_names,
                          "skills": {k: {"source": v[0], "value": v[1]} for k, v in resolved.items()}}, indent=2))
        return 0

    if not (args.task and args.difficulty):
        print("loop.py: render needs --task and --difficulty", file=sys.stderr)
        return 2
    if args.json and not args.base:
        print("loop.py: render --json needs --base, the branch the task starts from", file=sys.stderr)
        return 2
    lead = args.lead or lead_profile(cfg, args.difficulty)
    if lead not in cfg["profiles"]:
        print(f"loop.py: --lead {lead!r} is not a profile", file=sys.stderr)
        return 2
    adapter = adapters.get(kind)
    profiles = {r: role_candidates(cfg, args.difficulty, r, lead=lead) for r in cfg["loop"]["roles"]}

    def call_name(source, value):
        return value if source == "project" else adapter.skill_name(value)

    if args.json:
        print(json.dumps(as_data(cfg, args.task, args.difficulty, args.trivial, resolved, call_name, args.project,
                                 args.base, lead, profiles), indent=2))
    else:
        which = args.loop if args.loop in ("work", "check") else "work"
        print(render(cfg, args.task, args.difficulty, args.trivial, resolved, profiles, call_name, which), end="")
    for src, value in resolved.values():
        if src == "missing":
            print(f"loop.py: missing skill: {value}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
