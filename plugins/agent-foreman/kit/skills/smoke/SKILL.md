---
name: smoke
description: >-
  Show that the built product is alive: build it, start it the way the project
  documents, make one real call that uses the change, check the answer, and
  stop it. Records each command and its raw output in plan.md. Use in the
  build session's verify step, after the tests near the change pass and
  before the scenario script runs.
---

# Smoke

## Action

1. Find how the project builds and starts, in its guides, scripts and CI files. Use the documented commands as written.
2. Pick the shortest run that shows the product works with the change in it:
   - a service: start it, wait for the line that says it is ready, send one request that reaches the change, and read the answer;
   - a command-line tool: build it, then run the changed command once with simple input;
   - a library: build it, then load it from outside the tests and call the changed code once.
3. Decide before you run what must appear: a status code, a quoted line, exit code 0 with a named output. "No error" is not enough.
4. Run it in your clone. Keep the raw output.
5. Stop what you started: the process, the containers, the temporary folder. Check that each one is gone, for example with `ps` or `docker ps`.
6. Compare the output with step 3. A pass needs the expected output, not only exit code 0.

## Flow

- Step `verify`: after `unit` passes. Pass → `cross-check` runs the scenario script; a trivial task has none, so the verify step ends with outcome `done`.
- Fail → the verify step ends with outcome `fail` (back to build, with the fix as a new row in plan.md); verify then runs again from the start.
- A failure outside the product, such as a port in use or a missing tool: try once more. If it still fails, stop as blocked.

## Record

Add one entry under `## Checks` in `$AF_TASK_DIR/plan.md` (the task folder) for each command, in exactly this shape:

````markdown
### Smoke: <what must appear>
```
<command>
```
```
<raw output>
```
````

- The name says what must appear, for example `Smoke: GET /health answers 200 "ok"`.
- Paste the output as it came, with secrets masked. Keep the ready line and the answer.
- When verify runs again, replace the old smoke entries with the new ones.

## Rules

- Stop only what you started. Never stop another person's process to free a port.
- Leave nothing running when you are done.
