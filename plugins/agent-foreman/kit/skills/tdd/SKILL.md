---
name: tdd
description: >-
  Build one work item from plan.md. For an item marked test-first, write a
  test that fails first, then the least code that makes it pass. For an item
  marked test-after, write the code, then tests that fail without it. Use in
  the build session's build step, once for each work item, in the order of
  plan.md.
---

# TDD

## Action

1. Take the first row in `$AF_TASK_DIR/plan.md` (the task folder) whose status is not `done`. Read its goal, done-when, files and test.
2. Find how the project runs one test file or one test. Use that command for every run below.
3. The row's `test` is `test-first`:
   1. Write one test for the next behavior the done-when asks for. For a bug, the test shows the bug.
   2. Run it. It must fail because the behavior is missing. A failure from a typo, an import or a missing fixture does not count. Fix the test and run it again.
   3. Write the least code that makes it pass. Run it again. It passes.
   4. Repeat 1 to 3 until the done-when is met.
   5. With all tests passing, tidy the code you just wrote. Run the tests after each change.
4. The row's `test` is `test-after`: write the code, then add or update tests that check the done-when. Make sure each new test fails without your code: take the change out, run the test, put the change back.
5. Test what the code does, its inputs and outputs, not how it does it. Use real code before a fake, and a fake before a mock. Mock only what is slow, random, or outside your control.
6. Stay inside the row's files. If the item truly needs another file, add it to the row's `files`. A problem you see outside the item is not fixed here. Write it as one line under `## Follow-ups` in `$AF_TASK_DIR/handoff.md`; create the file with that heading if it is not there.

## Flow

- Step `build`, lead. For each row that is not done, in row order: this skill, then `unit` runs the row's tests, then `commit`. When every row is done, the build step ends with outcome `done` (next: verify).
- The item is bigger than planned: keep the row for the first part. Add a new row with a new id right under it for the rest. Write why under `## Decisions`.
- An existing test fails because the behavior must change. If task.md asks for that change, update the test and write why under `## Decisions`. If it does not, it is a decision for the person: stop at a decision point (loop.md).
- A test you cannot make fail for the right reason, or code you cannot make pass: try once more. If it still fails, stop as blocked.

## Record

**Evidence** for the step's `end` line, with commit's: `tdd, commit: W1 <sha>, W2 <sha>`.

- This skill writes no file of its own. Its record is the item's one commit (`commit`). That commit holds the tests and the code together, and the commits follow the row order of plan.md.
- A change to the plan (a split row, an added file) is written in plan.md: the row, and one line under `## Decisions`.

## Rules

- Never delete, skip, or loosen an existing test to make new code pass.
- Never start the next item while a test of this item fails.
- Write no code that the done-when does not ask for.
