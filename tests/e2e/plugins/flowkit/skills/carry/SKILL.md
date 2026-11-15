---
name: carry
description: Take one issue to an open pull request: a five-line plan, the change, a review by the checker agent, the pull request. Never merges.
---

# Carry

1. Write a five-line plan for the issue.
2. Make the change on a branch `issue-<n>` and commit it with `flowkit:commit`.
3. Ask the `flowkit:checker` agent to review the diff; apply what it reports.
4. Note the run: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/note.sh" carried <n>`.
5. Open the pull request with `Closes #<n>`. Never merge it.
