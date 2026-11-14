---
name: simplify
description: >-
  Make the code in this task's diff easier to read and simpler, without
  changing what it does: one change at a time, the item's tests after each,
  a revert when they fail, and each kept change committed apart from the
  feature commits with a subject that starts with "Simplify". Use in the build
  session's review stage (step simplify), after the pair's first review,
  whatever its verdict, and before its findings are fixed.
---

# Simplify

## Action

1. List this task's changes: `git diff origin/<base>...HEAD`, with the base the brief names. Work only on lines that this diff added or changed.
2. Read the pair's findings about readability in its newest answer under `$AF_TASK_DIR/reviews/` (the task folder). Add what you find yourself.
3. Look for: deep nesting, long functions, nested ternaries, repeated logic, dead code, unclear names, and wrappers that add nothing.
4. Before you change a piece of code, learn why it is there. Read its callers and its tests.
5. Make one change. Follow the project's own style. A change that only fits your taste is not simpler.
6. Run the tests of the item that owns the code: the tests its done-when names in plan.md.
   - They pass: commit this change alone. The subject starts with `Simplify`, for example `Simplify the retry loop in fetch_page`.
   - They fail: revert this one change with `git checkout -- <files>`, and go on to the next one.
7. A clean-up too large for this task is not done here. It is too large when it reaches code outside the diff or needs a design change. Write it as a follow-up (see Record).
8. Stop when the list is done. The goal is code that is easier to read, not fewer lines.

## Flow

- Step `simplify`, lead: after `review`, once per review stage. It ends with outcome `done` (next: fix), also when there was nothing to simplify.
- A change that fails in a way you cannot explain: revert it and leave it. Any other problem, such as tests that do not run at all: try once more. If it still fails, stop as blocked.

## Record

- Each kept change is its own commit, apart from the feature commits. Its subject starts with `Simplify`. It holds no test file and no feature code.
- No row of plan.md changes.
- A large clean-up goes in `$AF_TASK_DIR/handoff.md` under `## Follow-ups`, as one line: `- <where> — <what to clean up> — <why it is not done here>`. Create the file with that heading if it does not exist yet. The handoff skill keeps the line.

## Rules

- Keep the behavior: the same output, the same errors, the same side effects, in the same order.
- Do not change an existing test. A clean-up that needs a test change is a behavior change; do not make it.
- Do not remove error handling to make code shorter.
- Do not touch code outside this task's diff.
