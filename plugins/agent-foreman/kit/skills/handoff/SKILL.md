---
name: handoff
description: >-
  Finish the build session: rebase the branch onto its base, write handoff.md
  (purpose, decisions, tests, what was not touched, follow-ups), push and open
  a draft pull request whose body is handoff.md, run the gate, and mark the
  pull request ready when it passes. Use in the build session's finalize
  step.
---

# Handoff

## Action

1. **Rebase.** Run `git fetch origin`, then `git rebase origin/<base>`. The brief names the base. A conflict: fix it in the files, `git add` them, run `git rebase --continue`, and see Flow.
2. **Write `$AF_TASK_DIR/handoff.md`** (the task folder) in the shape under Record.
   1. Purpose: what the change does and why, in two to four sentences, from task.md. If the task comes from an issue, end with `Closes #<number>`.
   2. Decisions: each line of plan.md `## Decisions`, and each review finding left unfixed, with its reason.
   3. Tests: one line for each check that ran, with its command and result: the item tests, the tests near the change, the smoke test, and the scenario script. The raw output stays in plan.md and scenario.md.
   4. Not touched: what a reader might expect this change to touch, but it does not, and why. For example: related code, the same bug in another place, a file out of scope.
   5. Follow-ups: keep the lines already there. Add large clean-ups, `could` findings left open, and problems seen outside the task.
3. **Push and open a draft pull request.**
   1. `git push -u origin <branch>`. If the branch was pushed before a rebase, use `git push --force-with-lease origin <branch>`.
   2. No pull request yet: `gh pr create --draft --base <base> --head <branch> --title "<short imperative title>" --body-file "$AF_TASK_DIR/handoff.md"`. One exists from an earlier round: `gh pr edit <number> --body-file "$AF_TASK_DIR/handoff.md"`.
   3. Check it: `gh pr view <number> --json url,headRefOid`. `headRefOid` must equal `git rev-parse HEAD`.
4. **Wait for the checks**: `gh pr checks <number> --watch`, in the background or with a long timeout. When it says no checks are reported, go on. The gate blocks a check that has not finished.
5. **Run the gate** with the command the brief gives. Exit 6: fix what it lists under `blocked`, then run it again. Do not edit the gate file.
6. **Mark it ready**: `gh pr ready <number>`.

## Flow

- Step `finalize`, lead: after the pair's `recheck` approves (a trivial task: after verify). The step ends with outcome `done` once the pull request is ready; that is a stop point, and you report ready.
- The rebase needed a conflict fix → the step ends with outcome `conflict` (back to build, with a new row for the conflict fix so its tests run; verify and review then run again).
- When the verification session sends the task back, this skill runs again: rebase, update handoff.md, push, and update the pull request body.
- A push, a `gh` call, or the gate fails for a reason outside the code: try once more. If it still fails, stop as blocked.

## Record

Write `$AF_TASK_DIR/handoff.md` in exactly this shape:

````markdown
# Handoff: <task title>

## Purpose
<what the change does and why>

## Decisions
- <choice> — <reason>

## Tests
- `<command>` — <result, such as "48 passed">

## Not touched
- <what> — <why>

## Follow-ups
- <what> — <why it is not in this change>
````

- A section with nothing in it says `none`.
- The pull request body is this file, unchanged.

## Rules

- Never merge. Never push to main or the base branch.
- No secret, token, or machine path in handoff.md. No AI attribution in the pull request.
