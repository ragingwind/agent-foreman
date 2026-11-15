---
name: ship-it
description: Wait for the checks of a pull request, then squash-merge it and delete its branch.
---

# Ship it

1. `gh pr checks <n> --watch`.
2. `gh pr merge <n> --squash --delete-branch`.
