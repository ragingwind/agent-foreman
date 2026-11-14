---
name: full
description: >-
  Run the project's full test command, or every CI job when the project has
  none, at the change's head commit. Report each failure with its raw output,
  after checking whether it also fails on main. Edits nothing; launch.py saves
  the answer in the task folder's reviews/. Use by QA in the verification
  session (action T1), next to the red team review and the user scenario test.
---

# Full

## Action

1. Check that your clone is at the head commit the prompt names: `git rev-parse HEAD`.
2. Take the full test command from the brief. The brief takes it from the project's settings.
3. The brief gives none: read the CI files, for example `.github/workflows/*.yml`. Copy the command of every job, with its setup steps and environment variables, in order. Do not choose a smaller set.
4. Run each command as written. Keep its exit code and raw output.
5. A command that cannot run here, because it needs a secret, a service or a machine you do not have: do not pretend it ran. Write it as `not run`, with the reason.
6. A failure: before you call it new, run the same command at the base. Run `git worktree add ../main-check $(git merge-base HEAD origin/<base>)`, run the command in `../main-check`, then run `git worktree remove ../main-check`.
   - It passes at the base: this change broke it. It is new.
   - It fails at the base too: it is old.
7. Fix nothing. Do not edit, commit, or push.

## Flow

- T1, verification session, QA: the foreman starts it after the build session is `ready`, next to X1 and T2.
- `Verdict: pass`, the red team approves, and T2 passes → the merge gate.
- A new failure → back to build.
- Only old failures → not sent to build. They are written under handoff.md `## Tests`, and the person decides.
- A command not run → an environment problem → the person.
- Anything else off the path, such as the wrong commit or a missing tool: try once more. If it still fails, say what blocked you and end with `Verdict: fail`.

## Record

You write no file; you have no edit tools. launch.py saves your final answer, with your model, under `$AF_TASK_DIR/reviews/` (the task folder). The answer holds one line for each command, then the verdict:

```
ran: <command> — exit 0
failure (new): <command or test name> — <what failed>
failure (also on main): <command or test name> — <what failed>
not run: <command> — <reason>
Verdict: fail
```

- Under each `ran:` line, a fence with the summary lines as they came. Under each failure, a fence with its full error message and the summary line. Do not retell output in your own words.
- If one run of yours does both this and the user scenario test (T2), give one answer for both, with one verdict at the end. It is `pass` only when both pass.
- The last line is `Verdict: pass` or `Verdict: fail`. It is `pass` only when every command ran and passed.
