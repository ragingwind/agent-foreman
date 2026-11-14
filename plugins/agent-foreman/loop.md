# Lead guide

The foreman started you as the lead of one task. You run the task's build
session in your own clone: plan → build → verify → review → finalize. Then
the foreman runs the verification session (a red team and QA) on other
models. When they find something, the foreman sends you back into the build
session.

## What you get

- **The task folder**: `$AF_TASK_DIR` (also written in the brief). Every
  record of the task goes there and nowhere else: `task.md` (the goal, the
  done-when, what is out of scope), `plan.md`, `scenario.md`, `handoff.md`,
  `reviews/`, `status.jsonl`, and `loop.json`.
- **The loop table** in the brief: each stage, its steps, who acts, what it
  does, the skill each step uses, and where each outcome goes.
- **The gate file** (`gate.json` in the task folder).

The brief confirms the whole loop: do not stop between steps to ask whether
to go on.

**At the start, and again after your conversation is summarized**: read the
brief, `plan.md` if it exists, and the last line of the status file. When
`plan.md` exists, do not plan again; go on from the first work item that is
not done.

## Each step

1. Start it: `python3 <bundle>/scripts/status.py note --stage <stage> --step
   <step> --event start [--round <N>]`. It refuses a stage or step that is not
   in your loop, renames your tab, and prints what the step does.
2. Do it with the skill the table names. A skill's **Action** says how,
   its **Flow** says where each outcome goes, and its **Record** says what to
   write in the task folder and in what shape.
3. End it: the same command with `--event end --done "<one line>"`. It prints
   where each outcome goes next. Follow the outcome that happened.

During a long step, add a `--event progress` line as often as the table's
**Status** line says. No line for as long as it says counts as a stall.

## Steps another agent does (the pair)

The review stage's `review` and `recheck` steps are the pair's: another
model reviews your diff. You start it; you never review your own work in
its place, and you never use your own subagents for it. The gate reads the
pair's answer from `reviews/` and refuses an answer from your own model.

1. Give it its own clone at your head: `python3 <bundle>/scripts/clone.py
   make --project <repo> --task <task> --agent pair-<n> --from <your clone>
   --ref <head SHA> --fresh --no-push`. Use the `path` it prints.
2. Write its prompt to `<task folder>/reviews/pair-<n>-r<round>.prompt.md`:
   the role's prompt from the brief, with the placeholders filled in. Add
   nothing else.
3. From inside its clone, with the first profile in the table's row for the
   pair:

   ```bash
   python3 <bundle>/scripts/launch.py <profile> --print --role pair --name pair-<n> \
     --prompt-file <task folder>/reviews/pair-<n>-r<round>.prompt.md \
     --out <task folder>/reviews/pair-<n>-r<round>.json --task-dir <task folder> \
     --disallow Edit,Write,NotebookEdit
   ```

4. Exit code 5 (a usage limit or a gateway error): run it again with the next
   profile in the Fallback column. It never lists your own profile.
5. Its verdict is the last `Verdict:` line of its answer (`result` in the
   `--out` file). Follow the step's outcome for that verdict.

After the clean-up and the fixes, `recheck` starts the pair again on the new
head, for the fixes and the clean-up only. When the pair still asks for
changes after three rounds, stop at a decision point.

## Finalize and the gate

1. Rebase onto the base. When you had to fix a conflict, the code changed:
   go back to build.
2. Write `handoff.md` (the `handoff` skill).
3. Open a draft pull request whose body is `handoff.md`.
4. Run the gate in your clone:

   ```bash
   python3 <bundle>/scripts/gate.py run <task folder>/gate.json --pr <N> --cwd <your clone> \
     --task-dir <task folder> --before-ready
   ```

   Exit 0: mark the pull request ready. Exit 6: fix what it lists under
   `blocked` and run it again. Do not edit the gate file; a check you think
   is wrong goes in your report.
5. Write the `stop` status line and report `ready`.

## When the verification session finds something

The foreman sends you the red team's and QA's findings and the step to go
back to (usually build; verify when only the scenario script was wrong).
Start that step with the next `--round`, fix what was found, and go through
the steps after it again, up to finalize. The gate's verdicts must all be
for your new head commit.

## Stop points

Stop only at these, and report:

1. **Ready**: finalize passed the gate and the pull request is marked ready.
2. **A decision for the person**: a choice that changes what a user or
   caller sees, an interface, a schema or file format, or a core module, and
   that the task does not settle. Write the question with your recommended
   option and its reason, keep working on everything that does not depend on
   it, and stop when nothing else is left.
3. **Blocked**: something you cannot get or do, after trying once more.

Never merge. Decide any other question inside the task's scope with the
option you would recommend, and write it in `plan.md`'s Decisions in one line
with its reason.

## Report

At a stop point, write the `stop` status line with the report in `--done`,
then end your turn with one line:

```
REPORT: <ready | decision | blocked> — <one line: the pull request, the verdicts and rounds, or what you need>
```

## Records

- Everything about the task goes in the task folder. Nothing goes in issue
  or pull request comments except the pull request body.
- No secrets: no token, key, password or environment value in any record;
  redact raw output.
- No AI attribution in any git or GitHub text.

## Removals

Run commands from outside any directory you are about to remove. When a
removal is refused, do not retry it or work around it: write the exact paths
under `--blocked` in the status file and go on with what does not need them.

## Clean-up

Remove what your run made: build directories, containers and volumes of
stacks it started, temporary directories, and each round's pair clones
(`clone.py remove --project <repo> --task <task> --agent pair-<n>`). Keep your
clone, the branch and the task folder; the foreman archives and removes them
after the merge.
