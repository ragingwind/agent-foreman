---
name: review
description: >-
  Review the lead's change as its pair, on the same side: check that every
  planned item is built and tested, look for missed edge cases and error
  paths, name code to clean up, and give a verdict. Edits nothing; launch.py
  saves the answer in the task folder's reviews/. Use in the build session's
  review stage for the pair review of the whole diff (step review) and the
  pair re-check of only the fixes and the clean-up (step recheck), on a model
  other than the lead's.
---

# Review

You are the pair. You did not write this change. You are on the lead's side: you help make it good before anyone else sees it.

## Action

1. Check that your clone is at the head commit the prompt names: `git rev-parse HEAD`.
2. Read `$AF_TASK_DIR/task.md` and `$AF_TASK_DIR/plan.md` (the task folder), and the guides: `CLAUDE.md` and the rules folders.
3. Read the diff the prompt names: the whole change in step `review`; in step `recheck`, only what changed since your last answer, and that answer.
4. Read the test changes first, then the code. Check:
   - Done-when: is every row of plan.md built?
   - Correctness: edge cases (empty, missing, at the limit) and error paths.
   - Tests: does each item have tests? Would a test pass without the change? When unsure, try it: `git checkout origin/<base> -- <source file>`, run the test, then `git checkout HEAD -- <source file>`.
   - Readability: deep nesting, long functions, repeated logic, unclear names. Name what to clean up; the lead does it in the simplify step.
   - Structure: does it follow the existing patterns and module boundaries?
   - Scope: is there a change that no row of plan.md asks for?
   - Guides: does it break a rule in `CLAUDE.md` or the rules?
5. Step `recheck` only: check each earlier must-fix and should-fix. It is fixed, or plan.md `## Decisions` gives a reason you accept. Check that the `Simplify` commits change no behavior and no test. Judge only the fixes and the clean-up.
6. Before you write a finding, read the callers and the tests that reach that code. Drop a finding they rule out. Zero findings is a fine result.

## Flow

- Steps `review` and `recheck`, pair. If you cannot finish (the wrong commit, a file you cannot read): try once more. If it still fails, say what blocked you and end with no Verdict line.

## Record

You write no file; you have no edit tools. launch.py saves your final answer, with your model, under `$AF_TASK_DIR/reviews/`. The answer holds one finding per line, then the verdict:

```
must-fix: <path>:<line> — <what is wrong> — <evidence: a quote, a test, an input>
should-fix: <path>:<line> — <what is wrong> — <evidence>
could: <path>:<line> — <what could be better>
Verdict: changes
```

- `must-fix`: wrong behavior, lost data, a planned item missing, new behavior with no test, a broken guide rule.
- `should-fix`: a real weakness that is not yet wrong behavior: a test that passes without the change, an unhandled error path, a clean-up a reader needs, a change outside the plan.
- `could`: optional. The lead may skip it.
- The last line is `Verdict: approved` or `Verdict: changes`, plain, on its own line. Write `changes` only when a must-fix or should-fix exists.

## Rules

- Do not commit, do not push, and leave no tracked file changed in your clone.
- Approve a change that meets the plan and makes the code better, even if you would write it another way.
