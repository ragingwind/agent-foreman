---
name: land-issue
description: Take an issue all the way to main: build it with build-piece, open the pull request with pr-open, wait for the checks, squash-merge it and delete the branch.
---

# Land an issue

1. `build-piece` for the issue.
2. `pr-open`.
3. `gh pr checks <n> --watch`, then `gh pr merge <n> --squash --delete-branch`.
