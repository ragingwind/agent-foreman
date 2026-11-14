---
name: commit
description: >-
  Commit one finished work item as exactly one commit, with a message in the
  project's own style, then mark the item done in plan.md with the commit's
  short SHA. Use in the build session's build stage (action B3), after the
  item's tests pass and before the next item starts. The same steps commit the
  review stage's fixes.
---

# Commit

## Action

1. Read recent history: `git log --oneline -20`. Note the project's style: a prefix such as `feat:` or none, the tense, the case, the length.
2. Check what changed: `git status` and `git diff`. Every change you stage must belong to this item.
3. Stage this item's files by path: `git add <path> ...`. Do not use `git add -A` or `git add .`.
4. Read the staged diff: `git diff --cached`. It must hold no secret (token, key, password), no debug print, no build output, and no file that only your machine needs.
5. Write the message in the project's style. The subject is a short imperative phrase, such as `Add JSON output to the list command`. Add a body only when the reason is not clear from the diff. The body says why, not what.
6. Run `git commit`. Let the project's hooks run. If a hook fails, fix the cause and commit again.
7. Get the short SHA with `git rev-parse --short HEAD`, and update the row in plan.md (see Record).

## Flow

- B3, build stage, lead: after B2 passes for the item.
- Next: B1 for the next row whose status is `todo`. After the last row, the verify stage starts with V1.
- A fix in review (R3), or for a finding sent back from the verification session, is committed with the same steps, as its own commit. It changes no row of plan.md, unless the fix is a new row.
- The commit fails (a hook, a lock) and your fix does not help: try once more. If it still fails, stop and report it for the person.

## Record

- One work item, one commit.
- In `$AF_TASK_DIR/plan.md` (the task folder), set the item's row: `status` to `done`, and `commit` to the short SHA. For example:

```
| W2 | Print the list as JSON | `pytest tests/test_list.py` passes | src/list.py, tests/test_list.py | tdd | done | 3f2a9c1 |
```

- plan.md is outside the clone. Do not commit it.

## Rules

- No AI attribution in any message: no `Co-Authored-By` trailer, no "Generated with" line.
- Never use `--no-verify`. Do not amend a commit; make a new one.
- Never commit a secret, an `.env` file, or build output.
