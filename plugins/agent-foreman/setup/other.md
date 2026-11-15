# Part: other settings

Everything that is not a project, a model or the loop. Each has a standard
value that works; change one only when the person wants it different. Saved
at the person's level (every project) or a project's.

| Section | Keys | Standard |
| --- | --- | --- |
| `launch` | `profile` (used only when no profile is named; the foreman names one from the tier), `permission` (`bypass` or `default`), `worktree` (`true` or `false`) | `sonnet`, `bypass`, `false` |
| `labels` | `default` (the tab label), `events` (a label per stage, or for `blocked`, `exited`, `owner-decision`). Placeholders: `{task}`, `{stage}`, `{round}`, `{machine}`, `{profile}`, `{project}` | `{task} {stage}` |
| `report` | `language` (free text in reports), `address` (how to address the person, or empty), `template` | the person's language, none, a status table |
| `ops` | `check_minutes`, `report_minutes` (a lead's stage line at least this often), `stall_minutes` (more than `report_minutes`), `backoff` (`first_hours`, `factor`), `batch` (tasks at once, or null), `placement` (`least-busy` or `ask`), `disk_check`, `disk_min_free_gb`, `after_merge` (steps) | 10, 15, 30, 1 h ×2, none, `least-busy`, on, 20, 8 steps |
| `difficulty` | `lines`, `files`, `top_dirs`, `fix_days`, `fix_words`, and the path patterns `critical`, `public`, `docs_tests`, `docs` | 400, 10, 3, 90; see `config.py show` |
| `bundle` | `skills`: skills every agent carries besides the loop's | none |

## 1. Show and ask once

Show the sections above with their current values, one line each
(`python3 <skill>/scripts/config.py show [--project <repo>]`). Ask with
AskUserQuestion: `Keep: every value as shown` (recommended), or change some.
To change, ask in one call:

- **Scope**: every project (the person's settings), or one project.
- **Sections** (multi-select): the ones to change. A question holds at most
  four options, so split the six sections over two questions.

## 2. Change

For each chosen section, ask for the keys the person wants to change, each
with `Keep: <its value now>` first. Notes:

- `permission: default` makes agents stop at permission prompts; the person
  answers them in the agent's tab, never the foreman.
- `worktree: true` only matters for an agent started outside its own clone.
- A label per stage uses the loop's stage names (`loop.py show`).
- A `bundle` skill must be one `config.py skills` lists.

## 3. Save

At the scope the person chose (`SKILL.md` "Save").
