---
name: full
description: >-
  Run the project's full test command at the change's head commit and report
  each failure with its raw output, after checking whether it also fails at
  the base. Edits nothing; launch.py saves the answer in the task folder's
  reviews/. Use by QA in the verification session's test step, with the user
  scenario test.
---

# Full

## Action

1. Check that your clone is at the head commit the prompt names: `git rev-parse HEAD`.
2. Run the full test command the prompt names, as written. Keep its exit code and raw output. When the prompt says none is set, write `not run: no full test command`; that line alone does not fail the verdict.
3. A command that cannot run here, because it needs a secret, a service or a machine you do not have: do not pretend it ran. Write it as `not run`, with the reason.
4. A failure: run the same command at the base before you call it new. Inside your clone: `git worktree add .base-check $(git merge-base HEAD origin/<base>)`, run it in `.base-check`, then `git worktree remove --force .base-check`.
5. Fix nothing. Do not edit, commit, or push.

## Flow

- Step `test`, QA. If you cannot finish (the wrong commit, a missing tool): try once more. If it still fails, say what blocked you and end with no Verdict line.

## Record

**Evidence**: your answer is the step's evidence: each command with its output, and the verdict last.

You write no file; you have no edit tools. launch.py saves your final answer, with your model, under `$AF_TASK_DIR/reviews/` (the task folder). QA does this and the user scenario test (`cross-check`) in one run and gives one answer: one line for each command, the mismatch lines, then one verdict:

```
ran: <command> — exit 0
failure (new): <command or test name> — <what failed>
failure (also on the base): <command or test name> — <what failed>
not run: <command> — <reason>
Verdict: fail
```

- Under each `ran:` line, a fence with the summary lines as they came. Under each failure, a fence with its full error message and the summary line. Do not retell output in your own words.
- The last line is `Verdict: pass` or `Verdict: fail`, plain, on its own line. It is `pass` only when every command that is set ran and passed and the user scenario test passed.
