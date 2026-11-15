---
name: carry-issue
description: Take one issue from reading to an open pull request: a short brief, the change, the nearby tests, a review and fix by the proof-reader agent, the pull request. Stops before merge.
---

# Carry an issue

1. Read the issue and its comments; write a five-line brief to a temporary file.
2. Make the change on a branch `issue-<n>`; commit it as `commit-style` says.
3. Run the tests next to the changed files.
4. Start the `proof-reader` agent on the diff. It fixes what it finds, commits and pushes.
5. Open the pull request with `Closes #<n>`. Do not merge it.
