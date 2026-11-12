# herdr commands

`H` is `herdr` for the member `local` and `herdr --machine <label>` for any
other; every command below works both ways. Commands print JSON. Pane and tab
ids (`wA:p3`, `wA:t2`) are per machine. `herdr --skill` prints herdr's own
skill; read it once per session.

## Machines and workspaces

```bash
python3 <skill>/scripts/config.py machines        # label, ssh target, enabled
H workspace list                                  # find the group's workspace label
H workspace create --cwd <checkout> --label <workspace> --no-focus
```

The new workspace id is `.result.workspace.workspace_id`. It comes with one
shell tab (`.result.tab.tab_id`); leave it as the group's shell tab. It
closes with the workspace (`H workspace close <w>`), which the foreman does
only for a workspace it made.

## Open a task tab

```bash
H tab create --workspace <w> --cwd <checkout> --label <task> --no-focus
```

The pane id is `.result.root_pane.pane_id`; the tab id is `.result.tab.tab_id`.

## Add a helper pane

```bash
H pane split <implementer pane> --direction right --cwd <checkout> --no-focus
```

The new pane id is `.result.pane.pane_id`.

## Start an agent

```bash
H pane run <pane> 'python3 <bundle>/scripts/launch.py <profile> --name <name> --session-id <id>'
H agent wait <pane> --until idle --until blocked --timeout 20000
H agent rename <pane> <name>
```

- `<bundle>` is the `path` that `bundle.py push` printed for that machine.
- `pane run` types into whatever runs in the pane. Run it only on a pane at
  a shell prompt: when `H agent list` shows an agent in that pane, the
  command would go to the agent as a prompt.
- The first waits right after `pane run` fail with `agent_not_found` while
  the app starts. Repeat the wait up to six times; do not run the command
  again.
- A wait that returns is not proof the agent runs: an agent that fails at
  start is seen for a moment, then exits. `H agent rename` succeeding is the
  proof; on `agent_not_found`, read the pane.
- When the pane shows `launch.py:` and a shell prompt instead of the agent,
  read the exit line and go to `SKILL.md` "Launch".
- `Workspace trust not yet accepted`: Claude Code has never been trusted in
  that checkout on that machine, and a worktree session cannot start. Tell
  the person to run `claude` once in the checkout there and accept the
  trust question. Never accept it for them.

## Send the brief

For `local`, write the file to `<cache>/briefs/<group>/<name>.md`. For a
remote member, write it to the scratchpad and copy it:

```bash
ssh -o BatchMode=yes <target> mkdir -p <cache>/briefs/<group>
scp -q -o BatchMode=yes <scratchpad file> <target>:<cache>/briefs/<group>/<name>.md
```

`<target>` and `<cache>` come from `bundle.py push`. Then, with
`run_in_background`:

```bash
H agent prompt <pane> "Read <cache>/briefs/<group>/<name>.md and do what it says." --wait --timeout 3600000
```

## Read

```bash
H pane read <pane> --source recent-unwrapped --lines 40
```

- `--lines` reaches back about 1000 rows. The bottom rows hold the input
  line and the status line (model and branch). Text on the input line can be
  a suggestion Claude Code shows, not the person's input; see "Input line".
- When a report is cut, read the session's transcript instead. It holds every
  answer whole:

  ```bash
  python3 <skill>/scripts/transcript.py <session id> --last 1                      # local
  ssh -o BatchMode=yes <target> python3 <bundle>/scripts/transcript.py <session id> --last 1
  ```

## Input line

Before typing into an agent, read its last rows:

```bash
H pane read <pane> --source visible --lines 6 --format ansi
```

On the `❯` line, text drawn dim (`ESC[2m`, as in `ESC[2mTry "…"`) is Claude
Code's placeholder or suggestion and is typed over. Plain text there is the
person's unsent input: leave it and report it.

## Watch

```bash
H agent wait <pane> --timeout 3600000
```

Run it with `run_in_background`. Without `--until` it returns on `idle`,
`done` or `blocked`, at once when the agent is already there, so arm it only
while the agent works. States: `idle`, `working`, `blocked` (a question or
permission dialog is open), `done`, `unknown`.

## Keys

```bash
H pane send-keys <pane> esc
```

`send-keys` takes key names only (`esc`, `Enter`, `Down`, `ctrl+u`); text
goes with `H pane send-text <pane> '<text>'`. Escape is only for closing a
question dialog the person already answered. Never answer a permission
prompt.

## Close

1. Type the command and press Enter as two calls:
   `H pane send-text <pane> '/exit'`, then `H pane send-keys <pane> Enter`.
   (`send-keys <pane> '/exit'` fails with `unsupported key`.)
2. Read the pane. A worktree session asks "Keep worktree" (1) or "Remove
   worktree" (2). When the agent's changes are pushed, `H pane send-keys
   <pane> Down` then `Enter`; the pane prints `Worktree removed.`.
3. `H agent list`: the agent is gone. When it is still there, close the tab
   (`H tab close <tab>`), which ends the process, then remove the worktree on
   that machine with `git -C <checkout> worktree remove <path>`.
4. `H pane close <pane>` for a helper pane, `H tab close <tab>` for the task
   tab.
5. Remove the task's brief file.
