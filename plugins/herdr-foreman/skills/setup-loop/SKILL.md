---
name: setup-loop
description: >-
  Design herdr-foreman's loops: the stages of the work loop (one issue, one
  pull request), the foreman's management loop and the epic batch loop; who
  acts in each stage; the skills each stage uses (the project's own skills
  first, then the person's); and how the work loop changes with a task's
  difficulty (which stages run, how many reviewers). Saves the standard for
  every project, or a change for one project. Use for /setup-loop, to map a
  skill to a stage, to add or remove a stage, or to change what a difficulty
  runs.
---

# setup-loop

A loop is a list of stages, each an event: who acts, what it does, the skills
it uses, and where each outcome goes. The standard loops come with the
package; the person's settings and a project's settings store only their
changes, stage by stage.

`<hf>` is the herdr-foreman skill's directory: `../herdr-foreman` from this
file. Run its scripts with `python3`.

## 1. Detect

- `python3 <hf>/scripts/loop.py show [--project <repo>] --loop work` (and
  `manage`, `epic`): the stages, their actors, skills and next stages, and
  what runs at low, mid and high.
- Skill candidates:
  - the project's own skills on one of its machines, and where each current
    stage skill would come from:
    `python3 <hf>/scripts/loop.py skills --project <repo> --machine <label>`;
  - the person's skills: `python3 <hf>/scripts/config.py skills`.

## 2. Show and ask once

Show the work loop's table. Ask with AskUserQuestion, two questions in one
call:

- **Scope**: the standard for every project (the person's settings), or this
  project only.
- **What to change** (multi-select): skills per stage; stages (add or
  remove); what each difficulty runs; a role's mode or prompt; nothing.

Go into the chosen parts only.

## 3. Change

- **Skills per stage**: for each stage the person picks, offer the project's
  skills first, then the person's. Save the bare name (`cross-check-scenario`);
  where it comes from is decided per machine when a task starts. Save the full
  `plugin:skill` only when the bare name matches more than one of the
  person's skills.
- **Stages**: a new stage needs an `id`, an `actor` (`lead`, `foreman`,
  `person`, or a role), what it `does`, its `skills`, and `next` (each outcome
  to a stage id or `stop`; the last outcome is the success path). It goes
  after an existing stage (`"after": "<id>"`). A stage is removed with
  `{"id": "<id>", "remove": true}`. The order of existing stages stays.
- **Difficulty**: per stage, `run` at low, mid and high (`always`, `never`,
  `if-not-trivial`), `count` (how many agents, for a role's stage) and
  `extra` (an added instruction).
- **Roles**: `mode` (`prompt` or `pane`), `step` (tiers above the lead's), and
  the fixed prompt. A judging prompt must keep the `Verdict:` line and the
  comment title with the head SHA; the gate reads both.

## 4. Validate and write

Take the settings in effect (`config.py show [--project <repo>]`), change
them, and pass the whole object; only the changed stages are stored:

```bash
python3 <hf>/scripts/config.py save user --dry-run < <file>
python3 <hf>/scripts/config.py save project --project <repo> --dry-run < <file>
```

On a non-zero exit, fix the printed problems with the person. On exit 0,
`written` shows each changed stage by its `id`. Then run it without
`--dry-run`.

## 5. Confirm

Show `loop.py show` again and one task's loop:
`python3 <hf>/scripts/loop.py render --project <repo> --task <N> --difficulty mid --machine <label>`.
For each skill it lists as missing:

- a person's skill that the machine lacks is installed with the bundle: offer
  `python3 <hf>/scripts/bundle.py push <label> --project <repo>`;
- a name found nowhere is a typo or a skill to write; say which.
