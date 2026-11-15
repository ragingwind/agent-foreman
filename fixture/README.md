# Fixture: a run with real agents

A made-up project and two tasks to run through agent-foreman with real
agents, on this machine, with no GitHub: whether every step leaves its
evidence, and whether the foreman's checks, the gate and the merge work on
what real agents do.

| Path | Holds |
| --- | --- |
| `repo/` | The project: `stock`, a small Python CLI with tests, a CI file and a guide |
| `tasks/` | The tasks, as the foreman registers them: `1.md` (mid difficulty), `2.md` (high, so the foreman checks the plan) |
| `bin/gh` | A local stand-in for GitHub's `gh`: pull requests, their checks (`make test` on the head), labels, merges, issues, and the API calls the gate makes, in a state file. Anything else is refused and listed in the report |
| `run.py` | The run |

```bash
python3 fixture/run.py --dry-run     # prepare everything, call no model
python3 fixture/run.py               # both tasks
python3 fixture/run.py --task 2      # one task
```

The script plays the foreman's scripted part (the task folder, the loop, the
gate, the brief, the clones, the verification session, the merge gate, the
merge, the archive, the clean-up). The agents are real: the lead, the pair it
starts, the red team, QA, and the foreman's own judgment at `plan-check`.
The foreman's watching, its herdr tabs and setup are not part of the run.

It needs `claude` logged in on this machine and network, and costs real
tokens: the lead, the pair, the red team and QA run on the standard tiers
(mid: the lead on sonnet, the others on opus). It takes a while; the lead
alone may work for most of an hour.

Settings, the ledger, the log, the bundle and the report go in the run folder
(`--dir`, or a new temporary one); the person's own settings are not read or
changed. The task folders and clones go where the scripts always put them,
under `fixture-repo`, and are removed at the end.

The report (`report.md` and `report.json` in the run folder): per task, each
step's evidence line and its record check (`gate.py record`), plan-check's
word, the verdicts and rounds, the gate before ready and before merge, the
merge, the cost of each run, and every `gh` call the stand-in did not
support. Models do not answer the same way twice: read a failure for what
the agent did, not as a test that broke.

`repo/` keeps the project's `.github` as `dot-github` and its guide as
`CLAUDE.fixture.md`, so an agent working in this repository does not read
them as its own; the run copies them under their real names.
