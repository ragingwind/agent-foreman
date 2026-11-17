# Agent kind: claude (Claude Code)

What is particular to Claude Code agents. The code side is
`scripts/adapters/claude.py`; this page is the screen side. `H` is as in
`terminals/herdr.md`.

| Item | Claude Code |
| --- | --- |
| herdr kind | `claude` |
| Command | `claude --name <name> --session-id <id> --model <model> [--dangerously-skip-permissions] --plugin-dir <bundle>`, in the agent's clone |
| Skills in a brief | `foreman-kit:<skill>` |
| Transcript | `~/.claude/projects/*/<session id>.jsonl`, read by `transcript.py` |
| Prompt mode | `claude -p --output-format json` with the prompt on stdin; `launch.py --print` runs it and keeps the JSON |
| Trust | Asked once per folder; a trusted parent folder does not count for a clone. `clone.py trust` answers it for clones the foreman made ("Trust question") |

## Trust question

A new folder, such as a fresh clone, opens with this before the input line:

```
 Accessing workspace:

 <folder>
 ...
 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
```

- herdr's state for it varies: `unknown` right after the start in one run,
  `blocked` about 30 seconds later in another. Do not wait on the state; read
  the pane.
- The cursor starts on **No, exit**; Enter alone ends the agent.
- Right after `pane run` starts the agent, run `python3 <skill>/scripts/clone.py
  trust <clone> --pane <pane> --machine <machine>`. It reads the pane every
  second. When the question shows, and `clone.py check` says the folder is
  ours, and the pane runs in it, it sends `Down`, then `Enter`. It returns
  when the agent is idle at its input line: `"answered"` says whether there
  was a question. Claude Code then records the folder as trusted in
  `~/.claude.json`.
- When it exits 1, read its `error` and `screen`. A question it did not
  answer goes to the person. Never answer it for a folder that is not ours.
- A trusted parent folder does not cover a clone: Claude Code looks for a
  trusted folder only up to the git repository's root, and a clone is its own
  root. Checked 2026-11-17 with Claude Code 2.1.326: a trusted parent covered
  a plain folder under it but not a git repository under it, and
  `--dangerously-skip-permissions` still asked. A machine where bypass mode
  was never accepted may show that confirmation next; it was not seen here,
  so it goes to the person.

## Screen

The bottom rows hold the input line (`❯`) and the status line (model and
branch). Above them is the last answer.

## Input line

Before typing into the agent, read its last rows:

```bash
H pane read <pane> --source visible --lines 6 --format ansi
```

On the `❯` line, text drawn dim (`ESC[2m`, as in `ESC[2mTry "…"`) is Claude
Code's placeholder or suggestion and is typed over. Plain text there is the
person's unsent input: leave it and report it.

## Exit

1. Type the command and press Enter as two calls:
   `H pane send-text <pane> '/exit'`, then `H pane send-keys <pane> Enter`.
   (`send-keys <pane> '/exit'` fails with `unsupported key`.)
2. When the agent is still in `H agent list`, close the tab (`H tab close
   <tab>`), which ends the process. Its clone is removed with `clone.py
   remove`.
