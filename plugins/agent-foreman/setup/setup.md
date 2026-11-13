# Setup

Read from `SKILL.md` "Setup": when the person asks to set something up or
change a setting (`/agent-foreman:agent-foreman setup [part]`, or in
words), or when a check fails.

Settings have three levels, each laid over the one before: the standard
(`defaults.json` in the agent-foreman skill), the person's
(`~/.config/agent-foreman/config.json`) and a project's
(`~/.local/state/agent-foreman/projects/<owner>-<repo>/project.json`). A level
stores only what differs from the level below. Everything is personal and
lives outside any repository. Never ask for, read, print or store a token
value; a gateway holds only the name of the variable that carries it.

`<skill>` is the agent-foreman skill's directory, `..` from this file. Run its
scripts with `python3`.

## 1. Pick the parts

| Part | File | The request names |
| --- | --- | --- |
| Project | `project.md` | a repository, a machine, a checkout path |
| Models | `models.md` | a gateway, a token factory, a model, a profile, a tier |
| Loop | `loop.md` | a stage, a step, a skill, reviewers, the scenario, what a difficulty runs |
| Other | `other.md` | launch, permissions, tab labels, the report, check or stall times, disk, merge steps, difficulty thresholds, bundled skills |

When the request names a part, go straight to it. Otherwise run
`python3 <skill>/scripts/config.py projects` and ask once with AskUserQuestion
(multi-select), each option with a one-line summary of its current value:

- **Project**: marked recommended when no project is saved yet.
- **Models**
- **Loop**
- **Other settings**

## 2. Do each part

Read the part's file in this skill's directory and follow it. With several
parts, go in this order: models, project, loop, other. Models come first so
that the project's machine check covers the new gateways' token variables.

## 3. Save

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

## 4. Finish

Run `python3 <skill>/scripts/config.py check [--project <repo>]` and show the
result. Tell the person what changed, and that agents already running keep
the settings and bundle they started with. When a project was just set up,
the next step is the foreman: `claude --agent agent-foreman`, then name the
work (for example: "Run issues #12 and #15 of acme/api").
