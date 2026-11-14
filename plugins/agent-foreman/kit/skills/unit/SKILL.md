---
name: unit
description: >-
  Run the tests that cover a change with the project's own commands and read
  the result. In the build stage it runs one work item's tests before the item
  is committed. In the verify stage it runs every test near the whole change
  and records each command with its raw output in plan.md. Use in the build
  session for action B2 (after each item is built) and action V1 (the first
  step of verify).
---

# Unit

## Action

1. Find the project's test commands in its guides and CI files: how to run one file, and how to run a folder or a package. Use the project's own wrapper (`make`, a script, `./gradlew`) when it has one.
2. B2, one item: run the tests in the row's `files` and the tests its done-when names. If the CI runs fast checks such as lint or a type check, run them on those files too.
3. V1, the whole change: list the changed files with `git diff --name-only origin/<base>...HEAD`, with the base the brief names. Run the tests for each of them, and the tests of code that imports or calls them. When unsure, run the whole package or folder.
4. Read the output, not only the exit code. Check that the tests you meant to run did run: the count is not zero, and no test is skipped that ran before.
5. A failure: read the message and find the cause. Fix the code. Fix a test only when the test itself is wrong, and write why under `## Decisions` in plan.md. Then run the same command again.

## Flow

- B2, build stage, lead: after B1 for the same item. Pass → B3, commit the item. Fail → stay on the same item and fix it. Do not start the next item.
- V1, verify stage, lead: after the last item is committed. Pass → V2, smoke. Fail → back to build, with the fix as a new row in plan.md. Then verify runs again from V1.
- The same failure comes back after a fix: try once more. If it still fails, stop and report it for the person, with the command and the raw output.

## Record

- B2 records nothing while it passes. The commit action marks the row `done`.
- B2 stopping for the person: add the failing run under `## Checks`, in the shape below, named `B2 <id> tests (failing)`.
- V1 adds one entry under `## Checks` in `$AF_TASK_DIR/plan.md` (the task folder) for each command, in exactly this shape:

````markdown
### V1 tests near the change: <what it covers>
```
<command>
```
```
<raw output>
```
````

- Paste the output as it came, with secrets masked. A long output may drop passing lines; mark the cut with `[N lines cut]`. Never cut a failure or the summary line.
- When verify runs again, replace the old V1 entries with the new ones.

## Rules

- Never skip, delete, or loosen a test to make a run pass.
- Never call a run passed unless you ran it and read its output.
