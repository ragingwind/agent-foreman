# Part: loop

The build session's loop (`work`) and the verification session's loop
(`check`): their stages and steps, who acts in each step, the skill each step
uses, and how the loops change with a task's difficulty. Also the foreman's
management loop and the epic loop. Saved at the person's level (every
project) or a project's.

Each step's action is a default skill (`kit/skills/<name>`). The settings'
`skills` map can replace one with a project or local skill
(`{"skills": {"cross-check": "scenario-check"}}`); the replacement changes how
the action is done, and the default skill's flow and record still apply.

A loop is a list of steps: who acts, what it does, the skills it uses, and
where each outcome goes. Consecutive steps with the same `stage` form a
stage; tab labels, status lines and reports follow the stages.

## 1. Detect

- `python3 <skill>/scripts/loop.py show [--project <repo>] --loop work` (and
  `manage`, `epic`): each step with its stage, actor, skills and next step,
  and what runs at low, mid and high.
- Skill candidates:
  - the project's own skills on one of its machines, and where each current
    step's skill would come from:
    `python3 <skill>/scripts/loop.py skills --project <repo> --machine <label>`;
  - the person's skills: `python3 <skill>/scripts/config.py skills`;
  - plugin directories this session loads that the settings do not have
    yet: `python3 <skill>/scripts/config.py plugin-dir-candidates`, then their
    skills, before anything is saved: `python3 <skill>/scripts/config.py skills
    --plugin-dir <dir>` (repeat the option for each). Scripts start a bare
    `claude`, so they find those skills only through `plugin_dirs`.

## 2. Show and ask once

Show the work loop's table. Ask with AskUserQuestion, two questions in one
call:

- **Scope**: the standard for every project (the person's settings), or this
  project only.
- **What to change** (multi-select): stage names and which steps each
  holds; skills per step; steps (add or remove); what each difficulty runs;
  a role's mode or prompt.

Go into the chosen parts only.

## 3. Change

- **Stages**: show the steps in order with what each does, and let the
  person type each stage's name and the steps it holds (as
  `<name> <first>-<last>` by row number). Write the name into each of its
  steps' `stage`. A stage's steps stay together, and a stage may not take the
  name of a step in another stage; step ids stay as they are. Labels per
  stage (`labels.events`) move to the new names.
- **Replace a default skill**: for each default skill the person picks,
  offer the project's skills first, then the person's, and save the choice in
  `skills` (`"<default name>": "<skill>"`). Remove the entry to go back to the
  default.
- **Skills per step**: an extra skill a step uses besides its default one.
  For each step the person picks, offer the project's skills first, then the
  person's. Save the bare name (`scenario-check`);
  where it comes from is decided per machine when a task starts. Save the full
  `plugin:skill` only when the bare name matches more than one of the
  person's skills. A skill from a plugin directory found in step 1 adds
  that directory to the person's `plugin_dirs`.
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
  the fixed prompt. A judging prompt must keep its `Verdict:` line: the gate
  reads the last one in the answer that `launch.py --role` saves in the task
  folder.

## 4. Save

At the scope the person chose (`SKILL.md` "Save"); `written` shows each
changed step by its `id`. Then show `loop.py show` again and one task's loop:
`python3 <skill>/scripts/loop.py render --project <repo> --task <N> --difficulty
mid --machine <label>`. For each skill it lists as missing:

- a person's skill that the machine lacks is installed with the bundle: offer
  `python3 <skill>/scripts/bundle.py push <label> --project <repo>`;
- a name found nowhere is a typo or a skill to write; say which.
