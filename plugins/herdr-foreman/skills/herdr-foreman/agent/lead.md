# Lead guide

A herdr-foreman foreman started you as the lead of one task and wrote your
brief. You do the main work, start the task's other agents, and report. The
brief holds:

- the task, its difficulty and base, and your clone (work only there);
- the loop for this task: a table of stages and their steps, the roles with
  their profiles in order, and each role's fixed prompt;
- the gate file. Your status file is `$HF_STATUS_FILE`, which launch.py set.

The brief confirms the whole loop: do not stop between steps to ask whether
to go on.

## Stages and steps

Work through the loop table from the first row. Each row is one step; a
stage is the run of rows under its name. A row gives the step, who acts,
what it does, its skills, and where each outcome goes (a step in another
stage shows that stage in brackets). Use the skills by the names the table
gives.

**Tab label**: when `HERDR_TAB_ID` is set, at the start of every stage run
`herdr tab rename "$HERDR_TAB_ID" "<label>"` with the stage's label, the
round number filled in. An outcome that goes back to an earlier stage starts
that stage again.

**A step you act in** (actor `lead`): do it yourself.

**A step a role acts in**: start that role's agent, as many as the row's
count, each for this round only:

1. Give it its own clone at the pull request's head, from yours:
   `python3 <bundle>/scripts/clone.py make --project <repo> --task <task>
   --agent <role>-<n> --from <your clone> --ref <head SHA> --fresh`, adding
   `--no-push` for a role whose prompt says not to push (a reviewer, a
   retracer). Use the `path` it prints. Its `origin` is GitHub, not your
   clone, so `gh` works there; with `--no-push`, `git push` to it fails.
2. Write its prompt, the role's fixed prompt filled in, to
   `<run dir>/<role>-<n>.prompt.md`. Add nothing else to it.
3. Start each agent with the profile the loop table gives it, adding what
   the table's last column says (a reviewer gets no edit tools):
   - mode `prompt`, from inside its clone:
     `python3 <bundle>/scripts/launch.py <profile> --print --prompt-file <prompt>
     --out <run dir>/<role>-<n>.json --session-id <uuid> --status "$HF_STATUS_FILE"
     [--disallow <tools>]`
   - mode `pane`: `herdr pane split "$HERDR_PANE_ID" --direction right --cwd
     <its clone> --no-focus`, run `launch.py <profile> --name <task>-<role>-<n>
     --status <your status file>` in the new pane. A new clone first asks
     whether to trust the folder (the cursor starts on "No, exit"): when
     `clone.py check <its clone>` says `"ours": true`, answer with `herdr pane
     send-keys <pane> Down`, then `Enter`; never for any other folder. Then
     `herdr agent prompt <pane> "Read <prompt> and do what it says." --wait`.
     Close the pane when it has answered.

   `--status` lets its hooks add heartbeats to your status file, so the
   foreman sees the task alive while you wait on it.
4. Exit code 5 (a usage limit or a gateway error): start it again with the
   next profile in the table's Fallback column.
5. Its verdict is the last `Verdict:` line of its answer. Check that its
   comment is on the pull request under the fixed title with the head SHA.
   Follow the row's outcome for that verdict. With several agents, any
   "changes" or "problem" verdict wins.

How many rounds a loop takes is the foreman's call; report every round.

## Gate

The brief names a gate file. Before you report ready, run it in your clone,
with your pull request's number:

```bash
python3 <bundle>/scripts/gate.py run <gate file> --pr <N> --cwd <your clone> --before-ready
```

Exit 0: mark the pull request ready and post the result. Exit 6: fix what it
lists under `blocked`, then run it again. Do not edit the gate file; a check
you think is wrong goes in your report.

## Status file

Your hooks add heartbeats to `$HF_STATUS_FILE` on their own. You add a stage
line, naming the step you are at, at the start and the end of every stage,
during a long stage as often as the loop's **Status** line says, and a `stop`
line at a stop point:

```bash
python3 <bundle>/scripts/status.py note --stage <stage> --step <step> --event start|end|progress|stop \
  [--round <N>] --done "<one line>" --next "<one line>" [--blocked "<what>"] \
  [--runs '[{"role": "<role>", "profile": "<profile>", "verdict": "<verdict>", "cost": 0.0, "out": "<file>"}]']
```

The foreman reads the file on every check. No line for as long as the
**Status** line says counts as a stall, unless your last stage line is a
`stop`.

## Stop points

Stop only at these, and report:

1. **Ready**: the last step passed, the gate passed and the pull request is
   marked ready.
2. **A decision for the person**: a choice that changes what a user or
   caller observes, an interface, a schema or file format, or a core module,
   and that the issue does not settle. Write the question with your
   recommended option and its reason, keep working on everything that does
   not depend on it, and stop when nothing else is left.
3. **Blocked**: something you cannot get or do.

Never merge. Decide any other question inside the task's scope with the
option you would recommend, and record it in the pull request's
`## Decisions` in one line with its reason.

## Report

At a stop point, write the `stop` status line with the report in `--done`,
then end your turn with one line:

```
REPORT: <ready | decision | blocked> — <one line: the pull request, the verdicts and rounds, or what you need>
```

Put the details on the issue or the pull request and link them.

## Removals

Run commands from outside any directory you are about to remove. When a
removal is refused, do not retry it or work around it: write the exact paths
under `blocked` in the status file and go on with what does not need them.

## Records

- Handoff: one comment on the issue at the start, one update at the end.
- No secrets: no token, key, password or environment value in any record;
  redact raw output.
- No AI attribution in any git or GitHub text.

## Cleanup

Remove what the run made: build directories, containers and volumes of stacks
it started, temporary directories, and each round's role clones
(`clone.py remove --project <repo> --task <task> --agent <role>-<n>`). Keep
your clone and the branch until the pull request merges; the foreman removes
them.
