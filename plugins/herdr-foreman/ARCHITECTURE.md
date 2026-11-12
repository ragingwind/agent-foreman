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
| Global | Standard loop: stages, skills per stage, variants per difficulty | same file | `setup-loop` |
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
- **Difficulty**: low = level 0, mid = level 1, high = level 2-3. Level 3
  also needs the person's approval before merge.
- `score.py` computes L and the path part of I from the issue and, later, the
  diff. The foreman adds what code cannot see (is it user-visible?) and
  decides. After the diff exists the score is taken again and the difficulty
  only ever goes up.

Sources: Kamei et al. 2013 (just-in-time defect prediction), Meta Diff Risk
Score, ISTQB risk-based testing, Rigby & Bird 2013 (two reviewers), Google
small-CL guidance. The thresholds are a starting point; the log keeps each
task's level and outcome (reverts, follow-up fixes) to tune them.

## 6. Loops

A loop is a list of stages. Each stage is an event with an actor, the skills
and tools it uses, the gate checks that close it, and where each outcome goes.
`setup-loop` designs the stages and maps the tools; each project can change
them.

**Work loop: one issue, one pull request** (standard)

| # | Stage | Actor | Does | Next | Skills and tools |
| --- | --- | --- | --- | --- | --- |
| 1 | Start | Lead | Labels, branch, handoff comment | 2 | project branch and label skills |
| 2 | Implement | Lead | Code and new tests; in a fix round, the findings | 3 | `CLAUDE.md`, rules |
| 3 | Test 1 | Lead | New tests fail before the change and pass after; related tests | 4 | project test command |
| 4 | Clean | Lead | Clean this round's diff | 5 | a clean-code skill |
| 5 | Test 2 | Lead | Refresh the base, full tests, manual scenario and screens; in a fix round only what the fix touches | 6 | scenario skill |
| 6 | PR | Lead | Draft pull request; push in fix rounds; post and update the scenario comment | 7 | commit and PR skills |
| 7 | Code review | Code reviewer | Verdict on the diff (since the last review in a fix round), rules, breaking it, CI, the scenario or its skip reason | changes → 2, approved → 8 | fixed reviewer prompt |
| 8 | Scenario retrace | Retracer | Without the diff: the issue's criteria against the scenario, then the scenario in a fresh clone | code → 2, scenario or missing criterion → 5, pass → 9 | fixed retrace prompt, scenario skill |
| 9 | Ready and report | Lead | Run the gate, `gh pr ready`, handoff comment, report | stop | gate |

Verdict comments have fixed titles with the SHA they judged:
`## Code review of #<PR> at <sha>` and `## Scenario retrace of #<PR> at <sha>`.

**Variants by difficulty** (standard; `setup-loop` changes them)

| Difficulty | Lead tier | Review | Retrace | Extra |
| --- | --- | --- | --- | --- |
| low | low | one reviewer | skipped | — |
| mid | mid | one reviewer | when the change is user-visible | — |
| high | high | two reviewers | yes | main-only checks run at the PR stage when the change reaches them; level 3 needs the person's approval |

How many rounds a loop may take is the foreman's call, from the round count
in the status file.

**Management loop** (foreman): register issues at the smallest unit → brief
(the removal rule first) → start → watch → coordinate (same-file tasks in
sequence; relay the person's words as said) → merge gate → merge → clean up →
project steps from memory (tag, docs).

**Epic batch loop** (optional, for projects that use epics): sync the epic
onto main, then tell every branch cut from the epic to rebase → persona audit
→ fixes through the work loop → user scenarios → epic-to-main pull request →
the person approves.

## 7. Skills

A stage names its skills. For each, the lead's machine is checked:

1. A project skill (`<clone>/.claude/skills/<name>`) is used first.
2. Otherwise a user skill from the person's machine. When the agent's machine
   lacks it, the foreman warns and offers to install it with the bundle
   (cached by content hash on that machine).

## 8. Gates

Pass conditions are code, not prose.

- `gate.py` holds tested checks that read git and GitHub: pull request
  exists and is ready, CI green, each verdict present at the head SHA, a
  scenario comment with raw output or a one-line skip reason, `## Tests`,
  base freshness, `git range-diff` unchanged after a rebase, labels, size
  limits, forbidden paths, commands that must pass.
- For each task the foreman writes `gate.json`: which checks, with what
  values. A one-off script is allowed when no check fits.
- The lead runs `gate.py gate.json` before it reports ready, and posts the
  result to the status file and the pull request. The foreman runs the same
  gate again before it merges.

## 9. Reporting

- **Status file**, on the agent's machine:
  `~/.cache/herdr-foreman/runs/<project>/<task>/status.jsonl`.
  - A hook in the bundle appends a heartbeat on every tool call and every
    turn end (time, tool, stage).
  - The lead appends a line at the start and end of every stage: what was
    done, what is next, what blocks it, each sub-agent run with its verdict
    and cost.
- **The foreman** reads the last lines on every check (one SSH call per
  machine). No new line for 30 minutes (twice the 15-minute interval) is a
  stall.
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
  append only: every event, instruction sent, report received, decision of
  the person, sub-agent run, difficulty and outcome. No secret values.
- **Ledger**: `ledger.md` in the same folder, the summary a new foreman reads
  to take over.

## 12. Skills of this plugin

| Skill | Does |
| --- | --- |
| `herdr-foreman` | The foreman |
| `setup-models` | Gateways, models and tiers |
| `setup-loop` | Stages, skills and tools per stage, variants per difficulty |
| `setup` | A project: machines and paths, checked |
