# Part: project

The repository, the machines its agents run on, the checkout path on each,
and the project's full test command. Saved at the project's level.

## 1. Detect

- The repository and this machine's checkout, from the current directory:
  `gh repo view --json nameWithOwner -q .nameWithOwner` and `git rev-parse
  --show-toplevel`. Outside a checkout, there is no guess.
- The saved herdr machines: `python3 <skill>/scripts/config.py machines`.
- Whether the project exists (`config.py projects`); if it does, its
  settings: `python3 <skill>/scripts/config.py show --project <repo>`.
- For each enabled herdr machine, a guessed checkout path: this machine's
  path under `~`, written with `~` (`~/src/api`). Check it as in step 3
  before offering it.
- The full test command, from the checkout: first what `CLAUDE.md` (or
  `AGENTS.md`) says runs the tests, then the commands of the CI files'
  test jobs (`.github/workflows/*.yml` and the like), then a `Makefile` or
  `package.json` test target. Note where each one came from.

## 2. Show and ask once

Show what was found in one short table: the repository, and each machine
with its path and whether the check passed. Then ask with AskUserQuestion,
in one call:

- **Repository**: the detected one (recommended), or the person types
  `owner/name`.
- **Machines** (multi-select): `local` with its path, and each enabled herdr
  machine with its guessed path when the guess passed. Mark the machines an
  existing project already has as current.
- **Full test command**: the one found first (recommended), the others found,
  or none. The project's own file comes before any guess: when `CLAUDE.md`
  names one, recommend it. QA runs it in the verification session, and the
  gate runs it before merge.

For a chosen machine with no passing path, ask for its path in one more
call, one question per machine.

## 3. Check each machine

```bash
python3 <skill>/scripts/config.py check-machine <machine> <path> --project <repo>
```

It runs on that machine in its login shell, where agents start. Exit 0:
ready. Exit 3 lists the problems:

| Problem | What to tell the person |
| --- | --- |
| no git checkout at the path | Clone the repository there, or give the right path |
| the origin is another repository | The path holds another repository; give the right one |
| `claude`, `git`, `gh` or `python3` is not on PATH | Install it on that machine, or put it on PATH in the shell's profile; `gh` also needs `gh auth login` there |
| a token variable is not set | Set it in that machine's shell profile. Name the variable only |

Save a machine that has problems only when the person says so; the
foreman's preflight checks it again.

## 4. Save

At the project's level (`SKILL.md` "Save"). A new project's settings:

```json
{
  "repo": "acme/api",
  "workspace": "api",
  "machines": {
    "local": "~/src/api",
    "build-01": "~/work/api"
  },
  "tests": {"full": "make test"}
}
```

`machines` maps a herdr machine label (or `local`) to the checkout path
there. `workspace` is the herdr workspace label on every machine, the
repository's name unless the person says otherwise. `tests.full` is the
full test command; leave `tests` out when there is none. For an existing
project, start from its `config.py show --project <repo>` output and change
only `machines` and `tests`.
