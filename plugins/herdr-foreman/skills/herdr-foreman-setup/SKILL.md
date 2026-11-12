---
name: herdr-foreman-setup
description: >-
  Set up herdr-foreman: the person's own settings (gateways, profiles, launch
  defaults, plugin directories, the loop's skills and methods per stage,
  bundled skills, tab
  labels per event, report format, operating rules) and each project
  group's settings (repository, member machines and checkout paths,
  workspace label, and overrides). Detects herdr machines and the skills this
  machine's Claude Code can load, asks, validates and saves only what differs
  from the standard. Use for /herdr-foreman-setup, when herdr-foreman's
  `config.py check` fails, or when the person wants to change how the
  foreman works or add a group or machine.
---

# herdr-foreman setup

Settings have three levels, each laid over the one before: the standard
(`defaults.json` in the herdr-foreman skill), the person's, and the
group's. A level stores only what differs from the level below; a missing
value falls back. Everything is personal and lives outside any repository.

`<hf>` is the herdr-foreman skill's directory: `../herdr-foreman` from this
file. Run its scripts with `python3`.

## 1. Detect

Run these and keep the results:

- `python3 <hf>/scripts/config.py paths [--group <repo>]`: where each level
  lives.
- `python3 <hf>/scripts/config.py machines`: the saved herdr machines.
- The plugin directories this session was started with: `ps -o command= -p
  "$CLAUDE_PID"` shows the command line, and `type claude` shows a shell
  wrapper that adds `--plugin-dir`. Each `--plugin-dir <dir>` is a candidate
  for `plugin_dirs`. Scripts run the bare `claude`, so they see these
  plugins only through `plugin_dirs`.
- `python3 <hf>/scripts/config.py skills`: every skill this machine's Claude
  Code can load with the saved `plugin_dirs`, as `plugin:skill` or `skill`,
  with its directory. Run it again after `plugin_dirs` changes.
- `claude plugin details <plugin>` for each plugin with skills: each skill's
  token cost, always-on and on-invoke. Show it when the person picks skills.
- For a group: the repository (`gh repo view --json nameWithOwner -q
  .nameWithOwner` inside a checkout, or ask).

## 2. Load the current settings

`python3 <hf>/scripts/config.py show [--group <repo>]` prints the settings in
effect. Treat them as the current answers.

## 3. Ask

Ask with AskUserQuestion, one section at a time, the current value first and
marked. Never ask for a token value; a gateway holds only the name of the
environment variable that carries it.

**The person's level** (`save user`):

| Section | Ask |
| --- | --- |
| Plugin dirs | The plugin directories to load the way `claude --plugin-dir` does, so their skills can be bundled. Offer the ones found in step 1. Ask this section first: the skill choices below depend on it |
| Gateways and profiles | Each gateway's kind, base URL, auth and token variable name, its models (id, context size); each profile's agent kind (only `claude` today), gateway, model and role models |
| Launch | Default profile, permission mode (`bypass` or `default`), worktree on or off |
| Loop | For each stage in order: the skills it uses (from step 1's list, or none) and its method (standard, or the person's text). Then the tier → profile table. Stages can be removed, renamed or added |
| Bundle | Skills every agent carries besides the stages' |
| Labels | The default tab label format, then a format per event (`blocked`, `exited`, `owner-decision`) and per stage where it differs. Placeholders: `{task}`, `{stage}`, `{round}`, `{machine}`, `{profile}`, `{group}` |
| Report | Language, how to address the person (or not at all), and the status template |
| Ops | Check interval, back-off (first hours, factor), batch size, placement (`least-busy` or `ask`), disk check, the steps after a merge |

**A group's level** (`save group --group <repo>`):

- Members: for each machine (`local` or a label from step 1), the checkout
  path there. Check it with `python3 <hf>/scripts/config.py member <machine>
  <path> --agent <kind>`: it prints whether the checkout exists, whether it is
  ready for that agent kind (for `claude`: Claude Code trusts it there) and
  the reason when not, and exits 0 only when it is ready. A missing checkout is
  reported; this setup does not clone. An untrusted one cannot start a
  worktree session: tell the person to run `claude` once in that checkout
  on that machine and accept the trust question. Never accept it for them.
- Workspace label: the herdr workspace name on every member (standard: the
  repository's name).
- Then any section above that this group does differently.

Only ask what the person wants to change: start with "Keep the current
settings for <section>?" and go into a section only on "change". When the
skill is invoked with a section name, such as `/herdr-foreman-setup plugin
dirs`, go straight to that section and keep the rest as they are; any
setting can be changed this way at any time.

## 4. Validate and write

Build the settings as they should be in effect at that level, as one JSON
object, and pass it on stdin:

```bash
python3 <hf>/scripts/config.py save user --dry-run < <file>
python3 <hf>/scripts/config.py save group --group <repo> --dry-run < <file>
```

A non-zero exit prints the problems; fix them with the person and run it
again. On exit 0, the `written` field is exactly what will be stored. Then
run the same command without `--dry-run`. It rewrites the whole file, so a
second run gives the same file.

## 5. Confirm

Run `python3 <hf>/scripts/config.py check [--group <repo>]` and show its
result. Tell the person what changed, that a running foreman picks it up at
its next preflight, and that agents already running keep the bundle they
started with.
