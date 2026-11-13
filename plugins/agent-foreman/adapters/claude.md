# Agent kind: claude (Claude Code)

What is particular to Claude Code agents. The code side is
`scripts/adapters/claude.py`; this page is the screen side. `H` is as in
`terminals/herdr.md`.

| Item | Claude Code |
| --- | --- |
| herdr kind | `claude` |
| Command | `claude --name <name> --session-id <id> --model <model> [--dangerously-skip-permissions] --plugin-dir <bundle>`, in the agent's clone (`-w <name>` only with `launch.worktree` on) |
| Skills in a brief | `foreman-kit:<skill>` |
| Transcript | `~/.claude/projects/*/<session id>.jsonl`, read by `transcript.py` |
| Prompt mode | `claude -p --output-format json` with the prompt on stdin; `launch.py --print` runs it and keeps the JSON |
| Trust | Asked once per folder; a trusted parent folder does not count. Answered for clones the foreman made ("Trust question") |

## Start errors

- `Workspace trust not yet accepted`: only a worktree session (`-w`, with
  `launch.worktree` on) shows it; it cannot start in a folder Claude Code was
  never trusted in. Tell the person to run `claude` once in that checkout and
  accept the trust question. Never accept it for them.

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
- Answer it only when `clone.py check <folder>` (on that machine) says
  `"ours": true`: `H pane send-keys <pane> Down`, then `H pane send-keys
  <pane> Enter`. The input line follows. Claude Code then records the folder
  as trusted in `~/.claude.json`.
- Any other folder's trust question goes to the person. Never answer it.
- Checked 2026-11-13 with Claude Code 2.1.322: `/` was trusted and a folder
  under it still asked. A machine where bypass mode was never accepted may
  show that confirmation next; it was not seen here, so it goes to the person.

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
2. Read the pane. Only a worktree session asks "Keep worktree" (1) or
   "Remove worktree" (2). When the agent's changes are pushed, `H pane
   send-keys <pane> Down` then `Enter`; the pane prints `Worktree removed.`.
3. When the agent is still in `H agent list`, close the tab (`H tab close
   <tab>`), which ends the process. A worktree left behind is removed with
   `git -C <checkout> worktree remove <path>`; a clone with `clone.py
   remove`.
