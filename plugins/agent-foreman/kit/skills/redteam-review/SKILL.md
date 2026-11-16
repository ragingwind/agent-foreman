---
name: redteam-review
description: >-
  Review a finished change from the other side: try to break it with inputs,
  timing and state; check that every done-when of the task is really met; look
  for weakened tests, changes outside the request, and security and
  performance problems; and decide whether it can merge. Edits nothing;
  launch.py saves the answer in the task folder's reviews/. Use in the
  verification session's redteam-review step, at the head commit, on a model
  other than the lead's.
---

# Red team review

You did not build this change. You trust only what you can see in the code or in output you ran. Your job is to find what is wrong before it merges.

## Action

1. Check that your clone is at the head commit the prompt names: `git rev-parse HEAD`.
2. Read only these: the done-when in `$AF_TASK_DIR/task.md` (the task folder); the diff the prompt names; the guides, `CLAUDE.md` and the rules folders; and the test records: plan.md `## Checks`, scenario.md, and handoff.md `## Tests` and `## Not touched`. Do not read the `## Decisions` of plan.md or handoff.md. Judge the code, not the builder's reasons.
3. Read the test changes first. Look for weakened tests: a test removed or skipped, an assertion changed to match the new behavior, a lower threshold, a changed CI file. Each one is a must-fix unless task.md asks for it.
4. Compare the test records with the diff. Was each changed area tested? Does each recorded command fit the code? When in doubt, run the test yourself.
5. For each done-when in task.md, find the code and the test or scenario step that meets it. Note what is missing.
6. Try to make it fail. Run the changed code in your clone with empty, very large, wrong-type, and repeated input; with two calls at once; with a missing file or a bad setting.
7. Check the rest:
   - Structure: did it make the structure worse? Did it add a helper that the code already has?
   - Scope: is there a change outside the request? Is what handoff.md says was not touched really unchanged?
   - Complexity: what is still hard to read?
   - Security: input checks, secrets in code or logs, permissions.
   - Performance: a loop that may never end, the same call repeated with no need.
   - Guides: a broken rule.
8. Before you write a finding, read the callers and the tests that reach that code. Drop a finding they rule out. Check the base too: a defect that is already there is an old defect, not a regression. Zero findings is a fine result.

## Flow

- Step `redteam-review`, red team. If you cannot finish (the wrong commit, a test that will not run): try once more. If it still fails, say what blocked you and end with no Verdict line.

## Record

**Evidence**: your answer is the step's evidence. Every finding carries its own, and the last line is the verdict.

You write no file; you have no edit tools. launch.py saves your final answer, with your model, under `$AF_TASK_DIR/reviews/`. The answer lists each finding as one list item, then a blank line and the verdict:

```
- must-fix: <path>:<line> — <what is wrong> — <evidence: the input and what it did>
- should-fix: <path>:<line> — <what is wrong> — <evidence>
- could: <path>:<line> — <what could be better>

Verdict: changes
```

- `must-fix`: wrong behavior, a done-when not met, a weakened test, a security hole, lost data, a broken guide rule.
- `should-fix`: a real weakness that is not yet wrong behavior: an untested path, a duplicated helper, a change outside the request, needless repeated work.
- `could`: optional.
- An old defect starts its text with `old defect:`. It is `could`, unless this change makes it worse.
- The last line is `Verdict: approved` or `Verdict: changes`, plain, after a blank line, and not a list item. Write `changes` only when a must-fix or should-fix exists.

## Rules

- Do not commit, do not push, and leave no tracked file changed in your clone.
- Do not trust a recorded result you doubt. Run it again.
