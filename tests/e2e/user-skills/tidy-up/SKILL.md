---
name: tidy-up
description: Tidy a working diff without changing what it does: clearer names, shorter functions, no dead code. One change at a time, tests after each.
---

# Tidy up

1. List what reads badly in the diff.
2. Fix one item, run the tests, keep it only when they pass.
3. Repeat. Commit the tidy-up apart from the feature.
