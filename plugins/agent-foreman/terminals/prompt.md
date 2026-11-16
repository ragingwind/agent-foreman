# Terminal: prompt mode

One agent, one prompt, one JSON result. There is no tab, no pane and no
screen: nothing to read, answer or close. Use it for an agent that judges or
does one job and stops: the pair (the lead starts it in the build session's
review stage), the red team and QA (the foreman starts them in the
verification session).

## Start

In the agent's own clone (`clone.py make ... --no-push`), never in a shared
checkout, `loop.py prompt` writes the agent's prompt from the task's
`loop.json` and prints the commands that run it:

```bash
cd <clone> && python3 <bundle>/scripts/loop.py prompt --step <step> --task-dir <task folder>
```

It prints JSON: `prompt` and `out` (both in the task folder's `reviews/`) and
`commands`, one `launch.py --print --role ...` command per profile in the
order to try, never the lead's. Run the first one there. A lead runs it from
its own pane's shell and waits. The foreman runs both on another machine
through `remote.py`, with `run_in_background`:

```bash
python3 <skill>/scripts/remote.py <machine> --cwd <clone> -- \
  python3 <bundle>/scripts/loop.py prompt --step <step> --task-dir <task folder>
python3 <skill>/scripts/remote.py <machine> --cwd <clone> -- <the first command, word for word>
```

`remote.py` runs the command in that machine's login shell. A plain
`ssh <target> '<command>'` does not load the shell's setup, so `claude` is not
on `PATH` and gateway token variables are missing there (exit 3 or 4).
The login shell may print its own lines (such as a `stty` warning); the
summary is the last line of stdout.

- The prompt is a file, so its length does not matter. Nobody writes or
  edits it by hand.
- `launch.py --role` refuses a run without `--task-dir` and `--name`, with an
  `--out` outside the task folder's `reviews/`, or outside a git checkout:
  the gate counts only answers saved there with their model and head.
- A new clone needs no trust step in prompt mode, and its project skills
  (`.claude/skills/`) load. Checked on 2026-11-13 with Claude Code 2.1.322.
- `<task folder>` is `status.py dir --project <repo> --task <task>` on the
  agent's machine. `--task-dir` lets the agent's hooks write heartbeats to its
  status file.

## Result

`launch.py` prints one line of JSON:

| Field | Meaning |
| --- | --- |
| `ok` | The run finished with a result |
| `session_id` | The session, for `transcript.py` |
| `cost` | Its cost in USD, as the agent reports it |
| `denials` | How many tool calls the permission mode refused |
| `out` | The file with the agent's whole JSON result |
| `verdict` | The word on the last `Verdict:` line of the answer, or empty |
| `error` | When not `ok`: the end of the error text, or the exit code and the end of stderr when the agent exited with an error after its result |

Next to `out`, `<out without .json>.meta.json` records the role, the agent,
the profile and model, the commit it judged, the verdict, and the agent's
exit code and the end of its stderr; the gate reads both.

## Exit codes

| Code | Meaning | Next |
| --- | --- | --- |
| 0 | `ok` | Read the result. An answer that shows `fulltest.py: not run`: the disk was under the floor; free space and start the role again. Else an empty `verdict` and no `Verdict` anywhere in the answer: the agent stopped before its end; run the next command once, as for 5 |
| 5 | The run failed: a usage limit, a gateway error, no result | Run the next command `loop.py prompt` printed; with none left, ask the person |
| 3 | Setup needed | `config.py check --project <repo>` names it; setup (`/agent-foreman:agent-foreman setup`) fixes it |
| 4 | The gateway's token variable is not set on that machine | Tell the person the variable and the machine |
| 2 | Bad arguments; with `--role`, a run outside the task folder or outside a git checkout | Run the command `loop.py prompt` printed, from the agent's clone |

## Limits

- **No dialogs.** A permission prompt or a question cannot be answered. A
  refused tool shows in `denials`; the run goes on without it.
- **No messages during a run.** A follow-up is a new run.
- **Waiting means the process exits.** A long run keeps the caller's shell
  busy, so the foreman always runs it in the background.
