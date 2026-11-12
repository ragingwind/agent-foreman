# Terminal: prompt mode

One agent, one prompt, one JSON result. There is no tab, no pane and no
screen: nothing to read, answer or close. Use it for an agent that judges or
does one job and stops: a code reviewer, a retracer, a tester. A lead starts
its own; the foreman starts helpers this way when no one needs to watch.

## Start

In the agent's own clone, never in a shared checkout:

```bash
cd <clone> && python3 <bundle>/scripts/launch.py <profile> --print \
  --prompt-file <run dir>/<role>-<n>.prompt.md --out <run dir>/<role>-<n>.json \
  --session-id <uuid>
```

A lead runs it from its own pane's shell and waits. The foreman runs it on
another machine through `remote.py`, with `run_in_background`:

```bash
python3 <skill>/scripts/remote.py <machine> --cwd <clone> -- \
  python3 <bundle>/scripts/launch.py <profile> --print --prompt-file <file> --out <file>
```

`remote.py` runs the command in that machine's login shell. A plain
`ssh <target> '<command>'` does not load the shell's setup, so `claude` is not
on `PATH` and gateway token variables are missing there (exit 3 or 4).
The login shell may print its own lines (such as a `stty` warning); the
summary is the last line of stdout.

- The prompt is a file, so its length does not matter. A role's fixed prompt
  comes from the loop settings, filled in.
- `<profile>` comes from `config.py tier` for the role and the task's
  difficulty.
- A new clone needs no trust step in prompt mode, and its project skills
  (`.claude/skills/`) load. Checked on 2026-11-13 with Claude Code 2.1.322.
- `<run dir>` is `~/.cache/herdr-foreman/runs/<project>/<task>/` on the
  agent's machine.

## Result

`launch.py` prints one line of JSON:

| Field | Meaning |
| --- | --- |
| `ok` | The run finished with a result |
| `session_id` | The session, for `transcript.py` |
| `cost` | Its cost in USD, as the agent reports it |
| `denials` | How many tool calls the permission mode refused |
| `out` | The file with the agent's whole JSON result |
| `error` | When not `ok`: the end of the error text |

The verdict itself is the agent's `result` in `out`; a reviewer or retracer
also posts it on the pull request under its fixed title.

## Exit codes

| Code | Meaning | Next |
| --- | --- | --- |
| 0 | `ok` | Read the result |
| 5 | The run failed: a usage limit, a gateway error, no result | `config.py tier … --skip <profile>`, then run again with the next profile |
| 3 | Setup needed | `herdr-foreman-setup` |
| 4 | The gateway's token variable is not set on that machine | Tell the person the variable and the machine |

## Limits

- **No dialogs.** A permission prompt or a question cannot be answered. A
  refused tool shows in `denials`; the run goes on without it.
- **No messages during a run.** A follow-up is a new run.
- **Waiting means the process exits.** A long run keeps the caller's shell
  busy, so the foreman always runs it in the background.
