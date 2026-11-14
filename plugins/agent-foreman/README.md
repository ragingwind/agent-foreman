# agent-foreman

Turn one Claude Code session into the foreman of your coding agents on
[herdr](https://herdr.dev) machines. You name the work. For each task the
foreman:

- writes the task down in one task folder, and rates its risk;
- starts a **lead** agent that builds it in its own clone (the **build
  session**);
- starts a **red team** and **QA** on other models to check it (the
  **verification session**);
- runs a scripted gate, then merges, or leaves the merge to you when the risk
  is high.

The foreman writes no code and reviews no code itself.

## Words

| Word | Meaning |
| --- | --- |
| Foreman | This Claude Code session. You talk only to it |
| Lead | The agent that builds one task, from the plan to a ready pull request |
| Pair | Another model that reviews the lead's work inside the build session |
| Red team, QA | Agents on other models in the verification session. The red team tries to break the change; QA runs the full tests and the user scenario test |
| Task folder | One folder per task that holds every record: the task, the plan, the scenario, the handoff, every review and the status |
| Default skill | What one loop action is, shipped with agent-foreman. A project or local skill can replace how it is done |
| Difficulty | Low, mid or high. It picks the models and who merges |
| Gate | Checks in code that must pass before ready and before merge |

## How it works

```
intake (foreman)
  your request → task.md → task folder and lead
        ↓
build session (lead, in its own clone)
  plan → build → verify → review → finalize → ready
           ↻ for each work item: [implement → test → commit]
                            inside review: pair review → simplify → fix findings → pair re-check
  verify fails              → build
  review: a large fix needed → build
  finalize: rebase conflict → build
        ↓ ready (gate passed)
verification session (started by the foreman; both run together)
  redteam-review (red team) ─┐
                             ├→ both pass → merge gate → merge → archive and clean up
  test (QA) ─────────────────┘
  code finding · full tests fail · product problem in the scenario → build
  scenario script problem                                          → verify
  environment problem · over 3 rounds · anything else              → you
```

| Session | Stage | What happens | Default skills |
| --- | --- | --- | --- |
| build | plan | Split the task into work items with a done-when each; write the scenario script a person could follow | `work-breakdown`, `cross-check` |
| | build | Per work item: implement (test first if the project uses TDD), test, commit once | `tdd`, `unit`, `commit` |
| | verify | Tests near the change, a smoke test, and the scenario script run once in a fresh clone | `unit`, `smoke`, `cross-check` |
| | review | The pair reviews; the lead cleans up the diff and fixes the findings; the pair checks again | `review`, `simplify` |
| | finalize | Rebase, write handoff.md, open the pull request (its body is handoff.md), run the gate | `handoff` |
| verification | redteam-review | Try to break it: done-when, correctness, tests, structure, security | `redteam-review` |
| | test | The full tests, then the user scenario test without reading the diff | `full`, `cross-check` |

- **Other models check the work.** The pair, the red team and QA never run
  on the lead's profile. The gate refuses a verdict from the lead's model.
- **One place for records.** Everything about a task is in its task folder.
  After the merge, the foreman copies the folder to your project folder and
  removes it from the machine.
- **One rule off the path.** An agent tries once more; if it still fails, it
  stops and the foreman asks you.

## Requirements

| Need | Why |
| --- | --- |
| herdr on this machine and on every machine that runs agents, each remote saved with `herdr machine add` (tested with 0.9.5) | The foreman drives tabs and agents through `herdr --machine` |
| Claude Code, signed in, on every machine that runs agents (tested with 2.1.323) | The agents are Claude Code sessions |
| `claude`, `git`, `gh` (signed in) and `python3` on `PATH` in each machine's login shell | Agents start there and open pull requests; the scripts need only Python's standard library |
| SSH from this machine to each remote with no password prompt | Bundles and task folders travel over `ssh` and `scp` |
| A checkout of the repository on each machine | Agent clones are made from it |

## Setup

1. **Install the plugin** (in Claude Code):

   ```
   /plugin marketplace add ragingwind/herdr-skills
   /plugin install agent-foreman@herdr-skills
   ```

2. **Set up**, in a checkout of the repository:
   `/agent-foreman:agent-foreman setup`. It asks which parts to set up:
   - **Project**: the repository, the machines and their checkout paths, and
     the full test command (it proposes the one in `CLAUDE.md` or your CI
     files). Needed once per repository.
   - **Models** (optional): gateways and the profiles for each difficulty.
     Each difficulty needs a profile other than its lead's for the agents
     that check the work. Without it: `haiku`, `sonnet`, and `opus` then
     `sonnet`.
   - **Loop** (optional): replace a default skill with your own, or change
     what each difficulty runs.

3. **Start the foreman:**

   ```bash
   claude --agent agent-foreman
   ```

   Then name the work: `Add a --json flag to the list command of acme/api.`

Agents start with `--dangerously-skip-permissions`, so they do not stop for
permission prompts. To have them ask, set `launch.permission` to `default`
in setup. The foreman never answers a permission prompt.

## Security

- **On each machine** it writes under `~/.cache/agent-foreman/` (bundles and
  agent clones) and `~/.local/state/agent-foreman/tasks/` (task folders). It
  never writes into your checkout.
- **Trust**: the foreman answers Claude Code's folder trust question only for
  a clone it made.
- **Judging agents** (pair, red team, QA) run without edit tools, in clones
  that cannot push. This narrows them; it is not a sandbox.
- **Secrets**: settings and records hold token variable names only.

## Updating and uninstalling

```bash
claude plugin update agent-foreman@herdr-skills
claude plugin uninstall agent-foreman@herdr-skills
```

Uninstalling leaves your settings and records; remove them by hand:
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
