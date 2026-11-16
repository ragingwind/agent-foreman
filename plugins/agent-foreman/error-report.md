# Error report

When something goes wrong in a run, write it down in one form, so the
person and the next session can track it, reproduce it, find its cause and
fix it. `scripts/errors.py` keeps the reports, one JSON file each, in the
project's folder on this machine (`error-reports/E<n>.json`). Its
docstring lists every field and the rules it keeps.

## When

- The person says that something went wrong.
- Something fails in a way that no rule in `SKILL.md` covers: the gate
  blocks for a reason you cannot explain, a role ends with no verdict twice,
  an agent or a script fails at start, or an agent does what its rules
  forbid.
- Not for a finding that a verdict or the gate sends back to the lead. That
  is the loop working.

## 1. Open it

First look for an open report of the same problem: `python3
<skill>/scripts/errors.py list --project <repo> --status open`. When there
is one, add to it (step 2). Otherwise:

```bash
python3 <skill>/scripts/errors.py new --project <repo> --title "<what went wrong, in one line>" \
  --task <task> --step <step> --machine <label> --severity <high|medium|low> \
  --owner <foreman|project|outside> --observed "<what happened: facts only>" \
  --expected "<what should have happened>"
```

- **Severity**:
  - `high`: work was lost, a wrong merge or a wrong record could happen, or
    a machine ran out of disk.
  - `medium`: the person or you had to do a step again.
  - `low`: it cost only time.
- **Owner**:
  - `foreman`: this plugin's scripts and files.
  - `project`: the project's settings, its prompts, or its repository.
  - `outside`: a provider, a model, herdr, or a machine.
  - When you are not sure, write `foreman`, and change it when the cause is
    known.

Log it: `log.py add --project <repo> --event error-report --task <task>
--text "<E n>: <title>"`.

## 2. Collect the evidence

Copy the task's records before the clean-up removes them:

```bash
python3 <skill>/scripts/errors.py collect --project <repo> --id <E n>
```

It copies the task folder to `<E n>/task/`: from your archive when the task
was archived, else from the task's machine. It also copies your log lines
for the task to `<E n>/log.jsonl`. Then add, one item each, what it does not
copy: a pane's screen (save `H pane read` to a file in `<E n>/`), a part of
a transcript, or a command with its output:

```bash
python3 <skill>/scripts/errors.py add --project <repo> --id <E n> --to evidence \
  --json '{"kind": "pane", "path": "<E n>/pane.txt", "note": "<what it shows>"}'
```

Add the profile, the model, and the agent's CLI version on the machine to
`versions`. `set` replaces a field whole, so keep the plugin's version and
commit that `new` wrote (`errors.py show` prints them). Never copy a token,
a settings file or an environment into a report.

## 3. Reproduce it

Write the steps that make it happen again (`add --to repro`). Try them when
that is cheap: the fixture (`fixture/run.py` in this plugin's repository)
for the loop, or a script with made-up input for a script. Then record what
happened:

```bash
python3 <skill>/scripts/errors.py set --project <repo> --id <E n> \
  --json '{"repro": {"steps": ["<step>", "<step>"], "fixture": "<what you ran, or null>", "reproduced": true}}'
```

## 4. Find the cause

Write the cause, the evidence that shows it (its indexes in `evidence`),
and set the status to `analyzed`:

```bash
python3 <skill>/scripts/errors.py set --project <repo> --id <E n> \
  --json '{"cause": {"text": "<the cause>", "confidence": "confirmed", "evidence": [0, 2]}, "status": "analyzed"}'
```

Write `confirmed` only when a file or a reproduction shows the cause.
Otherwise write `guessed`, and say in the text what would confirm it.

## 5. Fix it

Add each fix with its owner and `proposed`:

```bash
python3 <skill>/scripts/errors.py add --project <repo> --id <E n> --to fix \
  --json '{"text": "<the change>", "owner": "<foreman|project|outside>", "status": "proposed", "commit": null}'
```

- A `foreman` fix is a change to this plugin. Tell the person; do not
  change the plugin yourself.
- A `project` fix to the settings goes through setup, after the person
  agrees.
- When a fix is in, set it again with `applied` and its commit, and set the
  report's status to `fixed`. A fix the person declines makes the report
  `wontfix`; a report of a problem that another report holds is `duplicate`,
  with a link to that one.

## 6. Tell the person

Show `errors.py show --project <repo> --id <E n>` and ask what to do with
it: keep it here, or file it as an issue (on this plugin's repository for
owner `foreman`, on the project's for owner `project`). Filing sends the
text off this machine. Before that, remove machine names, paths and
anything private, and file it only when the person says so.
