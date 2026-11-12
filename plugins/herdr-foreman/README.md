# herdr-foreman

Run one Claude Code session as the foreman of many coding agents spread over
your [herdr](https://herdr.dev) machines. The foreman starts each agent in a
herdr tab on the right machine, hands it a brief and the skills it needs,
wakes up when an agent finishes or gets stuck, and keeps a ledger and a
status report per project. It writes no code itself.

## What ships

| Part | What it does |
| --- | --- |
| `herdr-foreman` skill | The foreman: prepares a project group, places tasks on machines, launches agents, sends briefs, watches state, drives the task loop and reports |
| `herdr-foreman-setup` skill | Asks for your settings and a project group's machines, validates them and saves only what differs from the standard |
| `herdr-foreman` agent | Starts a session as the foreman: `claude --agent herdr-foreman` |
| `scripts/` | `config.py` (settings), `bundle.py` (skill bundles), `launch.py` (start an agent from a profile), `transcript.py` (read an agent's answers) |

## Requirements

| Need | Why |
| --- | --- |
| Claude Code, signed in on every machine that runs agents (tested with 2.1.322) | The agents are Claude Code sessions |
| herdr on every machine, with each remote saved by `herdr machine add` (tested with 0.9.5) | The foreman drives tabs and agents through `herdr --machine` |
| SSH from this machine to each remote without a password prompt (`ssh -o BatchMode=yes <target> true` works) | Bundles and briefs are copied with `ssh` and `scp` |
| Python 3 on every machine (tested with 3.12) | The scripts use only the standard library |
| `gh`, signed in, where the foreman runs | Issues, pull requests and labels |
| A checkout of the repository on each machine, opened once with `claude` and trusted | Worktree sessions refuse an untrusted folder |

## Install

In Claude Code:

```
/plugin marketplace add ragingwind/herdr-skills
/plugin install herdr-foreman@herdr-skills
```

From a shell:

```bash
claude plugin marketplace add ragingwind/herdr-skills
claude plugin install herdr-foreman@herdr-skills
```

To try it without installing: `claude --plugin-dir /path/to/herdr-skills/plugins/herdr-foreman`.

## First run

1. Run `/herdr-foreman-setup`. It asks for:
   - plugin directories you load with `--plugin-dir`, so their skills can be
     bundled for agents;
   - gateways and profiles (only the *name* of a token variable, never its
     value);
   - the skills each loop stage uses, labels, report and operating rules.
   Your answers go to `~/.config/herdr-foreman/config.json`.
2. Set up a project group in the same run: the repository (`owner/name`),
   each machine and its checkout path. It checks each checkout and saves
   `~/.local/state/herdr-foreman/groups/<owner>-<repo>/group.json`.
3. Start the foreman: `claude --agent herdr-foreman`, and tell it the
   repository and the work.

## Usage

```
Run issues #12, #15 and #18 of acme/api, two at a time.
What is waiting on me?
#15 is approved; merge it and clean up.
```

Run `/herdr-foreman-setup <section>` at any time to change one part, for
example `/herdr-foreman-setup plugin dirs`.

## How it works

1. **Group.** A project group is one repository and the machines it runs on.
   On each machine the foreman uses a herdr workspace named after the
   repository.
2. **Bundle.** The skills the group's agents need are packed into a small
   plugin, named by a hash of its content, and copied to each machine once.
   A change makes a new bundle; an unchanged one is reused.
3. **Agents.** For each task the foreman opens a tab on the least busy
   machine, starts Claude Code from a profile with the bundle loaded, and
   sends a brief file. The agent follows the built-in loop (implement, clean,
   test, PR, review, fix, approved) and renames its tab at each stage.
4. **Watching.** The foreman waits on herdr's agent state in the background.
   When an agent finishes or is blocked it reads the screen, or the session
   transcript when the answer is long, and acts or asks you.

## Configuration

Settings have three levels: the standard (`skills/herdr-foreman/defaults.json`),
yours, and the group's. Each level stores only what differs from the one
below; delete a key to fall back.

| Section | Standard |
| --- | --- |
| `plugin_dirs` | none |
| `gateways`, `profiles` | Anthropic; `sonnet`, `opus`, `haiku` |
| `launch` | profile `sonnet`, permission `bypass`, worktree on |
| `loop` | eight stages; tier S and M on sonnet, L on opus |
| `bundle` | no skills besides the stages' own |
| `labels` | `{task} {stage}`; own labels for blocked, exited, owner decision |
| `report` | a status table per group |
| `ops` | check every 10 minutes, least-busy placement, disk check, seven after-merge steps |

`python3 <plugin>/skills/herdr-foreman/scripts/config.py show --group owner/name`
prints the settings in effect; `check` validates them.

## Security

What the plugin runs, sends and writes:

- **Commands**: `herdr` (local and `--machine`), `ssh` and `scp` to the SSH
  targets of your saved herdr machines, `gh`, `git`, `claude`, `python3`.
- **On remote machines** it writes bundles to `~/.cache/herdr-foreman/bundles/`
  and briefs to `~/.cache/herdr-foreman/briefs/`, and starts Claude Code
  sessions in your checkouts.
- **Permissions**: agents start with `--dangerously-skip-permissions` unless
  you set `launch.permission` to `default`. The foreman never answers a
  permission prompt for you.
- **Secrets**: settings and ledgers hold token *variable names* only. A
  gateway's token is read from the environment of the machine that starts
  the agent and is never printed or stored.
- **Network**: nothing beyond your machines, GitHub through `gh`, and the
  model gateway your profiles name.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Workspace trust not yet accepted` in an agent's tab | Run `claude` once in that checkout on that machine and accept the trust question |
| `launch.py` exits with 4 | The gateway's token variable is not set on that machine |
| `skill not available on this machine` | Add the plugin directory with `/herdr-foreman-setup plugin dirs` |
| `config.py check` lists problems | Run `/herdr-foreman-setup` and fix the named section |
| A remote member does not answer | `herdr machine status`, then `ssh -o BatchMode=yes <target> true` |

## Updating and uninstalling

Update with `claude plugin update herdr-foreman@herdr-skills`. Uninstalling
the plugin leaves your settings; remove them by hand:
`~/.config/herdr-foreman/`, `~/.local/state/herdr-foreman/`,
`~/.cache/herdr-foreman/`, and `~/.cache/herdr-foreman/` on each remote.

## Development

From the repository root:

```bash
python3 -m unittest discover -s tests
claude plugin validate plugins/herdr-foreman
```

## License

MIT. See [LICENSE](../../LICENSE).
