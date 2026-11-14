---
name: work-breakdown
description: >-
  Read the task, the code and the project's guides, then split the task into
  small work items in build order. Each item gets a goal, a done-when that can
  be observed, the files it touches, and how it is tested. Writes plan.md in
  the task folder. Use in the build session's plan stage (actions P1 to P3),
  before the scenario script is written and before any code. Also use when the
  task comes back to build and needs new work items.
---

# Work breakdown

Plan small pieces in order, and decide how each one is checked, before any code.

## Action

1. Read `$AF_TASK_DIR/task.md` and `$AF_TASK_DIR/brief.md`. `$AF_TASK_DIR` is the task folder. Note the goal, each done-when, and what is out of scope.
2. If `$AF_TASK_DIR/plan.md` already exists, do not plan again. Keep every row. Add rows only for new work, such as a large fix sent back to build. Then build from the first row that is not `done`.
3. P1, read. Read the code the task names, the code that calls it, and their tests. Read the project's guides: `CLAUDE.md`, `AGENTS.md`, the rules folders, `README`, `CONTRIBUTING`, and the CI files. Read `git log` for the files you expect to touch. Change nothing.
4. Find the project's own commands to build, to run one test file, and to run all tests. Take them from the guides and the CI files, not from habit.
5. P2, split. One work item is one idea that a reviewer can check alone.
   - Give each item a goal, a done-when, and its files.
   - The done-when is something you can see: a command that exits 0, a line in the output, a named test that passes. Name the command when there is one.
   - Keep each item small: about five files or fewer, and three conditions or fewer in the done-when. A goal with "and" in it is often two items.
   - Prefer one thin, working path through every layer over one whole layer at a time.
   - Order the rows: what others depend on comes first, and the riskiest item comes early. Every item leaves the build working.
6. P3, pick the test for each item and write it in the `test` column.
   - `tdd`: a failing test comes first. Use it for new logic, a changed behavior, and every bug fix.
   - `unit`: the code comes first, then its tests. Use it for wiring, settings and generated code, where a test first does not fit.
7. Write each choice that task.md does not settle under `## Decisions`, with its reason.
8. Check the plan. Every row has a goal, a done-when and files. No row is too big. Together, the rows cover every done-when in task.md.

## Flow

- Stage: plan, actions P1 to P3. The lead runs it in its own clone.
- Reads: task.md, brief.md, the code, the guides.
- Done: step 8 passes. Next is P4, write the scenario script. Then the build stage starts at the first row.
- A decision for the person: a choice that task.md does not settle and that changes what a user or caller sees, an interface, a schema, or a file format. Write the question, the option you recommend, and its reason. Plan all the work that does not depend on it. Then stop and report it for the person.
- Anything else off the path, such as a file you cannot read: try once more. If it still fails, stop and report it for the person.

## Record

Write `$AF_TASK_DIR/plan.md` in exactly this shape:

````markdown
# Plan: <task title>

## Work breakdown

| id | goal | done when | files | test | status | commit |
|---|---|---|---|---|---|---|
| W1 | <goal> | <observable condition> | <paths> | unit or tdd | todo | |

## Decisions
- <choice> — <reason>

## Checks
````

- `<task title>` is the title in task.md.
- `id` is `W1`, `W2`, and so on, in build order. Never reuse an id.
- `test` is `unit` or `tdd`. `status` starts as `todo`. `commit` stays empty until the commit action fills it.
- Never put a `|` inside a cell, not even in a command. The gate splits each row at `|`.
- `## Checks` stays empty here. The verify stage fills it.
- Put no secret, token, or machine path in the file.

## Rules

- Write no code and change no file in the clone in this stage.
- Do not drop or reword a done-when from task.md. If one looks wrong, it is a decision for the person.
