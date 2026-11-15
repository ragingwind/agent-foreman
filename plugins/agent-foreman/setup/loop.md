# Part: loop

The build session's loop (`work`) and the verification session's loop
(`check`): their stages and steps, who acts in each step, the skill each step
uses, and how the loops change with a task's difficulty. Also the foreman's
management loop and the epic loop, and the project's own gate checks. Saved
at the person's level (every project) or a project's.

Each step's action is a default skill (`kit/skills/<name>`). A project's or
the person's skill takes a step at one of three levels:

| Level | What it does | Saved as |
| --- | --- | --- |
| Replace the action | Does the default skill's work its own way. The default skill's flow (the outcome to end with) and record (what to write in the task folder) still apply; the brief shows both, as `cross-e2e (flow and record: foreman-kit:cross-check)` | `skills`: `{"cross-check": "cross-e2e"}` |
| Add to the step | Runs beside the default skill, such as the project's review criteria for the pair | the step's `skills` |
| Run the step | An orchestrator that does several things itself, such as a project skill that implements an issue up to a pull request, in `build` | the step's `does` and `skills`: run it up to its stop before merge, with its non-interactive options, then do what it does not (each `plan.md` row marked done with its commit, `progress` lines while its own agents work) |

No skill takes over a whole loop or stage: the gate needs every step's `end`
line and the task folder's records, and the verdicts before ready come from
other models.

A loop is a list of steps: who acts, what it does, the skills it uses, and
where each outcome goes. Consecutive steps with the same `stage` form a
stage; tab labels, status lines and reports follow the stages.

## 1. Detect

- `python3 <skill>/scripts/loop.py show [--project <repo>] --loop work` (and
  `check`): each step with its stage, actor, skills and next step,
  and what runs at low, mid and high.
- Skill candidates:
  - the project's own skills and commands (`.claude/skills/*`,
    `.claude/commands/*.md`) on one of its machines, and where each current
    step's skill would come from:
    `python3 <skill>/scripts/loop.py skills --project <repo> --machine <label>`;
  - the person's skills: `python3 <skill>/scripts/config.py skills`;
  - plugin directories this session loads that the settings do not have
    yet, and plugins installed on this machine but not enabled here (such as
    one installed for another project):
    `python3 <skill>/scripts/config.py plugin-dir-candidates`, then their
    skills, before anything is saved: `python3 <skill>/scripts/config.py skills
    --plugin-dir <dir>` (repeat the option for each). Scripts start a bare
    `claude`, so they find those skills only through `plugin_dirs`.
- What each candidate does: read its `SKILL.md` (a command's file) whole, not
  only its description: a project's at `<checkout>/.claude/...` on that
  machine, a person's at the path `config.py skills` prints.
- The project's guides: `CLAUDE.md`, `AGENTS.md`, its rules folder, its
  contributing file, its CI files, and its `Makefile` or `package.json`
  scripts. Note each rule they state for a step: branch names, commit format,
  the tests to run, how and by whom a pull request merges, which changes the
  person approves.

## 2. Fit each step

Always, also when no one asked for it. For each step of `work` and `check`,
and for the foreman's register and merge steps, in this order:

1. **The project has a skill or command for it** (the same name, or the same
   work): a candidate, at the level that fits.
2. **The project has none**: ask with AskUserQuestion whether to look in the
   person's own skills (`Search my skills`, recommended; `Keep the
   default`). On search, ask which skills they mostly use for this kind of
   work (multi-select: the person's skills found in "1. Detect" that come
   closest, closest first), read the chosen ones, and fit them the same way.
3. **No skill, but the guides state a rule for the step**: a line in the
   step's `does`, a project gate check ("4. Project gate"), or a line in the
   project's `memory.md` (the merge method; the person-approval classes as
   `difficulty` patterns, so those tasks are high and the person merges).
4. **Nothing**: the default skill.

Check each candidate against this list, and show what it found:

| The candidate | The rule |
| --- | --- |
| merges a pull request | Bound to no step: the foreman merges after the gate, and every agent is denied `gh pr merge`. Its merge method goes in `memory.md` |
| makes worktrees, or needs the primary checkout on the default branch | Bound to no step: each agent works in its own clone |
| starts its own reviewers or testers | An overlap ("3. Overlaps") |
| pushes after the pair's review | Only in a step before `review`: a later push moves the head, and the verdicts must be at the head |
| asks the person midway | Bound with its non-interactive options in `does`; a question it still asks is a decision stop |
| writes labels or pull request comments | Allowed, as the project's own records; a label is never a verdict |
| calls a script by a path under `~` | Test that path on each machine; a missing one is the person's to fix |

Then ask with AskUserQuestion, one question per step with a candidate, up to
four per call: `Keep: <what it uses now>` first, then each candidate with its
level and where it comes from. Recommend the candidate that fits with no
conflict when the step still has the default nobody chose; else `Keep`.

## 3. Overlaps

A bound skill may do work another step also does: its own reviewers and the
pair's review, its own brief and `plan`, its own finalizer and `finalize`, its
own test run and `verify`. Show every overlap in one table: the two, what
each does, and the cost of each choice (time, tokens, what is lost). Then ask
with AskUserQuestion, one question per overlap: keep one (recommended: the
one that does the work better, so it is done once), or keep both.

The verdicts other models give (the pair, the red team, QA) stay in every
option. When the project's review is the better one, it becomes the role's
skill (the `skills` of `review` and `recheck`), so the review runs once, on
another model. A project's QA procedure becomes the QA role's skill the same
way. A role agent reads such a skill as the base branch has it (`clone.py
make --instructions-from`), so the change under review cannot rewrite it.

## 4. Project gate

The standard gate always runs (`ARCHITECTURE.md` "8. Gates"). The project adds
checks of its own: scripts it has for a pull request (a closing-keyword or a
body-format check), checks its guides require that CI does not run (a lint or
format check that writes nothing), a label its skills set. Each is a named
command check in the project's `gate`:

```json
"gate": [
  {"check": "command", "name": "pr-body", "from_base": "scripts/check-pr-body.sh", "at": "merge"},
  {"check": "command", "name": "lint", "run": "make lint-check"},
  {"check": "command", "name": "done-label", "run": "gh pr view \"$AF_PR\" --json labels -q '.labels[].name' | grep -qx status:done", "severity": "warn"}
]
```

- A command runs in the lead's clone with `AF_REPO`, `AF_PR`, `AF_TASK`,
  `AF_TASK_DIR`, `AF_BASE`, `AF_BASE_SHA` (the base branch's head on GitHub)
  and `AF_HEAD` set.
- A script from the repository is a `from_base` check: the gate takes it
  from `AF_BASE_SHA` itself and runs it, and a script it cannot get blocks.
  Never `run` a repository script, nor one that reads `origin/...`: the lead
  can change its own clone and its refs. In the script, name commits by
  `AF_BASE_SHA` and `AF_HEAD`, and fail on an empty or unreadable range.
- `"at": "merge"` runs a check only at the merge gate. `"severity": "warn"`
  reports without blocking; a label an agent sets itself is always `warn`,
  since it proves only that the agent said so.
- A name is lower-case letters, digits and `-`, used once, and not a standard
  check's; it stands for the check in the report and in `--skip`.

Ask with AskUserQuestion (multi-select): each check found, the ones a guide
or CI requires first.

## 5. Ask about the rest once

Show the work loop's table. Ask with AskUserQuestion (multi-select): `Keep:
the loop as shown` (recommended); stages and steps (names, which steps a
stage holds, add or remove a step); skills a step uses besides its default
one; what each difficulty runs and the roles (mode, prompt). When the person
changes anything here, ask the scope too: this project only (recommended when
this setup has a project), or the standard for every project.

Go into the chosen parts only.

## 6. Change

- **Stages**: show the steps in order with what each does, and let the
  person type each stage's name and the steps it holds (as
  `<name> <first>-<last>` by row number). Write the name into each of its
  steps' `stage`. A stage's steps stay together, and a stage may not take the
  name of a step in another stage; step ids stay as they are. Labels per
  stage (`labels.events`) move to the new names.
- **Replace a default skill** (step 2): save the choice in `skills`
  (`"<default name>": "<skill>"`). Remove the entry to go back to the
  default.
- **Skills per step**: an extra skill a step uses besides its default one.
  For each step the person picks, `Keep: <its skills now>` first, then the
  project's skills, then the person's. Save the bare name (`cross-e2e`);
  where it comes from is decided per machine when a task starts. Save the full
  `plugin:skill` only when the bare name matches more than one of the
  person's skills. A skill from a plugin directory found in step 1 adds that
  directory to `plugin_dirs` at the scope of the choice (the project's when
  this setup has a project). The bundle carries that plugin whole, so no
  machine needs it installed; prefer a directory that does not change with
  the plugin's version over a cache path.
- **Run the step**: the step's `does` names the skill, its non-interactive
  options, its stop before merge, and what the lead does after it; its
  `skills` hold the skill and the step's default skills, whose flow and
  record still apply.
- **Steps**: a new step needs an `id`, its `stage`, an `actor` (`lead`,
  `foreman`, `person`, or a role), what it `does`, its `skills`, and `next`
  (each outcome to a step id or `stop`; the last outcome is the success
  path, which must reach `stop`). Put it in the list where it runs, with no
  `"after"` key: saving works out its place, and the dry run's `written`
  shows it. A step is removed with `{"id": "<id>", "remove": true}`. The
  order of existing steps stays.
- **Difficulty**: per step, `run` at low, mid and high (`always`, `never`,
  `if-not-trivial`). A stage whose steps all do not run is skipped.
- **Roles**: `mode` (`prompt` or `pane`), `step` (tiers above the lead's), and
  the fixed prompt. `loop.py prompt` fills in `<task>`, `<repo>`, `<base>`,
  `<head>`, `<diff>`, `<task folder>`, `<skill>`, `<skills>`, `<full test
  command>` and `<trivial>`; write no other `<...>` in a prompt. A judging
  prompt must keep its `Verdict:` line, and each verdict word must be an
  outcome of the role's steps: the gate reads the last one in the answer that
  `launch.py --role` saves in the task folder.
- **Project gate** (step 4): the chosen checks in `gate`, at the project's
  level.

## 7. Save and share

Save at the scope from steps 2 and 5 (`setup.md` "4. Save"); `written` shows
each changed step by its `id`. Then show `loop.py show` again and one task's
loop: `python3 <skill>/scripts/loop.py render --project <repo> --task <N>
--difficulty mid --machine <label>`. For each skill it lists as missing:

- a person's skill that the machine lacks is installed with the bundle: offer
  `python3 <skill>/scripts/bundle.py push <label> --project <repo>`;
- a name found nowhere is a typo or a skill to write; say which.

Not every step fits at once. Show one table: each step, what it uses now,
where that comes from, its level, and whether it is bound, the default, or
open (a gap, or a question left for later). Go on with what is saved; the
open ones keep the default. Log them, so the retro comes back to them
(`SKILL.md` "Retro"):

```bash
python3 <skill>/scripts/log.py add --project <repo> --event setup --text "<n> steps fitted, <m> open" \
  --data '{"open": ["<step>: <what is open>"]}'
```
