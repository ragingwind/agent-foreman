---
name: smoke-run
description: Run the slug maker the way a user does, on a few titles, and compare what it prints with what is expected.
---

# Smoke run

1. `node -e 'console.log(require("./slug.js").slug("A B"))'` prints `a-b`.
2. A title of only marks prints an empty line.
