---
name: work-breakdown
description: >-
  Read the task, the code and the project's guides, then split the task into
  small work items in build order. Each item gets a goal, a done-when that can
  be observed, the files it touches, and how it is tested. Writes plan.md in
  the task folder. Use in the build session's plan step, before the scenario
  script is written and before any code. Also use when work comes back to
  build: each piece of it becomes a new row.
---

# Work breakdown

Plan small pieces in order, and decide how each one is checked, before any code.

## Action

1. Read `$AF_TASK_DIR/task.md` and `$AF_TASK_DIR/brief.md`. `$AF_TASK_DIR` is the task folder. Note the goal, each done-when, and what is out of scope.
2. If `$AF_TASK_DIR/plan.md` already exists, do not plan again. Keep every row. Add a row for each piece of new work that comes back to build: a fix that verify or review sends back, a finding from the verification session, a rebase conflict. Then build from the first row that is not `done`.
3. Read. Read the code the task names, the code that calls it, and their tests. Read the project's guides: `CLAUDE.md`, `AGENTS.md`, the rules folders, `README`, `CONTRIBUTING`, and the CI files. Read `git log` for the files you expect to touch. Change nothing.
4. Find the project's own commands to build, to run one test file, and to run all tests. Take them from the guides and the CI files, not from habit.
5. Split. One work item is one idea that a reviewer can check alone.
   - Give each item a goal, a done-when, and its files.
   - The done-when is something you can see: a command that exits 0, a line in the output, a named test that passes. Name the command when there is one.
   - Keep each item small: about five files or fewer, and three conditions or fewer in the done-when. A goal with "and" in it is often two items.
   - Prefer a small path that works end to end over one whole layer at a time.
   - Order the rows: what others depend on comes first, and the riskiest item comes early. Every item leaves the build working.
6. Pick the test for each item and write it in the `test` column.
   - `test-first`: a failing test comes first. Use it for new logic, a changed behavior, and every bug fix.
   - `test-after`: the code comes first, then its tests. Use it for wiring, settings and generated code, where a test first does not fit.
7. Write each choice that task.md does not settle under `## Decisions`, with its reason.
8. Check the plan. Every row has a goal, a done-when and files. No row is too big. Together, the rows cover every done-when in task.md.

## Flow

- Step `plan`, lead, before `cross-check` writes the scenario script. The step ends with outcome `done` (next: build).
- A decision for the person: a choice that task.md does not settle and that changes what a user or caller sees, an interface, a schema, or a file format. Write the question, the option you recommend, and its reason. Plan all the work that does not depend on it. Then stop at a decision point (loop.md).
- Any other problem, such as a file you cannot read: try once more. If it still fails, stop as blocked (loop.md).

## Record

**Evidence** for the step's `end` line: `work-breakdown: plan.md <n> rows`.

Write `$AF_TASK_DIR/plan.md` in exactly this shape:

````markdown
# Plan: <task title>

## Work breakdown

| id | goal | done when | files | test | status | commit |
|---|---|---|---|---|---|---|
| W1 | <goal> | <observable condition> | <paths> | <test-first or test-after> | todo | |

## Decisions
- <choice> — <reason>

## Checks
````

- `<task title>` is the title in task.md.
- `id` is `W1`, `W2`, and so on, in build order. Never reuse an id.
- `test` is `test-first` or `test-after`. `status` starts as `todo`. `commit` stays empty until the commit skill fills it.
- Every row has seven cells. Never put a `|` inside a cell, not even in a command: the gate splits each row at `|`, and a row that does not fit the header blocks it.
- `## Checks` stays empty here. The verify step fills it.
- Put no secret, token, or machine path in the file.

## Rules

- Write no code and change no file in the clone in this step.
- Do not drop or reword a done-when from task.md. If one looks wrong, it is a decision for the person.
