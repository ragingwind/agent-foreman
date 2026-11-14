---
name: cross-check
description: >-
  Write a scenario script that a person can follow alone to see the task's
  result as a user sees it, run it in a fresh clone and fill each step with the
  real output, and later run it again as a user, without the diff, and compare.
  Writes scenario.md in the task folder. Use in the build session's plan stage
  to write the script (P4; for a bug, reproduce it first), in its verify stage
  to run it (V3), and by QA in the verification session for the user scenario
  test (T2).
---

# Cross-check

One script, run twice. The lead's run shows that the script is right and the product works. QA's run shows that a user who follows it gets the same result.

## Action

**P4, write (lead).**
1. For each done-when in `$AF_TASK_DIR/task.md` (the task folder), plan the steps that show it as a user sees it: a command, a page, a file.
2. For a bug, reproduce it on the real surface before any fix. Those steps are the first draft. Keep what they printed for `## Closing`.
3. Write the preamble and the steps in the shape under Record. Write each Expect now, before any run. It must be something a broken build would not show.
4. One step is one act with one result. Every command is complete and ready to paste. A value that a later step needs goes through a file in the start directory, not a shell variable. A step that depends on its folder starts with its own `cd`.
5. Bringing the environment up is a step. Taking it down is a step. Leave every Agent block empty.

**V3, run (lead).**
1. Make a fresh clone at the head commit: `git clone <your clone> <new dir>`, then `git -C <new dir> checkout <head sha>`.
2. Search the script for what only your machine has: a literal port, `/Users/` or `/home/`, a `<...>` that no step prints, `...` in place of a command. Fix each one.
3. Run the steps in order, exactly as written. Paste each output into its Agent block, word for word, with secrets masked.
4. Anything you did that the script does not say (a wait, an install, a variable) is a missing step. Add it, and run again from step 1.
5. A step fails. A script problem: fix the script and run again from step 1. A product problem: go to build (see Flow).
6. See each main Expect fail once: run its step in a clone at the base commit, or with the fix taken out. For a bug, the reproduction already did this.
7. Take down what you brought up. Write `## Closing`.

**T2, user scenario test (QA).**
1. Read `$AF_TASK_DIR/scenario.md` only. Do not read the diff, plan.md, or the code.
2. Start in your own clone at the head commit, in the start directory the preamble names.
3. Run each step's Do as written. Fill a placeholder only from what an earlier step printed. Read the Agent block after the step has run, not before.
4. Compare your output with the Expect and the Agent block. A value that changes per machine (a port, a path, a time, an id) is not a mismatch.
5. A mismatch is a different result, a step you could not do as written, or a value the script did not say where to get. Name its cause: `script` (the script left out something), `environment` (your machine, data or permissions differ), or `product` (the product behaves differently).
6. Run the steps that take things down, even after a mismatch. Change nothing the script does not tell you to change.

## Flow

- A trivial task (the brief says so) has no scenario: skip P4, V3 and T2. The gate does not ask for scenario.md then.
- P4, plan stage: after P1 to P3. Next is the build stage.
- V3, verify stage: after V1 and V2. Pass (every Agent block filled, `Verdict: pass`) → the review stage. Script problem → fix it and run again. Product problem → build, with the fix as a new row in plan.md.
- T2, verification session: QA runs it next to T1. The brief skips it for a trivial change. No mismatch → pass. `product` → build. `script` → verify: the lead fixes the script and runs V3 again. `environment` → the person.
- Anything else off the path, such as a clone that fails: try once more. If it still fails, stop and report it for the person.

## Record

P4 and V3 write `$AF_TASK_DIR/scenario.md` in this shape:

````markdown
# Scenario: <task title>

Start directory: <the root of a clone at the head commit>
Terminals: <N>
Environment: <the one command that brings it up>

### 1 · <the act, not the command>

<One line: why this step is here.>

**Expect** — <a quoted line, a count, a named result>

**Do**

```bash
<the command>
```

**Agent**

```
<what the last full run printed>
```

## Closing

Verdict: pass
- Brought up: <what>. Brought down: <how; it is gone>.
- Blocked: <what blocked> — <what fixed it>.
- Seen failing: step <N> — <how it was made to fail, and what it printed>.
- Not verified: <what no step checks, or "nothing">.
- Where: <a fresh clone at <sha>, on which machine>.
````

- With nothing to bring up, write `Environment: none — <reason>`.
- A hand act writes one imperative sentence after `**Do** —` in place of the fence. It names the control and the page.
- The first line under `## Closing` is `Verdict: pass` or `Verdict: fail`, for the last full run. An Expect never seen failing goes under "Not verified".
- T2 writes no file. launch.py saves QA's answer under `$AF_TASK_DIR/reviews/`. Each mismatch is one line, `mismatch (script|environment|product): step N — <what differed>`, with a fence of the differing output under it. The last line is `Verdict: pass` (every step ran and matched) or `Verdict: fail`.
