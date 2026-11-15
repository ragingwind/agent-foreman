# agent-foreman architecture

This is the design the code follows. Where the code and this page differ, the
page is the target and the code is behind it.

`tests/test_architecture.py` checks the pictures in sections 1 and 6, and the
picture in `README.md`, against `defaults.json` and `status.py`: change a
loop or `status.py note` and its picture together. Every picture is plain
text; a loop is drawn as a sequence, with its outcomes listed under it.

## 1. Who does what

| Agent | Role | Started by | Runs as |
| --- | --- | --- | --- |
| Foreman | The project's manager: registers tasks, judges each task's difficulty, writes each task's brief, `loop.json` and gate file, watches, runs the verification session, merges (low and mid difficulty), archives and cleans up, talks with the person | The person | The person's harness session (Claude Code) |
| Lead | Owns one task: runs its build session in its own clone, starts its pair, runs the gate before it marks the pull request ready, reports | Foreman | The first pane of the task's tab |
| Pair | Reviews the lead's diff (step `review`) and the fixes (step `recheck`) | Lead | A prompt-mode run (`launch.py --print --role pair`) in its own clone at the lead's head |
| Red team | Tries to break the change (step `redteam-review`) | Foreman | A prompt-mode run in its own clone at the lead's head |
| QA | Runs the full tests and the user scenario test (step `test`) | Foreman | A prompt-mode run in its own clone at the lead's head |
| Helper, audit lead, scenario agent | The epic loop's roles | Foreman | A pane |
| Person | Decisions that need approval, high-difficulty merges, blocked removals, permission prompts, findings no script can settle | — | — |

```text
 PERSON           FOREMAN                            LEAD                 ROLE AGENTS
   │                │                                 │
   │ task           │                                 │
   ├───────────────▶│ register   task.md              │
   │                │ brief      loop.json            │
   │                │            gate.json + sha256   │
   │                │ launch ────────────────────────▶│ work loop, round 1
   │                │ watch, coordinate               │ review, recheck ─▶ PAIR
   │                │◀────────────────── REPORT ready │
   │                │ verify-session ─────────────────────────────────────▶ RED TEAM ∥ QA
   │                │◀──────────────────────────────────────────── verdicts
   │                │ sent back? ── findings-r<N>.md ▶│ round N+1
   │                │ merge-gate  gate.py run --sha   │
   │                │ merge                           │
   │                │ cleanup    archive, remove      │
   │◀─────── report │ ■ STOP                          │
```

The foreman manages leads, not the pair. A lead never needs the foreman to
move a task from one step to the next; the foreman steps in at stop points,
on a missed report, and on events the lead cannot handle.

Every agent gets its own profile, so one task can mix gateways: a lead on a
token-factory model and a red team on Anthropic opus are two processes with
two environments (`launch.py` clears the gateway variables before it sets a
profile's). The pair, the red team and QA never run on the lead's profile.

## 2. Layers

```text
┌──────────────────────────────────────────────────────────────────┐
│ foreman: loop control                                            │
├──────────────────────────────────────────────────────────────────┤
│ terminal layer: herdr, prompt mode     (later: tmux, ghostty)    │
├───────────────────────────────────┬──────────────┬───────────────┤
│ tab: one task's session           │ tab 2        │ ...           │
│ pane 1: lead                      │              │               │
│ prompt runs: pair, red team, QA   │              │               │
├───────────────────────────────────┴──────────────┴───────────────┤
│ agent adapter: claude                  (later: other kinds)      │
└──────────────────────────────────────────────────────────────────┘
```

**Terminal layer.** One interface, several adapters. herdr and prompt mode
are first-class; tmux and ghostty come later behind the same interface.

| Operation | herdr | Prompt mode |
| --- | --- | --- |
| machines | saved herdr machines (SSH targets) | SSH targets |
| open a session | tab in the project's workspace | the agent's own clone; its prompt and answer go in the task folder's `reviews/` |
| start an agent | `pane run` of `launch.py` | a `launch.py --print --role` command that `loop.py prompt` prints, on another machine through `remote.py` (its login shell) |
| send | `agent prompt`, `send-text`, `send-keys` | not possible: one prompt per run |
| read | `pane read`, transcript | the JSON result in `reviews/`, transcript |
| wait | `agent wait` | the process exits |
| close | exit, `tab close` | nothing to close |

**Agent adapter.** What differs per agent kind (command, skill delivery,
transcript, checkout readiness, screen rules). Only `claude` exists.

## 3. Settings

| Scope | What | File | Written by |
| --- | --- | --- | --- |
| Global | Models: providers (token variable names only), their models and the tiers | `~/.config/agent-foreman/providers.json` | the person, after setup: models makes it |
| Global | Standard loop: stages and steps, skills per step, variants per difficulty | `~/.config/agent-foreman/config.json` | setup: loop |
| Project | Machines (SSH devices) and the project path on each; loop changes for this project | `~/.local/state/agent-foreman/projects/<owner>-<repo>/project.json` | setup: project |
| Project | Memory: values only this project has (tag format, docs steps, disk floor, labels) | `.../projects/<owner>-<repo>/memory.md` | the foreman |

A level stores only what differs from the level below. The package ships the
standard values.

## 4. Models

- **Providers.** `providers.json` lists each provider (Anthropic, or an
  anthropic-compatible endpoint with its URL, auth and token variable name)
  and its models. A model's `name` (default: its `id`) is its **profile**:
  the name tiers, `loop.json` and `launch.py` use. Scripts turn the file
  into the gateways and profiles they run on (`config.py`).
- **Tiers.** `high`, `mid`, `low` (상·중·하), in the same file. Each tier is an
  ordered list of profiles.
- **Standard tiers** are the harness's own models: for Claude Code, low =
  `haiku`, mid = `sonnet`, high = `opus` then `sonnet`. `fable` is never in a
  standard tier.
- **Other models** (`fable`, token-factory models, any other provider) enter
  a tier only when the person puts them there in `providers.json`.
- **The lead.** The task's difficulty gives the lead's tier; the lead runs on
  its first profile, and on a usage limit on the next one.
- **A role** takes the difficulty's tier raised by the role's `step` in the
  settings, capped at high: standard, the pair 0, the red team and QA 1. It
  may run on that tier's profiles and then each higher tier's, never a lower
  tier's, and never on the profile the lead runs on, which `loop.json`
  records (`loop.py render --lead`). `loop.py prompt` prints the launch
  commands in that order; on exit 5 (a usage limit, a gateway error) the
  next one runs.
- `config.py check` reports a difficulty whose lead has no profile, or whose
  role has no profile but the lead's.
- **No `providers.json`** means the standard tiers above: the harness's own
  models. `config.py providers --init` copies `providers.json.sample`, which
  holds them, into the file to edit.

## 5. Difficulty

The foreman sets each task's difficulty from a score and its own judgment.

- **Likelihood L** (0-3, one point each): more than 400 changed lines or more
  than an hour of human work; more than 10 files or 3 or more top-level
  directories; a bug fix, or touched files with a fix in the last 90 days.
- **Impact I** (the highest that applies): 3 authentication or secrets,
  money, schema or data migration, deletion, CI or deploy configuration, or a
  path on the project's critical list; 2 user-visible behavior, a public API
  or a shared library; 1 other runtime code; 0 docs or tests only.
- **Level** = I when L is 0 or 1, else I + 1 (at most 3).
- **Difficulty**: low = level 0, mid = level 1, high = level 2-3. The person
  merges every high-difficulty pull request.
- `score.py estimate` scores an issue before any code, from the paths and
  size the foreman expects and the issue's labels. `score.py diff` scores the
  change once it exists (`git diff BASE...HEAD` and the touched files' fix
  history); run it in the lead's clone, through `remote.py` on another
  machine. With `--previous` the difficulty only ever goes up.
- The thresholds (400 lines, 10 files, 3 top-level directories, 90 days) and
  the path patterns for critical, public, docs and test paths are the
  `difficulty` settings; a project adds its own critical paths there.
- The foreman adds what paths cannot show (does a user or caller observe the
  change? does it change a public API or a shared library?) and decides.
  `score.py` also flags a docs-only change as a trivial candidate.

Sources: Kamei et al. 2013 (just-in-time defect prediction), Meta Diff Risk
Score, ISTQB risk-based testing, Rigby & Bird 2013 (two reviewers), Google
small-CL guidance. The thresholds are a starting point; the log keeps each
task's level and outcome (reverts, follow-up fixes) to tune them.

## 6. Loops

A loop is a list of steps. Each step has an actor, what it does, the skills
it uses, and `next`: where each outcome goes, a step id or `stop`. The last
outcome in `next` is the success path; `config.py check` reports a loop whose
success path does not reach `stop` from the work loop's first step and from
each check step. The rules per difficulty (`run`, `count`, `extra`) are on
the steps. A stage is a run of steps with the same `stage`; tab labels,
status lines and reports follow the stages. Setup (loop) designs the loops;
each project can change them.

**The task's loop.** With the brief, the foreman writes the task's loop into
its task folder as `loop.json` (`loop.py render --json`): the work and check
steps that run for this task, its base, the lead's profile, and each role's
prompt and profiles. `status.py note`, `loop.py prompt` and the gate read
it, so a task keeps the settings it started with; the gate file holds its
hash.

### Work loop: the build session (lead)

```text
 WORK LOOP · the build session, round N
 LEAD (own clone)                                PAIR (other model)  status.py note
  │                                               │                   │
  │ plan      plan.md rows, scenario.md ─────────────────────────────▶│ end done
  │ build     one row at a time, its tests ──────────────────────────▶│ end done
  │ verify    tests, smoke, scenario.md ─────────────────────────────▶│ end done | fail
  │ review    clone at head, loop.py prompt ─────▶│                   │
  │◀──────────────────────────── answer, Verdict ─│                   │
  │           ───────────────────────────────────────────────────────▶│ end done
  │ simplify  clean-up commits ──────────────────────────────────────▶│ end done
  │ fix       must-fix, should-fix ──────────────────────────────────▶│ end done | large
  │ recheck   only the fixes, loop.py prompt ────▶│                   │
  │◀──────────────────────────── answer, Verdict ─│                   │
  │           ───────────────────────────────────────────────────────▶│ end approved | changes
  │ finalize  rebase, handoff.md, draft PR,       │                   │
  │           gate --before-ready, gh pr ready ──────────────────────▶│ end done | conflict
  │                                               │                   │
 outcomes:
   plan ─done─▶ build                  build ─done─▶ verify
   verify ─done─▶ review               verify ─fail─▶ build
   review ─done─▶ simplify             simplify ─done─▶ fix
   fix ─done─▶ recheck                 fix ─large─▶ build
   recheck ─approved─▶ finalize        recheck ─changes─▶ fix
   finalize ─done─▶ stop               finalize ─conflict─▶ build
 actors: lead = plan, build, verify, simplify, fix, finalize · pair = review, recheck
 a trivial task skips: review, simplify, fix, recheck
```

- The stages are plan, build, verify, review (review, simplify, fix,
  recheck) and finalize.
- The pair's `review` always ends with `done`: its findings go to simplify
  and fix. In `recheck` the pair's verdict is the outcome. The lead starts
  the pair: a clone at its head (`clone.py make --no-push`), then `loop.py
  prompt --step <step>` there, which writes the filled prompt into `reviews/`
  and prints the launch commands.
- finalize: rebase, `handoff.md`, a draft pull request whose body is
  `handoff.md`, `gate.py run --before-ready`, then `gh pr ready`.
- A **trivial** task (docs or text only, a typo, a rename that changes no
  behavior; the foreman marks it in the brief) skips the steps the picture's
  last line names: its loop is plan → build → verify → finalize, with no
  scenario and no pair.
- A **round** is one pass of the build session: 1 at first; the foreman gives
  the next number when the verification session sends the task back
  (`status.py note --round`).

A **scenario** (`scenario.md`) drives the change end to end through whatever
surface it reaches, as a user or caller would: an API, a CLI, a UI, a job.
The lead writes it in plan and runs it in verify in a fresh clone; QA runs it
again without reading the diff.

### Check loop: the verification session (foreman)

```text
 CHECK LOOP · the verification session, both steps at once
 FOREMAN                                  RED TEAM       QA     status.py note --file
  │                                           │           │           │
  │ gate --before-ready on the lead's claim   │           │           │
  │ redteam-review  clone at head, prompt ───▶│           │           │
  │ test            clone at head, prompt ───────────────▶│           │
  │◀──────────────────────── answer, Verdict ─│           │           │
  │◀──────────────────────────────────── answer, Verdict ─│           │
  │                 ─────────────────────────────────────────────────▶│ end, once per step
  │                                           │           │           │
 outcomes:
   redteam-review ─approved─▶ stop     redteam-review ─changes─▶ build
   test ─pass─▶ stop                   test ─fail─▶ build
   test ─script─▶ verify
 actors: redteam = redteam-review · qa = test
```

- On `REPORT: ready` the foreman runs the gate with `--before-ready` on the
  lead's claim, then starts both steps at once, each in its own clone at the
  lead's head, through `loop.py prompt` (models other than the lead's).
- The answer's verdict is the outcome, except when QA's `fail` comes only
  from `mismatch (script)` lines: then it is `script`.
- When both steps end in `stop`: the merge gate. When one names a work step:
  the foreman copies the findings to `reviews/findings-r<round>.md` and sends
  the lead back to that step with the next round (two different steps: the
  earlier one). After the lead is ready again, only the roles whose verdict
  check still blocks run again.
- To the person instead: no verdict, an `environment` mismatch, a `not run`
  test, a failure that also fails on the base, or 3 rounds that still find
  something. When the person says to merge anyway, the merge gate runs with
  `--skip verdict:<role>` for that role only.

**Variants by difficulty** (standard; setup changes them). Every difficulty
runs the same steps; only a trivial task skips the pair's steps.

| Difficulty | Lead | Pair | Red team, QA | Merge |
| --- | --- | --- | --- | --- |
| low | low tier | low tier and up | mid tier and up | foreman |
| mid | mid tier | mid tier and up | high tier | foreman |
| high | high tier | high tier | high tier | the person |

None of them runs on the lead's profile (section 4).

- Role agents start without edit tools (the role's `deny_tools`: `Edit`,
  `Write`, `NotebookEdit`). That narrows them; it is not a sandbox. Their own
  clone, whose push to origin fails (`clone.py make --no-push`), and the
  gate's check that each verdict is at the head commit keep their writes from
  reaching the pull request. A role agent never starts other agents.

### How a step moves

```text
 the agent                              status.py note                 status.jsonl
 --event start --step S ──────────────▶ append ──────────────────────▶ S start, round N
 --event end --step S --outcome X ────▶ X is one of S's next keys?
                                        ├─ no  ─▶ exit 2, nothing written
                                        └─ yes ─▶ append ────────────▶ S end, X, to Y
                                                  prints "next: Y"
                                                  (Y = stop: a stop point)
 starts Y ◀──────────────────────────── loop.md: follow the printed next step
```

- A script holds the outcome: an `end` line must name one of the step's
  `next` keys, and it records where the outcome leads (`to`). Going there is
  the agent's part, which `loop.md` asks.
- The gate's `steps` check needs an `end` line for every work step before
  finalize, from any round, so a step skipped in a later round passes it.
  The verdict checks still need answers at the head commit.

### Where it stops

| Stop | Who | When | Held by |
| --- | --- | --- | --- |
| Ready | Lead | finalize passed `gate.py run --before-ready`, the pull request is marked ready, and finalize ends with `done` | A script: `status.py note` prints `next: stop` and `status.py read` counts the task stopped. The foreman runs the gate on the claim before the verification session |
| A decision for the person | Lead | A choice the task does not settle that changes what a user or caller sees, an interface, a schema or file format, or a core module | A prompt (`loop.md`); the lead writes the stop line with `status.py note --event stop` |
| Blocked | Lead | Something it cannot get or do, after trying once more | A prompt; the stop line with `--blocked` |
| The third recheck still says `changes` | Lead | fix and recheck repeat | A prompt only (`loop.md`); no script counts rechecks |
| Ask the person | Foreman | No verdict, an `environment` mismatch, a `not run` test, a failure that also fails on the base, 3 rounds that still find something | A prompt (`SKILL.md`). Merging anyway takes `gate.py run --skip verdict:<role>`; the gate refuses a bare `verdict` |
| Merge blocked | Foreman | The merge gate exits 6 | A script (`gate.py`). A `gate-file` or `loop-file` block: tell the person and merge nothing |
| High difficulty | Person | The merge gate passed | A prompt (`SKILL.md`) |
| Done | Foreman | cleanup ended | — |

A script holds that every loop can reach `stop` (`config.py check`). Only
prompts hold that a cycle ends: fix and recheck, and the rounds of the
verification session.

### Management and epic loops

**Management loop** (foreman; the picture in section 1): register (task.md)
→ brief (`loop.json`, `gate.json` and its hash, `brief.md`) → launch → watch
→ coordinate (same-file tasks in sequence; relay the person's words as said)
→ verify-session → merge-gate → merge (high difficulty: the person) →
cleanup (archive, then remove) → the project's steps from memory (tag,
docs). A review finding that recurs goes into the project's memory, with a
proposed rule, test or hook. Each report sorts the open pull requests for
the person: safe to merge, needs a real review, hold, close.

**Epic batch loop** (optional, for projects that use epics): sync the epic
onto main, then tell every branch cut from the epic to rebase → persona audit
→ fixes through the work loop → user scenarios → epic-to-main pull request →
the person approves.

## 7. Skills

A step names its skills (`loop.py show`).

1. A **default skill** (`kit/skills/<name>`, one per loop action) ships in
   every bundle as `foreman-kit:<name>`. The settings' `skills` map may
   replace one with a project or local skill; the replacement changes how the
   action is done, never the flow or the record.
2. Any other skill, and a replacement, is looked up for the lead's machine:
   a project skill (`<checkout>/.claude/skills/<name>`) first, otherwise a
   user skill from the person's machine, which goes into the bundle (cached
   by content hash on that machine). `loop.py skills --project <repo>
   --machine <machine>` prints where each comes from; a missing one is named
   to the person with its fix (setup, loop).

## 8. Gates

Pass conditions are code, not prose (`scripts/gate.py`).

- **Checks**, each reading the task folder, git or GitHub:
  - `pr-open`: the pull request exists and is open.
  - `loop-file`: `loop.json` still has the hash the template wrote.
  - `steps`: `status.jsonl` has an `end` line for each work step before
    finalize.
  - `docs`: every row of `plan.md`'s work breakdown is done, `handoff.md` has
    its sections, and `scenario.md`'s closing verdict is pass with every
    Agent block filled (not for a trivial task).
  - `ci`: every status check finished and passed.
  - `base-fresh`: the head contains the base branch's head.
  - `verdict`: enough agents of a role whose latest answer in `reviews/`
    (`launch.py --role`) ran to the end with a `Verdict:` the role accepts,
    at the head commit (with `--cwd`, also at an earlier commit whose change
    is the same, by `git patch-id`), on a profile other than the lead's.
  - `tests-weakened`: no removed test file, added skip or focus marker,
    edited CI file or changed coverage threshold, except what `allow` names.
  - `size`, `ready`, and `command` (a command that must pass in the clone).
  - A check can be a warning instead of a block.
- `gate.py template --loop <loop.json>` writes a task's gate file: `pr-open`,
  `loop-file`, `steps`, `docs`, `ci`, `base-fresh`, a verdict check per role
  (the pair's before ready and at merge, the red team's and QA's at merge),
  the full test command when the project has one, `tests-weakened`, `size`
  (a warning) and `ready`. The foreman adds commands, or an `allow` for what
  the task asks.
- The foreman records `gate.py hash <gate.json>` in the ledger and passes it
  to every gate run of its own with `--sha`; a changed gate file blocks as
  `gate-file`.
- The lead runs `gate.py run --before-ready` in finalize before it marks the
  pull request ready; that skips `ready` and every check marked `at: merge`.
  The foreman runs the same on the lead's report, and every check before it
  merges. Exit 6 lists what blocks.
- Known limit: the lead can write in its own task folder, so no script stops
  it from writing a fake answer file into `reviews/`.

## 9. Reporting

- **Status file**: `status.jsonl` in the task folder, on the task's machine
  (`status.py path`). `launch.py --task-dir` hands the folder to an agent as
  `AF_TASK_DIR` and the file as `AF_STATUS_FILE`; without `--task-dir` or
  `--status` both are cleared, so an agent never writes into its starter's
  file.
  - The bundle's hooks (claude: `PostToolUse` and `Stop`) run
    `heartbeat.py`: a `heartbeat` line at most once a minute while tools run,
    and a `turn-end` line at every turn's end (time, agent, tool). Role agents
    start with the task folder too, so a long review shows as heartbeats.
    Checked 2026-11-13: plugin hooks fire in `claude -p`,
    `${CLAUDE_PLUGIN_ROOT}` resolves, and the variable reaches the hook.
  - The lead writes a `start` line and an `end` line with its outcome for
    every step (`status.py note`, section 6), `progress` lines during a long
    one, and a `stop` line at a decision or when blocked. The foreman writes
    the verification session's lines with `--file`.
- **The foreman** runs `status.py read` on every check (one SSH call per
  machine). No line for `ops.stall_minutes` (30) is a stall, unless the task
  is stopped: its last stage line is a `stop` line or an `end` line that
  leads to `stop`.
- **`REPORT:`** at the end of a turn only at stop points: ready, a decision
  for the person, blocked.
- **Prompt-mode runs** of a role leave three files in `reviews/`:
  `<agent>-<n>.prompt.md` (from `loop.py prompt`), `<agent>-<n>.json` (the
  JSON result: `result`, `session_id`, `total_cost_usd`,
  `permission_denials`) and `<agent>-<n>.meta.json` (role, agent, profile,
  model, the commit it ran at, verdict, start and end).

## 10. Isolation and trust

- Every agent that touches files works in its own clone (`clone.py make`):
  `~/.cache/agent-foreman/work/<project>/<task>/<agent>`. It starts inside
  that clone, never in a shared checkout, so `launch.worktree` is off.
  - The lead's clone comes from the project's checkout on that machine. The
    pair's, the red team's, QA's and the lead's scenario clone come from the
    lead's clone at its head, with `--fresh --no-push`. Either way `origin`
    is then set to the source's GitHub URL and fetched: without it `gh` fails
    ("none of the git remotes … point to a known GitHub host", checked
    2026-11-13).
  - A clone starts detached at the task's base or the head SHA, with no
    local branch, and holds a marker in `.git` that the foreman made it.
  - A judging agent's clone gets `--no-push`: origin's push URL points
    nowhere, so `gh` still works and `git push` to origin fails.
- `launch.py --role` runs only with `--task-dir`, `--name`, an `--out` inside
  the task folder's `reviews/`, and a git checkout to run in; the commit
  checked out goes into the meta file the gate reads.
- A new clone is an untrusted folder, and a trusted parent does not count
  (checked 2026-11-13: `/` was trusted, a folder under it still asked).
  - Prompt mode needs no trust step and still loads the clone's project
    skills (checked 2026-11-13).
  - In a pane, Claude Code asks first, with the cursor on "No, exit"; herdr
    shows the agent `unknown` or `blocked`, so the foreman reads the pane. When `clone.py check` says the folder is a
    clone the foreman made, the foreman (or the lead, for its own panes)
    answers Yes with herdr keys: `Down`, `Enter`. Any other folder's trust
    question goes to the person. (The person allowed this on 2026-11-13.)
- Cleanup (`clone.py remove`) removes the task's clones and task folder.
  It refuses a folder without the marker, one holding the caller's working
  directory, and, unless forced, a clone with changes to tracked files or,
  for a clone that can push, commits that are on no remote.

## 11. Records

- **Task folder**, on the task's machine:
  `~/.local/state/agent-foreman/tasks/<owner>-<repo>/<task>/` (`status.py
  dir`). Every record of the task is there; nothing goes in issue or pull
  request comments except the pull request body.

  | File | Written by | Holds |
  | --- | --- | --- |
  | `task.md` | foreman | The goal, the done-when, what is out of scope |
  | `brief.md` | foreman | What the lead reads first |
  | `loop.json` | foreman | The task's loop (section 6) |
  | `gate.json` | foreman | The task's gate (section 8) |
  | `plan.md` | lead | The work breakdown, the decisions, the checks |
  | `scenario.md` | lead | The user scenario: steps, Agent blocks, a closing verdict |
  | `handoff.md` | lead | The pull request body |
  | `status.jsonl` | lead, foreman, hooks | Section 9 |
  | `reviews/` | `launch.py`, foreman | Each role run's prompt, answer and meta; the foreman's `findings-r<round>.md` |

- After the merge, `clone.py archive` copies the task folder to the
  foreman's project folder (`projects/<owner>-<repo>/tasks/<task>`) and checks
  that every file arrived; `clone.py remove` then removes it with the clones.
- **Log**: `~/.local/state/agent-foreman/projects/<owner>-<repo>/log.jsonl`,
  append only (`log.py add`, `log.py tail`): every event, instruction sent,
  report received, decision of the person, sub-agent run, difficulty and
  outcome. No secret values.
- **Ledger**: `ledger.md` in the same folder: state and links only, one row
  per task with its gate hash. A new foreman reads it to take over;
  decisions, findings and briefs live in the task folder.
- **The foreman's place**: `~/.local/state/agent-foreman/foreman/<owner>-<repo>.json`,
  the project's last foreman session (id, transcript, folder, time). The
  plugin's `Stop` hook writes it at each turn's end; its `SessionStart` hook,
  in a new foreman session, adds that session's last exchanges, at most 9,000
  characters (`scripts/session.py`). Only in a session started with
  `claude --agent agent-foreman`, whose hooks see `agent_type`
  `agent-foreman:agent-foreman`.

## 12. Layout

One plugin that is one skill: `SKILL.md` sits at the plugin root, so the
same folder installs as a plugin (with the `agent-foreman` agent) or links
into `~/.claude/skills/agent-foreman` as a user skill.

| Path | Holds |
| --- | --- |
| `SKILL.md` | The foreman, and the entry to setup |
| `setup/` | Setup: `setup.md` runs the parts in order; `models.md`, `project.md`, `loop.md`, `other.md` |
| `loop.md` | The lead's guide to its loop; every bundle carries it |
| `kit/skills/` | The default skills, one per loop action; every bundle carries them as `foreman-kit:<name>` |
| `scripts/`, `terminals/`, `adapters/`, `defaults.json` | The scripts, the terminal layer, the agent kinds, the standard settings |
| `providers.json.sample` | The standard models by provider; setup copies it to `~/.config/agent-foreman/providers.json` for the person to edit |
| `agents/agent-foreman.md` | `claude --agent agent-foreman`; only with the plugin installed |
| `hooks/hooks.json` | The foreman's place across sessions (section 11); only with the plugin installed |
