# Agent kind: claude (Claude Code)

What is particular to Claude Code agents. The code side is
`scripts/adapters/claude.py`; this page is the screen side. `H` is as in
`terminals/herdr.md`.

| Item | Claude Code |
| --- | --- |
| herdr kind | `claude` |
| Command | `claude -w <name> --name <name> --session-id <id> --model <model> [--dangerously-skip-permissions] --plugin-dir <bundle>` |
| Skills in a brief | `foreman-kit:<skill>` |
| Transcript | `~/.claude/projects/*/<session id>.jsonl`, read by `transcript.py` |
| Prompt mode | `claude -p --output-format json` with the prompt on stdin; `launch.py --print` runs it and keeps the JSON |
| Checkout ready | A git checkout that Claude Code has been trusted in (`config.py member`) |

## Start errors

- `Workspace trust not yet accepted`: Claude Code has never been trusted in
  that checkout on that machine, and a worktree session cannot start. Tell
  the person to run `claude` once in the checkout there and accept the trust
  question. Never accept it for them.

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
2. Read the pane. A worktree session asks "Keep worktree" (1) or "Remove
   worktree" (2). When the agent's changes are pushed, `H pane send-keys
   <pane> Down` then `Enter`; the pane prints `Worktree removed.`.
3. When the agent is still in `H agent list`, close the tab (`H tab close
   <tab>`), which ends the process, then remove the worktree on that machine
   with `git -C <checkout> worktree remove <path>`.
