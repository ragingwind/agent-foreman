# herdr-foreman architecture

This is the design the code follows. Where the code and this page differ, the
page is the target and the code is behind it.

## 1. Who does what

| Agent | Role | Started by | Runs as |
| --- | --- | --- | --- |
| Foreman | The project's manager: registers issues, judges each task's difficulty, writes briefs and gate files, watches, evaluates and instructs, merges, cleans up, talks with the person | The person | The person's harness session (Claude Code) |
| Lead | Owns one task: does the main work, starts and steers the task's sub-agents, runs the gate, reports | Foreman | The first pane of the task's tab |
| Sub-agent | One role for one round: code reviewer, retracer, tester, scenario agent, helper, audit roles | Lead (helpers and audit leads: Foreman) | A new pane in the task's tab, or a prompt-mode run (`claude -p`) |
| Person | Decisions that need approval, merges that need approval, blocked removals, permission prompts | — | — |

The foreman manages leads, not sub-agents. A lead never needs the foreman to
move a task from one stage to the next; the foreman steps in at stop points,
on a missed report, and on events the lead cannot handle.

Every agent gets its own profile, so one task can mix gateways: a lead on a
token-factory model and a reviewer on Anthropic opus are two processes with
two environments (`launch.py` clears the gateway variables before it sets a
profile's).

## 2. Layers

```
foreman (loop control)
--------------------------------------------------------------
terminal layer: herdr | prompt mode   (later: tmux, ghostty)
--------------------------------------------------------------
tab = one task's session          ||  tab 2  ||  ...
pane 1: lead | pane 2: reviewer   ||  ...    ||
prompt runs: retracer, tester     ||         ||
--------------------------------------------------------------
agent adapter: claude             (later: other kinds)
```

**Terminal layer.** One interface, several adapters. herdr and prompt mode
are first-class; tmux and ghostty come later behind the same interface.

| Operation | herdr | Prompt mode |
| --- | --- | --- |
| machines | saved herdr machines (SSH targets) | SSH targets |
| open a session | tab in the project's workspace | a run directory |
| start an agent | `pane run` of `launch.py` | `launch.py --print`, on another machine through `remote.py` (its login shell), output to a JSON file |
| send | `agent prompt`, `send-text`, `send-keys` | not possible: one prompt per run |
| read | `pane read`, transcript | the JSON result, transcript |
| wait | `agent wait` | the process exits |
| close | exit, `tab close` | nothing to close |

**Agent adapter.** What differs per agent kind (command, skill delivery,
transcript, checkout readiness, screen rules). Only `claude` exists.

## 3. Settings

| Scope | What | File | Written by |
| --- | --- | --- | --- |
| Global | Model pool: gateways (token variable names only) and tiers | `~/.config/herdr-foreman/config.json` | `setup-models` |
| Global | Standard loop: stages and steps, skills per step, variants per difficulty | same file | `setup-loop` |
| Project | Machines (SSH devices) and the project path on each; loop changes for this project | `~/.local/state/herdr-foreman/projects/<owner>-<repo>/project.json` | `setup` |
| Project | Memory: values only this project has (tag format, docs steps, disk floor, labels) | `.../projects/<owner>-<repo>/memory.md` | the foreman |

A level stores only what differs from the level below. The package ships the
standard values.

## 4. Models

- **Tiers.** `high`, `mid`, `low` (상·중·하). Each tier is an ordered list of
  profiles.
- **Standard tiers** are the harness's own models: for Claude Code, high =
  `opus`, mid = `sonnet`, low = `haiku`. `fable` is never in a standard tier.
- **Other models** (`fable`, token-factory models, any other gateway) enter a
  tier only when the person puts them there with `setup-models`.
- **Picking.** The task's difficulty gives the lead's tier. Reviewers and the
  retracer take one tier higher, capped at high. Within a tier, the first
  profile is used; on a usage limit or a gateway error the next one is.
- **No settings** means the standard tiers above: the harness's own models.

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

A loop is a list of steps grouped into stages. Each step has an actor, the
skills and tools it uses, and where each outcome goes; the rules per
difficulty (run, count, extra) are on the steps. A stage is a run of steps;
tab labels, status lines and reports follow the stages. `setup-loop` designs
both and maps the tools; each project can change them.

**Work loop: one issue, one pull request** (standard)

| Stage | # | Step | Actor | Does | Next |
| --- | --- | --- | --- | --- | --- |
| `plan` | 1 | `start` | Lead | Labels, branch, handoff comment with the completion criteria restated; unless the change is trivial, the scenario drafted as the target | 2 |
| `build` | 2 | `implement` | Lead | The failing check first, then the change; in a fix round, the findings | 3 |
| | 3 | `test` | Lead | New tests fail without the change and pass with it; related tests | 4 |
| | 4 | `refactor` | Lead | Restructure this round's diff without changing behavior | 5 |
| `verify` | 5 | `regression` | Lead | Rebase onto the current base (preparation), then the full suite on the result | 6 |
| | 6 | `scenario` | Lead | The manual scenario end to end through the surface the change reaches (API, CLI, UI, job), with raw output and screens for a UI; every change that is not trivial | 7 |
| `review` | 7 | `pull-request` | Lead | Draft pull request: purpose, decisions with the alternatives ruled out, tests | 8 |
| | 8 | `code-review` | Code reviewer | Verdict on the diff, the test changes first, the rules, CI, the scenario or its skip reason | changes → 2 (build), approved → 9 |
| | 9 | `scenario-retrace` | Retracer | Without the diff: the issue's criteria against the scenario, then the scenario in a fresh clone | code → 2 (build), scenario → 6 (verify), pass → 10 |
| `handoff` | 10 | `ready` | Lead | Run the gate, `gh pr ready`, handoff comment, report | stop |

A stage whose steps all do not run for a task is skipped. The management and
epic loops have no stages: each of their steps is its own.

A **scenario** drives the change end to end through whatever surface it
reaches, as a user or caller would: an API, a CLI, a UI, a job. Only a
trivial change skips it (docs or text only, a typo, a rename that changes no
behavior), with a one-line reason under `## Tests`; the foreman marks a task
trivial in its brief.

Verdict comments have fixed titles with the SHA they judged:
`## Code review of #<PR> at <sha>` and `## Scenario retrace of #<PR> at <sha>`.

**Variants by difficulty** (standard; `setup-loop` changes them)

| Difficulty | Lead tier | Review | Scenario and retrace | Extra | Merge |
| --- | --- | --- | --- | --- | --- |
| low | low | one reviewer | scenario unless trivial; no retrace | — | foreman |
| mid | mid | one reviewer | both unless trivial | — | foreman |
| high | high | two reviewers on different models | both unless trivial | main-only checks at the `regression` step when the change reaches them | the person |

- Reviewers on different models: the second takes the next profile of the
  tier, or of a lower tier, so their blind spots differ (Addy Osmani, "Agentic
  Code Review": of 617 flagged locations, 93.4% were caught by exactly one of
  four tools).
- Reviewers and retracers start without edit tools (`--disallow
  Edit,Write,NotebookEdit`). That narrows them; it is not a sandbox. Their own
  clone, whose remote is the lead's clone, and the gate's check that each
  verdict is at the head SHA, keep their writes from reaching the pull
  request. A role agent never starts other agents.
- How many rounds a loop may take is the foreman's call, from the round
  count in the status file.

**Management loop** (foreman): register issues at the smallest unit → brief
(the removal rule first) → start → watch → coordinate (same-file tasks in
sequence; relay the person's words as said) → merge gate → merge (high
difficulty: the person) → clean up → project steps from memory (tag, docs).
A review finding that recurs goes into the project's memory, with a proposed
rule, test or hook. Each report sorts the open pull requests for the person:
safe to merge, needs a real review, hold, close.

**Epic batch loop** (optional, for projects that use epics): sync the epic
onto main, then tell every branch cut from the epic to rebase → persona audit
→ fixes through the work loop → user scenarios → epic-to-main pull request →
the person approves.

## 7. Skills

A step names its skills. For each, the lead's machine is checked:

1. A project skill (`<clone>/.claude/skills/<name>`) is used first.
2. Otherwise a user skill from the person's machine. When the agent's machine
   lacks it, the foreman warns and offers to install it with the bundle
   (cached by content hash on that machine).

## 8. Gates

Pass conditions are code, not prose (`scripts/gate.py`).

- **Checks**, each reading git and GitHub: `pr-open`, `sections` (`## Purpose`,
  `## Decisions`, `## Tests`), `ci` (every check finished and passed),
  `base-fresh` (the head contains the base's head), `verdict` (enough comments
  under a role's fixed title at the head SHA, or at an earlier SHA whose
  change is the same after a clean rebase, by `git patch-id`), `scenario` (the
  `## Manual scenario` comment with raw output, or a skip reason under
  `## Tests` for a trivial change), `tests-weakened` (a removed test file, an
  added skip or focus marker, an edited CI file, a changed coverage
  threshold), `size`, `ready`, and `command` (a command that must pass, such as
  a main-only check). A check can be a warning instead of a block.
- `gate.py template` writes a task's gate file from its loop: one verdict
  check per judging step that runs, with that step's count. The foreman
  adds commands or allowances (`tests-weakened` may allow what the issue asks
  for) and puts the file in the brief.
- The lead runs `gate.py run <file> --cwd <clone> --before-ready` before it
  marks the pull request ready, and posts the result. The foreman runs the
  same gate, `ready` included, before it merges. Exit 6 lists what blocks.

## 9. Reporting

- **Status file**, on the agent's machine:
  `~/.cache/herdr-foreman/runs/<project>/<task>/status.jsonl`
  (`status.py path`). `launch.py --status` hands it to an agent as
  `HF_STATUS_FILE`; without `--status` the variable is cleared, so an agent
  never writes into its starter's file.
  - The bundle's hooks (claude: `PostToolUse` and `Stop`) run
    `heartbeat.py`: a `heartbeat` line at most once a minute while tools run,
    and a `turn-end` line at every turn's end (time, agent, tool). The lead
    starts its role agents with its own status file, so a long review shows
    as heartbeats too. Checked 2026-11-13: plugin hooks fire in `claude -p`,
    `${CLAUDE_PLUGIN_ROOT}` resolves, and the variable reaches the hook.
  - The lead appends a stage line (`status.py note`) at the start and end of
    every stage, at least every `ops.report_minutes` (15) during a long
    one, and a `stop` line at a stop point: what was done, what is next,
    what blocks it, each sub-agent run with its verdict and cost.
- **The foreman** runs `status.py read` on every check (one SSH call per
  machine). No line for `ops.stall_minutes` (30) is a stall, unless the last
  stage line is a `stop`.
- **`REPORT:`** at the end of a turn only at stop points: ready, a decision
  for the person, blocked.
- **Prompt-mode runs** leave their JSON result (`result`, `session_id`,
  `total_cost_usd`, `permission_denials`) in the task's run directory.

## 10. Isolation and trust

- Every agent that touches files works in its own clone:
  `~/.cache/herdr-foreman/work/<project>/<task>/<agent>`. It starts inside
  that clone, never in a shared checkout.
- A new clone is an untrusted folder. Prompt mode needs no trust step there
  and still loads the clone's project skills (checked 2026-11-13). When Claude
  Code shows the trust question in a pane whose folder is a clone the foreman
  made under that work root, the foreman answers "Yes, I trust this folder" with herdr keys. Any
  other folder's trust question goes to the person. (The person allowed this
  on 2026-11-13.)
- Cleanup removes the task's clones, run directory and stacks.

## 11. Records

- **Log**: `~/.local/state/herdr-foreman/projects/<owner>-<repo>/log.jsonl`,
  append only (`log.py add`, `log.py tail`): every event, instruction sent,
  report received, decision of the person, sub-agent run, difficulty and
  outcome. No secret values.
- **Ledger**: `ledger.md` in the same folder, the summary a new foreman reads
  to take over.

## 12. Skills of this plugin

| Skill | Does |
| --- | --- |
| `herdr-foreman` | The foreman |
| `setup-models` | Gateways, models and tiers |
| `setup-loop` | Stages and their steps, skills and tools per step, variants per difficulty |
| `setup` | A project: machines and paths, checked |
