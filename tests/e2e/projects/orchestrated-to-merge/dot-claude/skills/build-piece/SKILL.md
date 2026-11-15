---
name: build-piece
description: Make the change an issue asks for in the current checkout, with its tests, and commit it. Opens no pull request.
---

# Build a piece

1. Write the test the issue implies; see it fail.
2. Make it pass. Run `node --test`.
3. Commit with the issue number in the subject.
