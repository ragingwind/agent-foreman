# Setup

Read from `SKILL.md` "Setup": when the person runs
`/agent-foreman:agent-foreman setup`, asks in words to change a setting, or
when a check fails.

Settings have three levels, each laid over the one before: the standard
(`defaults.json` in the agent-foreman skill), the person's
(`~/.config/agent-foreman/config.json`) and a project's
(`~/.local/state/agent-foreman/projects/<owner>-<repo>/project.json`). A level
stores only what differs from the level below. The models are not in these
levels: they are in `~/.config/agent-foreman/providers.json`, which the
person edits (`models.md`). Everything is personal and lives outside any
repository. Never ask for, read, print or store a token value; a provider
holds only the name of the variable that carries it.

`<skill>` is the agent-foreman skill's directory, `..` from this file. Run its
scripts with `python3`.

## 1. The parts

| Part | File | What it sets |
| --- | --- | --- |
| Models | `models.md` | Providers, their models and the low, mid and high tiers, in `providers.json`, which the person edits |
| Project | `project.md` | The repository, the machines, the checkout path on each, the full test command |
| Loop | `loop.md` | The skill each step uses (the project's and the person's skills fitted to each step), stages, steps, what a difficulty runs, the project's own gate checks |
| Other | `other.md` | Launch, permissions, tab labels, the report, check and stall times, disk, merge steps, difficulty thresholds, bundled skills |

**`setup`, and a failed check, run every part**, in this order: models,
project, loop, other. Models come first so that the project's machine check
covers the new providers' token variables. Words after `setup` pick no part;
a repository they name is the project part's guess.

**A request in words to change one setting** ("add machine build-02", "put
opus first in high") goes to the part the table names for it, and only that
part.

## 2. Keep what is set

Every question about a setting that already has a value offers that value
first, as `Keep: <value>`, marked recommended. A person who wants nothing
changed answers each part with its first options. A part whose answers keep
every value saves nothing. There is one exception, in the loop part. When a
project's skill or the person's skill fits a step, recommend it over a default
skill that nobody chose for that step (`loop.md` "2. Fit each step").

## 3. Do each part

Read the part's file in this skill's directory and follow it, in the order
above.

## 4. Save

Every part saves the same way. Take the settings in effect (`config.py show`,
with `--project <repo>` for a project's level), change what the person chose,
and write the whole object to a scratch file. A key left out is lost: the
file is rewritten whole, storing only what differs from the level below.

```bash
python3 <skill>/scripts/config.py save user --dry-run < <file>
python3 <skill>/scripts/config.py save project --project <repo> --dry-run < <file>
```

On a non-zero exit, fix the printed problems with the person and run it
again. On exit 0, `written` is exactly what will be stored. Then run it
without `--dry-run`.

## 5. Finish

Run `python3 <skill>/scripts/config.py check [--project <repo>]` and show the
result. Tell the person what changed, and that agents already running keep
the settings and bundle they started with. When a project was just set up,
the next step is the foreman: `claude --agent agent-foreman`, then name the
work (for example: "Run issues #12 and #15 of acme/api").
