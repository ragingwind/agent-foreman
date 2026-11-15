---
name: patch-and-pr
description: Patch the code for an issue and open a pull request: the change, a fix-up pass by the fixer-bot agent, release notes, the pull request.
---

# Patch and open a pull request

1. Make the change and commit it.
2. Start the `fixer-bot` agent on the diff.
3. Stamp the build: `sh ~/.claude/skills/patch-and-pr/scripts/stamp.sh`.
4. Write the release notes with `release-notes`.
5. Open the pull request.
