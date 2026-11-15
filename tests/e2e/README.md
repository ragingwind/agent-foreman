# End-to-end projects

Made-up projects, each in a different form, that `tests/test_e2e_projects.py`
runs the scripts on: the skills each step finds, the task's loop, the bundle,
the launch command, the machine check, the gate and the retro's facts. Their
code and skills are invented and only big enough to show the behavior.

| Project | Form |
| --- | --- |
| `orchestrated-span` | One skill takes an issue to an open pull request, with its own reviewer that fixes and pushes; a project command for QA; a commit-subject script as a gate check |
| `orchestrated-to-merge` | One skill takes an issue all the way to a merge; a batch runner makes worktrees and merges; their parts are separate skills |
| `orchestrated-straddle` | One skill does the work of two default skills (the plan and the scenario) |
| `orchestrated-gaps` | Only an implement-and-open skill, which names an agent, a script and a skill the project does not have |
| `orchestrated-similar` | Skills that look like default skills but do other work, and a skill name two plugins share |
| `vendored` | The project's own changed copy of a plugin skill, under the same name |
| `plugin-driven` | No skills in the repository; the guide says to work with a plugin |
| `guides-only` | Rules in the guide, CI, a Makefile and a pull request template |
| `bare` | Code and tests only; the person picks one of their own skills |

- `plugins/flowkit`, `plugins/otherkit`: plugins the projects use, loaded
  with `--plugin-dir`. Both have a `changelog` skill.
- `user-skills/`: the person's own skills (`~/.claude/skills`).
- `expected/<project>.json`:
  - `settings`: what setup should save for the project;
  - `expect`: what the scripts must then show;
  - `setup`: what setup should conclude (levels, conflicts, overlaps, open
    items). The scripts do not check it; it is the answer for a run of
    setup with a model.

A folder named `dot-x` becomes `.x`, and `.fixture` leaves a file's name,
when a test copies a project: the fixtures' `.claude` folders and guides
stay out of the way of an agent working in this repository.

```bash
python3 -m unittest discover -s tests -p 'test_e2e_projects.py'
```

A new form is a folder under `projects/` and its `expected/` file; the test
picks it up. A project that needs a tool names it in `needs` and is skipped
without it.
