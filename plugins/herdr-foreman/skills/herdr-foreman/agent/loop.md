# Agent loop

A herdr-foreman foreman started you and wrote your brief. The brief names
the task, the tier, the stage table and this file. One task, one pull
request, one loop. The brief confirms every stage: it is the whole loop, not
its first stage.

## Stages

Work through the brief's stage table in order. Each row gives the stage, the
tab label, the skills to use and the method. Use the skill names exactly
as the table writes them, not a skill of the same name from somewhere else. `review` and `fix` repeat, with a round number, until the
review approves.

**Tab label**: when `HERDR_TAB_ID` is set, at the start of every stage run
`herdr tab rename "$HERDR_TAB_ID" "<label>"` with the row's label, the round
number filled in. Without `HERDR_TAB_ID`, skip it.

You may show your plan once when you start; the foreman answers it. After
that, do not list a stage and wait for a yes, and do not ask "shall I
proceed?" between stages.

## Stop points

Stop only at these:

1. **Approved**: the review approved and the pull request's checks pass.
2. **Owner decision**: a choice that changes what a user or caller
   observes, an interface, a schema or file format, or a core module, and
   that the issue does not settle. Write the question with your recommended
   option and its reason, keep working on everything that does not depend on
   it, and stop at approval with the question still listed. Rename the tab
   with the brief's `owner-decision` label while you wait.
3. **Merge**: never merge. The foreman or the person merges.

Any other question inside the task's scope: decide it with the option you
would recommend, record it in the pull request's `## Decisions` in one line
with its reason, and continue.

## Report

The foreman reads your screen when your turn ends; there is no message
channel. Report only at a stop point, when you are blocked on something you
cannot get, or when a task without a pull request is done. End that turn
with one line:

```
REPORT: <approved | owner-decision | blocked | done> — <one line: the pull request, the verdict and rounds, or what you need>
```

Put the details on the issue or the pull request and link it. Keep the
report under five lines. Do not end a turn for progress, and do not message
the foreman any other way.

## Records

- Handoff: one comment on the issue at the start, one update at the end.
- No secrets: no token, key, password or environment value in any record;
  redact raw output.
- No AI attribution in any git or GitHub text.

## Cleanup

At the end, remove what the run made: build directories, containers and
volumes of stacks it started, temporary directories. Keep the worktree and
the branch until the pull request merges, for a later fix round.
