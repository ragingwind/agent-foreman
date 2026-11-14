---
name: handoff
description: >-
  Finish the build session: rebase the branch onto the latest main, write
  handoff.md (purpose, decisions, tests, what was not touched, follow-ups), and
  publish the change, usually as a pull request whose body is handoff.md. Use
  in the build session's finalize stage: the rebase (F1), handoff.md (F2), and
  the publish (F4) after the gate (F3) passes.
---

# Handoff

## Action

**F1, rebase.**
1. Run `git fetch origin`, then `git rebase origin/<base>`. The brief names the base.
2. No conflict: the rebase gave each commit a new SHA. List them with `git log --oneline origin/<base>..HEAD`, and set each row's `commit` in `$AF_TASK_DIR/plan.md` (the task folder) to its new short SHA. Match a row to its commit by subject.
3. A conflict: fix it in the files, `git add` them, and run `git rebase --continue`. Then go back to build (see Flow).

**F2, write handoff.md.**
1. Purpose: what the change does and why, in two to four sentences, from task.md. If the task comes from an issue, end with `Closes #<number>`.
2. Decisions: each line of plan.md `## Decisions`, and each review finding left unfixed, with its reason.
3. Tests: one line for each check that ran, with its command and result: the item tests, V1, V2, and the scenario script. The raw output stays in plan.md and scenario.md.
4. Not touched: what a reader might expect this change to touch, but it does not, and why. For example: related code, the same bug in another place, a file out of scope.
5. Follow-ups: keep the lines already there. Add large clean-ups, `could` findings left open, and problems seen outside the task.
6. Read it once as a stranger. It becomes the pull request body.

**F4, publish, after the gate passes.**
1. Push the branch: `git push -u origin <branch>`. If the branch was pushed before a rebase, use `git push --force-with-lease origin <branch>`.
2. No pull request yet: `gh pr create --base <base> --head <branch> --title "<short imperative title>" --body-file "$AF_TASK_DIR/handoff.md"`.
3. A pull request exists from an earlier round: `gh pr edit <number> --body-file "$AF_TASK_DIR/handoff.md"`.
4. Check it: `gh pr view <number> --json url,headRefOid`. `headRefOid` must equal `git rev-parse HEAD`.
5. Mark the task ready the way the brief says.

## Flow

- Finalize stage, lead: after the review stage gives `Verdict: approved`. The order is F1, F2, F3, F4. F3 is the gate script; run it the way the brief says.
- F1 had to fix a conflict → back to build. Run the tests of each item the conflict touched. Then verify and review run again, and then finalize.
- F3 fails: fix what it lists, then run it again.
- F4 done: the build session ends with `ready`. The foreman starts the verification session. If that session sends the task back, the loop runs again and so does this skill: rebase, update handoff.md, push, and update the pull request body.
- A push, a `gh` call, or the gate fails for a reason outside the code: try once more. If it still fails, stop and report it for the person.

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
- After F1, plan.md's `commit` column holds the new SHAs.

## Rules

- Never merge. Never push to main or the base branch.
- No secret, token, or machine path in handoff.md. No AI attribution in the pull request.
