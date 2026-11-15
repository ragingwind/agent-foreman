---
name: wave-batch
description: Run several issues at once: one git worktree per issue beside the checkout, an agent in each, and a merge of each pull request as it finishes.
---

# Wave batch

1. For each issue: `git worktree add ../streak-<n> origin/main`.
2. Start an agent in each worktree with `land-issue`.
3. Merge each pull request when its agent ends; remove the worktree.
