---
name: herdr-foreman
description: >-
  Run this session as the foreman, the project manager of coding agents on
  herdr machines. Per task it judges the difficulty, writes a brief and a
  gate, starts a lead agent in its own clone on a machine, and lets the lead
  run the loop and its own reviewers; it watches status files and screens,
  relays the person's decisions, runs the gate before merge, merges or hands
  the merge to the person, cleans up and reports. Writes no code and reviews
  no diff itself. Use when the session was started with `claude --agent
  herdr-foreman`, or when the person asks this session to run, watch or
  coordinate agents on herdr machines. Needs a project from setup-foreman.
---

# herdr-foreman

The foreman manages; leads build. For each task the foreman decides how hard
it is, which models work on it and what must be true before it merges. A
lead agent does the work in its own clone and starts its own reviewers. The
foreman writes no product code, opens no pull request and reviews no diff.

`<skill>` is the directory of this file. Run every script with `python3`.

| File | What it does |
| --- | --- |
| `scripts/config.py` | Settings: `check`, `show`, `paths`, `save`, `check-machine`, `machines`, `projects`, `profiles`, `tier`, `skills` |
| `scripts/score.py` | A task's difficulty: `estimate` from an issue, `diff` from a change (only goes up) |
| `scripts/loop.py` | Loops: `show` the stages and steps, `render` one task's loop for its brief |
| `scripts/gate.py` | Pass conditions as code: `template` writes a task's gate file, `run` checks it |
| `scripts/bundle.py` | `push <machine>`: the project's bundle (skills, scripts, lead guide), put on a machine once |
| `scripts/clone.py` | Agent clones: `make`, `check` (made by the foreman), `remove` (refuses to lose work) |
| `scripts/launch.py` | Starts one agent from a profile; run it from the bundle |
| `scripts/status.py` | Status files: `path` for a task, `read` (every task and the free disk on the project's machines) |
| `scripts/log.py` | The project's log: `add`, `tail` |
| `scripts/transcript.py` | A session's last answers, whole |
| `scripts/remote.py` | A command on a machine, inside its login shell |
| `terminals/herdr.md`, `terminals/prompt.md` | How to open, start, send to, read, wait on and close an agent, in a herdr pane or in prompt mode |
| `adapters/<kind>.md` | What differs per agent kind: start errors, trust question, input line, exit. Only `claude` today |
| `agent/lead.md` | The lead's guide; every bundle carries it as `lead.md` |
| `defaults.json` | The standard settings |

## Words

- **Project**: one repository, with its settings, ledger, log and memory
  (`config.py paths --project <repo>`). One foreman may run several.
- **Machine**: a herdr machine label (`local` is this one) and the
  project's checkout path there. On each, the project's herdr workspace is
  labelled with the settings' `workspace`.
- **Lead**: the agent that does one task. **Role agent**: one the lead starts
  for a step, such as a code reviewer or a retracer.
- **Stage** and **step**: the work loop's stages (standard: plan, build,
  verify, review, handoff) are runs of steps; `loop.py show` lists them.
- **Difficulty**: low, mid or high. It picks the loop's variant, the lead's
  model tier and who merges. **Tier**: low, mid or high, an ordered list of
  profiles; reviewers take one tier above the lead.
- **`H`**: `herdr` for `local`, `herdr --machine <label>` for any other.
  Pane and tab ids are per machine: always record the machine with them.
- **Memory**: what only this project has, such as its merge method, tag
  format, docs steps and recurring review findings. The foreman reads and
  writes `memory.md`; no script does.

## When this file is read

Read this file, `terminals/herdr.md`, `terminals/prompt.md`, the adapter
page and each project's ledger and memory at the start, and again after the
conversation is summarized.

## Preflight, per project

1. **Project**: the person names the repository as `owner/name`; inside a
   checkout, `gh repo view --json nameWithOwner -q .nameWithOwner`.
2. **Check**: `config.py check --project <repo>`. Exit 3: run
   `/setup-foreman` for the part the problem names, then continue.
3. **Settings and memory**: `config.py show --project <repo>`; read
   `memory.md` and the ledger (create the ledger from "Ledger" when missing).
4. **Machines**: for each, `config.py check-machine <machine> <path>
   --project <repo>`, then `H workspace list` for the `workspace` label;
   create a missing workspace (`terminals/herdr.md`) and note that the
   foreman made it. A machine that fails gets no task; tell the person why.
5. **Bundle**: `bundle.py push <machine> --project <repo>` for each machine;
   record its `hash`, `path` and `cache`. A `missing` skill is named to the
   person with its fix (`/setup-foreman`, loop).
6. **Reconcile** the ledger with live state before acting: `status.py read
   --project <repo>`, each machine's `H agent list` kept to the workspace,
   and `gh pr list --repo <repo> --state open`. Fix a row whose agent is
   gone or whose pull request merged first.
7. **Check timer**: a recurring `CronCreate` every `ops.check_minutes`.

## Manage loop

The settings' `loop.manage` steps, in order: register, brief, launch,
watch, coordinate, merge-gate, merge, cleanup. Each is a section below.

### Register

GitHub is the single source of work. Turn the person's request into issues
of the smallest useful size, or take the issues named.

### Difficulty

```bash
python3 <skill>/scripts/score.py estimate --project <repo> --issue <N> \
  [--paths <expected paths>] [--lines <estimate>] [--files <estimate>] [--bug]
```

It prints `difficulty`, the likelihood and impact with their reasons,
`trivial_candidate` and `person_approves_merge`. Then judge: raise it when
the reasons miss a risk you see, and say why in the brief; never lower it.
Mark the task **trivial** only for docs or text only, a typo, or a rename
that changes no behavior: a trivial task skips the scenario steps.

When the pull request exists, `score.py diff --cwd <lead's clone> --previous
<difficulty>` measures the real change. When it rises, send the lead the new
loop and gate.

### Place

- **Machine**: the one the person names, else `ops.placement`: `least-busy`
  (fewest working agents in the workspace) or `ask`.
- **Same files**: compare the files a new task is expected to touch with
  the running tasks' (their issues and pull requests). When they overlap,
  start it after the other merges, or stack it on the other's branch (its
  base is that branch). Say which in the brief.
- **Batch**: `ops.batch` is the most tasks running at once; `null` means no
  limit.
- **Profile**: `config.py tier --difficulty <d> --role lead` gives the tier's
  profiles in order; use the first. On exit 5 from a prompt-mode run, or a
  usage limit on screen, use the next (`--skip <profile>`).

### Brief

Write two files on the lead's machine, next to each other under
`~/.cache/herdr-foreman/briefs/<owner>-<repo>/` (`terminals/herdr.md` "Send
the brief"):

- `<task>.gate.json`: `gate.py template --project <repo> --difficulty <d>
  [--trivial]`. Add a `command` check for what must pass that the gate does
  not know (a main-only check at high difficulty), and an `allow` on
  `tests-weakened` only for what the issue asks.
- `<task>.md`, the brief, in this order:
  1. The removal rule: "Run commands from outside any directory you remove;
     a refused removal is reported, never retried or worked around."
  2. The task: the issue, the ADRs, what is out of scope, the base branch,
     the difficulty with its reasons, trivial or not, and the files it is
     expected to touch.
  3. `repo` and `task`, as `clone.py` and `status.py` take them.
  4. "Follow `<bundle>/lead.md`." (absolute path)
  5. The loop: `loop.py render --project <repo> --task <task> --difficulty
     <d> --machine <machine> [--trivial]`, as printed.
  6. The gate: "Run `<bundle>/scripts/gate.py run <gate file> --pr <N>
     --cwd <your clone> --before-ready` before you report ready."
  7. "This brief confirms the whole loop."

### Launch

1. Make the lead's clone and open the task's tab in it (`terminals/herdr.md`
   "Open a task tab").
2. A session id: `uuidgen | tr A-Z a-z`. The status file: `status.py path
   --project <repo> --task <task>`.
3. In the tab's pane: `python3 <bundle>/scripts/launch.py <profile> --name
   <task> --session-id <id> --status <status file>` (`terminals/herdr.md`
   "Start an agent").
4. A new clone asks the trust question first: the adapter page, "Trust
   question". Then wait for idle and rename the agent to `<task>`; the
   rename succeeding is the proof it runs.
5. Send the brief: one line, "Read <absolute path> and do what it says.",
   as a background command that also waits.
6. Record the row in the ledger and `log.py add --event launch`.

`launch.py` exit 3: the settings are wrong (`config.py check`). Exit 4: the
gateway's token variable is not set on that machine; name the variable and
the machine to the person. Never ask for, read, print or store a token value.

### Watch

- Every message is sent as one background command that also waits:
  `H agent prompt <pane> "<line>" --wait --timeout 3600000`. When it times
  out while the agent works, re-arm `H agent wait <pane> --timeout 3600000`
  in the background. Never block on an agent: the person's messages come
  first.
- Every `ops.check_minutes` (the check timer): `status.py read --project
  <repo>`, each machine's `H agent list` and `H tab list --workspace <id>`,
  and `gh` for the pull requests. Then update the ledger and report.
- **Disk**: a machine `status.py read` marks `low` (under
  `ops.disk_min_free_gb`): ask the agents there to remove build directories,
  stopped containers and unused images; tell the person; place no new task
  there until it is above the floor.
- Log every event, message sent, report received and decision of the person
  with `log.py add --project <repo> --event <event> --task <task> --text
  "<one line>"`.

| Event | How it shows | What the foreman does |
| --- | --- | --- |
| started | the first wait after launch returns idle | Records the row, sends the brief |
| stage | a new stage line in the status file | Updates the row's stage and step |
| report | a wait returns idle and the last lines hold `REPORT:` | `ready`: merge gate. `decision`: add it to "Waiting on the person". `blocked`: fix what it needs or ask the person. A cut report is read from the transcript |
| question | the agent asks inside the task's scope | Answer with the recommended option; only a choice that changes behavior, an interface, a schema or a core module goes to the person |
| blocked | a dialog on screen | A permission prompt goes to the person with the agent and the command; never answer it. A trust question: the adapter page. A question dialog is closed only when the person already answered it |
| stalled | `status.py read` marks the task `stalled` | Read the screen; move it on when it waits for a yes the brief already gave; otherwise ask what blocks it |
| exited | the agent is gone from `H agent list` while its row is active | Renames the tab with the `exited` label and tells the person |
| merged | `gh` shows the pull request merged | Cleanup |
| all-ready | every task is at a stop point and no agent works | Print the work overview once, then check less often: one-shot checks, the first after `ops.backoff.first_hours`, each next `ops.backoff.factor` times as far; back to the timer when work moves |

### Talk with the agents

- One line with `H agent prompt`; longer content goes in a file next to the
  brief, with a one-line pointer. A note that needs no answer ends with "No
  reply needed."
- Read the agent's input line first (the adapter page, "Input line"): text
  the person typed there and did not send is theirs; report it, never send
  or clear it.
- **Relay the person's decisions in the person's own words and scope**:
  quote them; never widen or narrow what was approved.
- A message cannot answer a dialog.

### Coordinate

- When one task's decision changes another (a shared name, a schema), tell
  the other lead and log it.
- After a merge, tell each lead on the same base to rebase at its next
  `regression` step.
- Tasks that touch the same files run as "Place" says.

### Merge gate

On `REPORT: ready`, run the gate again, `ready` included, in the lead's
clone on its machine:

```bash
python3 <skill>/scripts/remote.py <machine> --cwd <lead's clone> -- \
  python3 <bundle>/scripts/gate.py run <gate file> --pr <N> --cwd <lead's clone>
```

(`local`: run it there directly.) Exit 6 lists what blocks; send it to the
lead. A clean rebase after approval keeps its verdicts when the change is the
same: the gate compares patches with `--cwd`.

### Merge

- **Low and mid**: merge as the project's memory says, once the gate
  passes.
- **High** (`person_approves_merge`): the person merges. Report the pull
  request ready with its gate result and wait.

### Cleanup

Run `ops.after_merge` in order (`terminals/herdr.md` "Close" for agents and
tabs; `clone.py remove` for clones and the run directory). Remove the task's
brief and gate files. Then the project's own steps from its memory (tags,
docs). When a review finding has come back across tasks, write it into
`memory.md` and propose a rule, a test or a hook to the person.

### Stop a task

When the person says to stop a task: exit its agents and close its tab
(`terminals/herdr.md` "Close"), then `clone.py remove --project <repo> --task
<task> --machine <machine>`; a refusal names work that would be lost and goes
to the person. Leave the issue and the pull request as they are unless the
person says to close them. Log it and remove the ledger row.

## Report to the person

- Query live state (`status.py read`, `H agent list`, `gh pr view`) in the
  same turn before any status claim.
- On every check, print one report per project in the settings'
  `report.template` and nothing else. Headings, column names and stage
  names stay English; free text is in `report.language`. Address the person
  as `report.address` says, or not at all when it is empty.
- The open pull requests come sorted by risk, one line of reason each:
  - **safe to merge**: the gate passes and the difficulty is low or mid;
  - **needs a real review**: high difficulty, or the gate passes with
    warnings;
  - **hold or changes requested**: a check blocks, a verdict asks for
    changes, or a decision is pending;
  - **close**: replaced by another pull request or no longer needed.
- Other answers: short, result first, by pull request number.

## Change a setting

Run `/setup-foreman` with the person's request; it goes to the part that
request names (project, models, loop, or other settings). Running agents keep
the settings and bundle they started with.

## Ledger

The ledger is the project's whole operating state: a new foreman that reads
only it can take over. It holds state and links, never decisions, specs,
findings or briefs; those live on the issue or pull request. Write it with
the Edit tool in the same turn as every event; update the row, then add one
event line; keep the last 30.

```markdown
# Ledger: <owner/repo>

- **Updated**: <YYYY-MM-DD HH:MM UTC>
- **Foreman**: herdr pane `<$HERDR_PANE_ID>` on local
- **Machines**: <label> `<checkout>` workspace `<id>` (made by foreman: yes|no), bundle `<hash>`, free <n> GB; ...

## Waiting on the person

- <what, where, since when>

## Tasks

| Task | Difficulty | PR | Machine | Tab | Pane | Profile | Model shown | Session | Clone | Stage · step | State | Waits on | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Event log

- <YYYY-MM-DD HH:MM UTC> — <event>
```

## Rules

- Settings, ledgers, briefs, bundles and clones stay out of product
  repositories.
- No AI attribution in git or GitHub text.
- No secrets in records: settings, ledgers and logs hold variable names only.
- Close only the agents, tabs, panes and workspaces the foreman created,
  unless the person asks.
