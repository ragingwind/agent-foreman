# agent-foreman

Turn one Claude Code session into the foreman of your coding agents. You
name the work, for example "run issues #12 and #15 of acme/api". The foreman
then:

- rates how risky each task is;
- hands each task to a lead agent working in its own clone on one of your
  [herdr](https://herdr.dev) machines;
- checks the result with a script before anything merges;
- merges it, or leaves the merge to you when the risk is high.

The foreman writes no code and does not review code itself.

## Contents

- [Words](#words)
- [Features and why](#features-and-why)
- [Requirements](#requirements)
- [Setup](#setup)
- [Scenarios](#scenarios)
- [Stop, change or take over](#stop-change-or-take-over)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

## Words

| Word | Meaning |
| --- | --- |
| Foreman | This Claude Code session. It plans, starts, watches and merges; you talk only to it |
| Lead | The agent that does one task, from the first commit to a ready pull request |
| Reviewer, retracer | Agents a lead starts to judge its work. A reviewer reads the diff. A retracer reads only the issue and reruns the scenario |
| Difficulty | The task's risk rating: low, mid or high (likelihood of a defect × its impact). It decides how much review a task gets and who merges |
| Trivial | A task that is docs or text only, a typo, or a rename with no behavior change. The foreman decides; a trivial task skips the scenario |
| Scenario | The change run end to end through what it touches (an API call, a CLI command, a UI flow, a job), as a user would. An agent runs it, not the test suite |
| Gateway | Where a model is served: Anthropic, or an Anthropic-compatible service such as a token factory (a model service your company runs) |
| Profile | A gateway and a model, by name (`opus`, `tf-coder`) |
| Tier | An ordered list of profiles for one difficulty; the first is used, the next one on a usage limit |
| Stage, step | The lead's work loop: five stages (plan, build, verify, review, handoff), each a few steps |
| Gate | A file of checks a pull request must pass before it is ready and again before it merges |
| Prompt mode | An agent that answers one prompt and exits (`claude -p`), with no tab to watch |

## Features and why

| Feature | What it does | Why |
| --- | --- | --- |
| Delegation to a lead | Per task, the foreman writes a brief; the lead does the work and starts its own reviewers | The foreman stays free to manage many tasks, and no step waits on a round trip through it |
| Difficulty | `score.py` rates the issue, and later the diff: size, how many files and folders, past fixes there, critical and public paths. The foreman may raise the rating, never lower it | Review effort goes where defects are likely and costly; a high-risk change is merged by you |
| Model tiers and gateways | Each difficulty picks a tier; a tier's profiles can be on any gateway; on a usage limit the next profile takes over | Cheaper models for easy tasks, the strongest for risky ones; one task can mix gateways |
| Reviewers on other models | Reviewers and retracers run one tier above the lead (at most high); with two reviewers, each on a different model. They have no edit tools and their clone cannot push | In one comparison of four review tools, 93.4% of 617 flagged spots were caught by only one tool (Addy Osmani, "Agentic Code Review"). And a judge must not change what it judges |
| Scenario | Every task that is not trivial runs its scenario before review; a retracer reruns it from the issue alone | Passing tests do not show the change works for the person who uses it |
| Gate in code | `gate.py` checks the pull request: the body's Purpose, Decisions and Tests sections; CI; the branch is on the latest base; each verdict is at the current commit; the scenario; no test deleted, skipped or loosened; size | A task counts as done only when the checks pass, not when an agent says so |
| Loop as data | The stages, steps, skills and difficulty variants are settings; your project's own skills come first | You can rename a stage, add a step or map your skills without changing code |
| Own clone per agent | Each agent starts in a fresh clone of your checkout, pointed at GitHub; the foreman answers Claude Code's folder trust question only for a clone it made | Agents never share files with each other or with your checkout |
| Status files | Hooks write a heartbeat; the lead writes a line per stage; `status.py read` gets every task and the free disk in one SSH call per machine | You see each agent's stage and that it is alive without reading screens; an agent that goes quiet shows as stalled |
| Many machines | Agents run in herdr tabs on any saved herdr machine; skills travel as a bundle, copied once per content | Spread work over machines; every agent gets the same skills |
| Ledger, log and memory | Per project: the live state, every event, and what only this project has (its merge method, recurring review findings) | A new foreman session can take over; a finding that keeps coming back becomes a rule or a test |
| Risk-sorted report | Open pull requests sorted into: safe to merge, needs a real review, hold or changes requested, close; one line of reason each | You see what to do first without opening each pull request |

## Requirements

| Need | Why |
| --- | --- |
| herdr on this machine and on every machine that runs agents, each remote saved with `herdr machine add` (tested with 0.9.5) | The foreman drives tabs and agents through `herdr --machine` |
| Claude Code, signed in, on every machine that runs agents (tested with 2.1.322) | The agents are Claude Code sessions |
| `claude`, `git`, `gh` (signed in) and `python3` on `PATH` in each machine's login shell | Agents start there and post to GitHub; the scripts need only Python's standard library |
| SSH from this machine to each remote with no password prompt | Bundles, briefs and checks travel over `ssh` and `scp` |
| A checkout of the repository on each machine | Agent clones are made from it |
| `gh`, signed in, on this machine | Issues, pull requests and merges |

This machine can run agents too: add it as `local` in the project's
machines. The foreman checks every 10 minutes only while its session is
open; run it in a herdr pane (that is how it was tested).

## Setup

With the requirements met:

1. **Install the plugin** (in Claude Code):

   ```
   /plugin marketplace add ragingwind/herdr-skills
   /plugin install agent-foreman@herdr-skills
   ```

   Or use it as a plain skill: clone this repository and link the plugin
   folder, which is also the skill folder. You then start with the skill
   (`/agent-foreman`) instead of `claude --agent agent-foreman`.

   ```bash
   ln -s "$PWD/herdr-skills/plugins/agent-foreman" ~/.claude/skills/agent-foreman
   ```

2. **Set up.** In a checkout of the repository, run
   `/agent-foreman:agent-foreman setup`. It first asks which parts to set up
   (or goes straight to the one you name, as in `/agent-foreman:agent-foreman setup
   models` or `/agent-foreman:agent-foreman setup add machine build-02`):
   - **Project** (needed once per repository): it finds the repository and
     your herdr machines, then asks which repository and which machines, and
     a path for any machine it cannot guess. It checks each machine (the
     checkout and its origin; `claude`, `git`, `gh` and `python3`; the token
     variables your models need, by name only) and saves
     `~/.local/state/agent-foreman/projects/<owner>-<repo>/project.json`.
   - **Models** (optional): add a gateway such as a token factory, or change
     which models each difficulty uses (scenario 3). Without it: Anthropic's
     `haiku`, `sonnet` and `opus` for low, mid and high. Chosen together with
     Project, it goes first, so the machine check covers the new token
     variable.
   - **Loop** (optional): rename stages, map your skills to steps, or change
     what each difficulty runs. Without it: the standard loop below.
   - **Other settings** (optional): launch, tab labels, the report, check
     and stall times, disk floor, difficulty thresholds.

3. **Start the foreman:**

   ```bash
   claude --agent agent-foreman
   ```

   Then name the work: `Run issues #12 and #15 of acme/api.`

Agents start with `--dangerously-skip-permissions`, so they do not stop for
permission prompts. To have them ask, set `launch.permission` to `default`
in setup (Other settings). You then answer each prompt in that agent's
herdr tab; the foreman tells you where, and never answers one.

## Scenarios

### 1. Hand over two issues and get them merged

You: `Run issues #12 and #15 of acme/api.`

1. The foreman rates each issue. #12 changes a help text: **low**. #15
   changes token refresh under `auth/`: **high**.
2. For each, it writes a brief and a gate file, makes a clone on the least
   busy machine, opens a tab there and starts a lead on that difficulty's
   tier.
3. Each lead works through the stages; the tab label follows them
   (`15 build`, then `15 review 1`).
4. At **review** the lead opens a draft pull request and starts the
   reviewers: one for #12; two for #15, on different models. Each posts a
   comment titled `## Code review of #<PR> at <commit>` with a `Verdict:`
   line. For #15 a retracer also reruns the scenario from the issue alone.
5. At **handoff** the lead runs the gate, marks the pull request ready and
   reports ready.
6. The foreman runs the gate again. It merges #12 itself. For #15 it tells
   you the pull request is ready, with the gate result, and waits.
7. After each merge it removes the agents, clones, tab and run files.

What you do: when a lead needs a decision (a change to an interface, a
schema or what users see, that the issue does not settle), the foreman asks
you in its session; your answer goes to the lead in your words. Then merge
#15.

### 2. Ask what is waiting on you

You: `What is waiting on me?`

The foreman reads the live state and answers in the report format
(shortened):

```
## Status 14:05 UTC · acme/api
build-01: 2 working, 0 blocked · 41 GB free
| Tab | Issue / PR | Stage | Waiting on | Note |
| --- | --- | --- | --- | --- |
| build-01:t3 | #15 / #88 | handoff | owner merge | high, 2 approvals |
| build-01:t4 | #21 / #90 | review | reviewer | round 2 |
**Pull requests for you** (risk-sorted; high-difficulty merges are yours):
- Needs a real review: #88 — token refresh, high difficulty
**For you**: merge #88; #21 asks whether to keep the old flag (see #90)
```

"owner merge" means the pull request waits for you to merge it.

### 3. A token-factory model builds, Anthropic opus reviews

1. Run `/agent-foreman:agent-foreman setup models` and add a gateway: a name (`tf`), its
   base URL, `bearer` auth, and the **name** of the variable that holds its
   token (`TF_TOKEN`). Add its model and a profile for it (`tf-coder`).
2. Put `tf-coder` first in the low and mid tiers. Leave high on `opus`.
3. Set `TF_TOKEN` in each machine's shell profile. Setup and the foreman
   check that it is set and never read its value.

A mid task now runs its lead on `tf-coder`. Its reviewers take the tier
above, high, and run on Anthropic `opus`. When `tf-coder` hits a usage
limit, the tier's next profile (`sonnet` in the mid tier) takes over.

## Stop, change or take over

- **Stop a task**: `Stop #15.` The foreman exits its agents, closes the tab
  and removes the clones. If a clone holds work that is on no remote, it
  stops and asks you. The issue and pull request stay as they are.
- **Merge everything yourself**: tell the foreman; it keeps that in the
  project's memory and stops merging low and mid tasks.
- **Change a setting**: `/agent-foreman:agent-foreman setup`, naming what to change, or ask the
  foreman.
- **Take over**: a new `claude --agent agent-foreman` session reads the
  project's ledger and picks up where the last one stopped.

## How it works

```
you ── foreman (this session) ── per task: brief + gate
                                  │
              herdr tab on a machine, own clone
                                  │
                 lead ── reviewers, retracer (prompt mode)
                  │
       status file ◄── hooks          GitHub: pull request, verdicts
```

The work loop (standard):

| Stage | Steps | Low | Mid | High |
| --- | --- | --- | --- | --- |
| plan | start: branch, restated criteria, scenario drafted | ✓ | ✓ | ✓ |
| build | implement, test, refactor | ✓ | ✓ | ✓ |
| verify | regression (rebase, full suite), scenario | ✓; scenario unless trivial | ✓; scenario unless trivial | ✓; scenario unless trivial; plus checks that normally run only on the main branch |
| review | pull-request, code-review, scenario-retrace | 1 reviewer, no retrace | 1 reviewer, retrace | 2 reviewers on different models, retrace |
| handoff | ready: gate, mark ready, report | foreman merges | foreman merges | you merge |
| **Agent sessions per round, at most** | | lead + 1 | lead + 2 | lead + 3 |

A review asking for changes goes back to build; a retrace that finds the
scenario wrong goes back to verify. Each reviewer and retracer gets its own
clone for the round, removed after it. Reviewers and retracers run in prompt
mode; a role set to `pane` mode runs in a pane beside the lead instead. The
full design is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Configuration

Settings have three levels: the standard (`defaults.json` in the plugin),
yours (`~/.config/agent-foreman/config.json`), and the project's. Each level
stores only what differs from the one below.

| Section | Standard | Change it with |
| --- | --- | --- |
| `gateways`, `profiles`, `tiers` | Anthropic; low `haiku`, mid `sonnet`, high `opus` | setup: Models |
| `loop` | the work loop above | setup: Loop |
| project | repository, machines and paths | setup: Project |
| `difficulty` | thresholds: 400 changed lines, 10 files, 3 top folders, 90 days of fix history; path patterns for critical code (auth, payments, migrations, CI, deploy, …) and public interfaces (API, CLI, SDK, …) | setup: Other |
| `launch` | permission `bypass`, no worktree; profile `sonnet` only when no profile is named (the foreman always names one from the tier) | setup: Other |
| `labels`, `report` | tab label `{task} {stage}`; the report above | setup: Other |
| `ops` | check every 10 minutes; a stage line at least every 15 minutes; stalled after 30; disk floor 20 GB; the after-merge steps | setup: Other |

Each project's files are in `~/.local/state/agent-foreman/projects/<owner>-<repo>/`:
`project.json` (its settings), `ledger.md` (live state), `log.jsonl` (every
event) and `memory.md` (its merge method, tag format, recurring findings).
Ask the foreman to show the settings in effect.

## Security

- **Commands**: `herdr` (local and `--machine`), `ssh` and `scp` to your saved
  herdr machines, `gh`, `git`, `claude`, `python3`.
- **On each machine** it writes under `~/.cache/agent-foreman/`: `bundles/`
  (the skills your loop names and the scripts, with a hook that writes
  heartbeats to the task's status file), `briefs/`, `work/` (agent clones)
  and `runs/` (status files and results). It never writes into your
  checkout.
- **Permissions**: see Setup. The foreman never answers a permission prompt.
  It answers Claude Code's folder trust question only for a clone it made
  under `work/`.
- **Reviewers** run without edit tools and with a clone that cannot push to
  origin. This narrows them; it is not a sandbox.
- **Secrets**: settings, ledgers and logs hold token variable *names* only.
  A token is read from the environment of the machine that starts the agent
  and is never printed or stored.
- **Network**: your machines, GitHub through `gh` and `git`, and the model
  gateways your profiles name.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Setup reports a problem on a machine | Its message names the fix: clone the repository there, correct the path, put a tool on `PATH`, or set a token variable in the shell profile |
| `launch.py` exits with 4 | The gateway's token variable is not set on that machine |
| A trust question in a folder the foreman did not make | It is yours to answer; the foreman will not |
| `missing skill` when the bundle is built (only after setup mapped a skill to a step) | The skill's plugin directory is not in your settings; add it in setup, Loop |
| A machine is reported low on disk | Remove build directories and unused images there; the foreman places no new task on it until it is above the floor |
| `config.py check` lists problems | `/agent-foreman:agent-foreman setup`, the part the problem names |

## Updating and uninstalling

```bash
claude plugin update agent-foreman@herdr-skills
claude plugin uninstall agent-foreman@herdr-skills
```

Uninstalling leaves your settings and caches; remove them by hand:
`~/.config/agent-foreman/`, `~/.local/state/agent-foreman/`, and
`~/.cache/agent-foreman/` here and on each remote.

## Development

From the repository root:

```bash
python3 -m unittest discover -s tests
claude plugin validate --strict plugins/agent-foreman
```

## License

MIT. See [LICENSE](../../LICENSE).
