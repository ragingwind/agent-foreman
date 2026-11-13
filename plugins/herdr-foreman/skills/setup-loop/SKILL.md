---
name: setup-loop
description: >-
  Design herdr-foreman's loops: the stages of the work loop (one issue, one
  pull request) and the steps in each, the foreman's management loop and the
  epic batch loop; who acts in each step; the skills each step uses (the
  project's own skills first, then the person's); and how the work loop
  changes with a task's difficulty (which steps run, how many reviewers).
  Saves the standard for every project, or a change for one project. Use for
  /setup-loop, to name or regroup the stages, to map a skill to a step, to
  add or remove a step, or to change what a difficulty runs.
---

# setup-loop

A loop is a list of steps: who acts, what it does, the skills it uses, and
where each outcome goes. Consecutive steps with the same `stage` form a
stage; tab labels, status lines and reports follow the stages. The standard
loops come with the package; the person's settings and a project's settings
store only their changes, step by step.

`<hf>` is the herdr-foreman skill's directory: `../herdr-foreman` from this
file. Run its scripts with `python3`.

## 1. Detect

- `python3 <hf>/scripts/loop.py show [--project <repo>] --loop work` (and
  `manage`, `epic`): each step with its stage, actor, skills and next step,
  and what runs at low, mid and high.
- Skill candidates:
  - the project's own skills on one of its machines, and where each current
    step's skill would come from:
    `python3 <hf>/scripts/loop.py skills --project <repo> --machine <label>`;
  - the person's skills: `python3 <hf>/scripts/config.py skills`.

## 2. Show and ask once

Show the work loop's table. Ask with AskUserQuestion, two questions in one
call:

- **Scope**: the standard for every project (the person's settings), or this
  project only.
- **What to change** (multi-select): stage names and which steps each
  holds; skills per step; steps (add or remove); what each difficulty runs;
  a role's mode or prompt; nothing.

Go into the chosen parts only.

## 3. Change

- **Stages**: show the steps in order with what each does, and let the
  person type each stage's name and the steps it holds (as
  `<name> <first>-<last>` by row number). Write the name into each of its
  steps' `stage`. A stage's steps stay together, and a stage may not take the
  name of a step in another stage; step ids stay as they are. Labels per
  stage (`labels.events`) move to the new names.
- **Skills per step**: for each step the person picks, offer the project's
  skills first, then the person's. Save the bare name (`cross-check-scenario`);
  where it comes from is decided per machine when a task starts. Save the full
  `plugin:skill` only when the bare name matches more than one of the
  person's skills.
- **Steps**: a new step needs an `id`, its `stage`, an `actor` (`lead`,
  `foreman`, `person`, or a role), what it `does`, its `skills`, and `next`
  (each outcome to a step id or `stop`; the last outcome is the success
  path). It goes after an existing step (`"after": "<id>"`). A step is
  removed with `{"id": "<id>", "remove": true}`. The order of existing steps
  stays.
- **Difficulty**: per step, `run` at low, mid and high (`always`, `never`,
  `if-not-trivial`), `count` (how many agents, for a role's step) and
  `extra` (an added instruction). A stage whose steps all do not run is
  skipped.
- **Roles**: `mode` (`prompt` or `pane`), `step` (tiers above the lead's), and
  the fixed prompt. A judging prompt must keep the `Verdict:` line and the
  comment title with the head SHA; the gate reads both.

## 4. Validate and write

Take the settings in effect (`config.py show [--project <repo>]`), change
them, and pass the whole object; only the changed steps are stored:

```bash
python3 <hf>/scripts/config.py save user --dry-run < <file>
python3 <hf>/scripts/config.py save project --project <repo> --dry-run < <file>
```

On a non-zero exit, fix the printed problems with the person. On exit 0,
`written` shows each changed step by its `id`. Then run it without
`--dry-run`.

## 5. Confirm

Show `loop.py show` again and one task's loop:
`python3 <hf>/scripts/loop.py render --project <repo> --task <N> --difficulty mid --machine <label>`.
For each skill it lists as missing:

- a person's skill that the machine lacks is installed with the bundle: offer
  `python3 <hf>/scripts/bundle.py push <label> --project <repo>`;
- a name found nowhere is a typo or a skill to write; say which.
