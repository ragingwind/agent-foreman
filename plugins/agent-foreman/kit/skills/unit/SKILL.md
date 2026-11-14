---
name: unit
description: >-
  Run the tests that cover a change with the project's own commands and read
  the result. In the build step it runs one work item's tests before the item
  is committed. In the verify step it runs every test near the whole change
  and records each command with its raw output in plan.md. Use in the build
  session's build step (after each item is built) and first in its verify
  step.
---

# Unit

## Action

1. Find the project's test commands in its guides and CI files: how to run one file, and how to run a folder or a package. Use the project's own wrapper (`make`, a script, `./gradlew`) when it has one.
2. Step `build`, one item: run the tests in the row's `files` and the tests its done-when names. If the CI runs fast checks such as lint or a type check, run them on those files too.
3. Step `verify`, the whole change: list the changed files with `git diff --name-only origin/<base>...HEAD`, with the base the brief names. Run the tests for each of them, and the tests of code that imports or calls them. When unsure, run the whole package or folder.
4. Read the output, not only the exit code. Check that the tests you meant to run did run: the count is not zero, and no test is skipped that ran before.
5. A failure: read the message and find the cause. Fix the code. Fix a test only when the test itself is wrong, and write why under `## Decisions` in plan.md. Then run the same command again.

## Flow

- Step `build`: after `tdd` for the same row. Pass → `commit`. Fail → stay on the same row and fix it. Do not start the next row.
- Step `verify`: first, before `smoke`. Pass → `smoke`. Fail → the verify step ends with outcome `fail` (back to build, with the fix as a new row in plan.md); verify then runs again from the start.
- The same failure comes back after a fix: try once more. If it still fails, stop as blocked, with the command and the raw output.

## Record

- In the build step it records nothing while it passes. The commit skill marks the row `done`.
- In the verify step, add one entry under `## Checks` in `$AF_TASK_DIR/plan.md` (the task folder) for each command, in exactly this shape:

````markdown
### Tests near the change: <what it covers>
```
<command>
```
```
<raw output>
```
````

- Paste the output as it came, with secrets masked. A long output may drop passing lines; mark the cut with `[N lines cut]`. Never cut a failure or the summary line.
- When verify runs again, replace the old entries with the new ones.

## Rules

- Never skip, delete, or loosen a test to make a run pass.
- Never call a run passed unless you ran it and read its output.
