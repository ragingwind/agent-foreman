#!/usr/bin/env python3
"""Error reports: what went wrong in a project's run of agent-foreman, kept
in one form so that it can be tracked, reproduced, analysed and fixed
(`error-report.md`).

A report is one JSON file in the project's folder (`config.py paths
--project`, state): `projects/<owner>-<repo>/error-reports/E<n>.json`. The
evidence that `collect` copies goes next to it, in `E<n>/`, because the task
folder and the clones are removed after the merge.

Usage:
  errors.py new --project OWNER/REPO --title TEXT [--severity high|medium|low]
                [--owner foreman|project|outside] [--task N] [--step ID] [--machine LABEL]
                [--observed TEXT] [--expected TEXT]
  errors.py collect --project OWNER/REPO --id E<n> [--task N] [--machine LABEL]
  errors.py set --project OWNER/REPO --id E<n> --json OBJECT
  errors.py add --project OWNER/REPO --id E<n> --to evidence|fix|links|repro --json VALUE
  errors.py list --project OWNER/REPO [--status STATUS] [--owner OWNER]
  errors.py show --project OWNER/REPO --id E<n>
  errors.py check --project OWNER/REPO

Fields (`set` replaces top-level fields, `add` appends one item to a list):

  id, created                 written by `new`
  title                       one line
  project, task, step, round, machine
  severity                    high | medium | low
  owner                       foreman (this plugin) | project (its settings
                              or repository) | outside (a provider, a model,
                              herdr, a machine)
  status                      open | analyzed | fixed | wontfix | duplicate
  observed, expected, impact  text: what happened (facts only), what should
                              have happened, who had to redo what
  versions                    {name: text}: `new` writes the plugin's version
                              and commit; add the profile, model, agent CLI
  evidence                    [{kind, path, note}]; kind is status, meta,
                              answer, log, gate, pane, file or other. A path
                              under E<n>/ is a copy that `collect` made
  repro                       {steps: [text], fixture: text or null,
                              reproduced: true, false or null}
  cause                       {text, confidence: confirmed | guessed,
                              evidence: [indexes into evidence]}
  fix                         [{text, owner, status: proposed | applied,
                              commit: text or null}]
  links                       [text]: another report's id, an issue or pull
                              request URL, a commit

The script keeps these rules, and writes no change that breaks one: a
confirmed cause names its evidence; `analyzed` needs a cause; `fixed` needs
an applied fix with its commit; `duplicate` needs a link to another report.

`collect` copies the task folder (from the foreman's archive of it, or from
the task's machine) to `E<n>/task/` and the task's lines of the foreman's
log to `E<n>/log.jsonl`, and adds them to evidence. It copies no settings
and no environment.

Exit codes: 1 = no such report or task folder, or a copy failed, 2 = bad
arguments or a broken rule.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from config import LOCAL, REPO, SKILL_DIR, log_path, project_dir

SEVERITIES = ["high", "medium", "low"]
OWNERS = ["foreman", "project", "outside"]
STATUSES = ["open", "analyzed", "fixed", "wontfix", "duplicate"]
KINDS = ["status", "meta", "answer", "log", "gate", "pane", "file", "other"]
CONFIDENCE = ["confirmed", "guessed"]
FIX_STATUSES = ["proposed", "applied"]
TEXT = ["title", "observed", "expected", "impact", "task", "step", "machine", "project"]
FIELDS = TEXT + ["id", "created", "round", "severity", "owner", "status", "versions", "evidence", "repro", "cause",
                 "fix", "links"]
LISTS = {"evidence": "evidence", "fix": "fix", "links": "links", "repro": "repro.steps"}
ID = re.compile(r"^E([1-9][0-9]*)$")


def folder(repo):
    return os.path.join(project_dir(repo), "error-reports")


def path_of(repo, rid):
    return os.path.join(folder(repo), f"{rid}.json")


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def plugin_versions():
    out = {}
    try:
        with open(os.path.join(SKILL_DIR, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            out["plugin"] = str(json.load(f).get("version", ""))
    except (OSError, ValueError):
        pass
    r = subprocess.run(["git", "-C", SKILL_DIR, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        out["commit"] = r.stdout.strip()
    return out


def problems(report):
    """Every way the report breaks the form or its rules."""
    p = []
    if not isinstance(report, dict):
        return ["a report is a JSON object"]
    p += [f"unknown field {k!r}" for k in report if k not in FIELDS]
    if not ID.match(str(report.get("id", ""))):
        p.append("id must look like E<n>")
    if not str(report.get("title", "")).strip():
        p.append("title is empty")
    p += [f"{k} must be text" for k in TEXT if report.get(k) is not None and not isinstance(report[k], str)]
    if report.get("round") is not None and (not isinstance(report["round"], int) or isinstance(report["round"], bool)):
        p.append("round must be a whole number")
    for key, allowed in (("severity", SEVERITIES), ("owner", OWNERS), ("status", STATUSES)):
        if report.get(key) not in allowed:
            p.append(f"{key} must be one of {', '.join(allowed)}")
    versions = report.get("versions", {})
    if not (isinstance(versions, dict) and all(isinstance(v, str) for v in versions.values())):
        p.append("versions must map names to text")
    evidence = report.get("evidence", [])
    if not isinstance(evidence, list):
        p.append("evidence must be a list")
        evidence = []
    for i, e in enumerate(evidence):
        if not (isinstance(e, dict) and e.get("kind") in KINDS and isinstance(e.get("path"), str) and e["path"]):
            p.append(f"evidence {i}: needs a kind ({', '.join(KINDS)}) and a path")
    repro = report.get("repro", {})
    if not (isinstance(repro, dict) and isinstance(repro.get("steps", []), list)
            and all(isinstance(s, str) for s in repro.get("steps", []))
            and repro.get("reproduced") in (True, False, None)
            and (repro.get("fixture") is None or isinstance(repro["fixture"], str))):
        p.append("repro must be {steps: [text], fixture: text or null, reproduced: true, false or null}")
    cause = report.get("cause")
    if cause is not None:
        refs = cause.get("evidence", []) if isinstance(cause, dict) else None
        if not (isinstance(cause, dict) and str(cause.get("text", "")).strip()
                and cause.get("confidence") in CONFIDENCE and isinstance(refs, list)):
            p.append("cause must be {text, confidence: confirmed or guessed, evidence: [indexes]}")
        elif any(not isinstance(r, int) or isinstance(r, bool) or not 0 <= r < len(evidence) for r in refs):
            p.append(f"cause: evidence names an index that is not in evidence (0 to {len(evidence) - 1})")
        elif cause["confidence"] == "confirmed" and not refs:
            p.append("cause: a confirmed cause names its evidence")
    fixes = report.get("fix", [])
    if not isinstance(fixes, list):
        p.append("fix must be a list")
        fixes = []
    for i, f in enumerate(fixes):
        if not (isinstance(f, dict) and str(f.get("text", "")).strip() and f.get("owner") in OWNERS
                and f.get("status") in FIX_STATUSES and (f.get("commit") is None or isinstance(f["commit"], str))):
            p.append(f"fix {i}: needs text, an owner ({', '.join(OWNERS)}), a status (proposed or applied) "
                     f"and a commit or null")
    links = report.get("links", [])
    if not (isinstance(links, list) and all(isinstance(x, str) for x in links)):
        p.append("links must be a list of text")
        links = []
    status = report.get("status")
    if status == "analyzed" and not cause:
        p.append("status analyzed needs a cause")
    if status == "fixed" and not any(isinstance(f, dict) and f.get("status") == "applied" and f.get("commit")
                                     for f in fixes):
        p.append("status fixed needs an applied fix with its commit")
    if status == "duplicate" and not any(ID.match(x) and x != report.get("id") for x in links):
        p.append("status duplicate needs a link to another report (E<n>)")
    return p


def load(repo, rid):
    if not ID.match(rid or ""):
        raise LookupError(f"--id must look like E<n>, not {rid!r}")
    try:
        with open(path_of(repo, rid), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise LookupError(f"no report {rid} in {folder(repo)}")


def write(repo, report):
    found = problems(report)
    if found:
        raise ValueError("; ".join(found))
    os.makedirs(folder(repo), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder(repo), prefix=".tmp.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path_of(repo, report["id"]))


def all_reports(repo):
    out = []
    if os.path.isdir(folder(repo)):
        for name in os.listdir(folder(repo)):
            m = re.match(r"^(E[1-9][0-9]*)\.json$", name)
            if m:
                out.append(load(repo, m.group(1)))
    return sorted(out, key=lambda r: int(r["id"][1:]))


def new(repo, title, **fields):
    taken = [int(m.group(1)) for n in (os.listdir(folder(repo)) if os.path.isdir(folder(repo)) else [])
             for m in [re.match(r"^E([1-9][0-9]*)\.json$", n)] if m]
    report = {"id": f"E{max(taken, default=0) + 1}", "title": title, "created": now(), "project": repo,
              "severity": fields.pop("severity", None) or "medium", "owner": fields.pop("owner", None) or "foreman",
              "status": "open", **{k: v for k, v in fields.items() if v is not None},
              "versions": plugin_versions(), "evidence": [], "repro": {"steps": [], "fixture": None, "reproduced": None},
              "cause": None, "fix": [], "links": []}
    write(repo, report)
    return report


def collect(repo, rid, task, machine):
    """Copy the task folder and the task's log lines into E<n>/, and add them to the report's evidence."""
    from clone import archive
    report = load(repo, rid)
    task = task or report.get("task")
    if not task:
        raise LookupError("the report names no task; pass --task")
    dest = os.path.join(folder(repo), rid)
    copied = os.path.join(dest, "task")
    archived = os.path.join(project_dir(repo), "tasks", task)
    if os.path.isdir(archived):
        shutil.copytree(archived, copied, dirs_exist_ok=True)
        source = f"the foreman's archive ({archived})"
    else:
        machine = machine or report.get("machine") or LOCAL
        got = archive(machine, repo.replace("/", "-"), task, copied)
        if got.get("error"):
            raise RuntimeError(got["error"])
        source = f"the task folder on {machine}"
    lines = []
    if os.path.exists(log_path(repo)):
        with open(log_path(repo), encoding="utf-8") as f:
            for raw in f:
                try:
                    if str(json.loads(raw).get("task")) == str(task):
                        lines.append(raw if raw.endswith("\n") else raw + "\n")
                except ValueError:
                    continue
    with open(os.path.join(dest, "log.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(lines)
    rel = lambda *p: os.path.join(rid, *p)
    items = [{"kind": "status", "path": rel("task", "status.jsonl"), "note": f"task {task}'s status lines, from {source}"},
             {"kind": "log", "path": rel("log.jsonl"), "note": f"the foreman's {len(lines)} log line(s) for task {task}"}]
    if os.path.isdir(os.path.join(copied, "reviews")):
        items.append({"kind": "meta", "path": rel("task", "reviews") + "/",
                      "note": "each role run's prompt, answer and meta (model, head, ok, exit code)"})
    if os.path.exists(os.path.join(copied, "gates.jsonl")):
        items.append({"kind": "gate", "path": rel("task", "gates.jsonl"), "note": "each gate run's result"})
    for item in items:  # a path collected before keeps its place, so the cause's evidence indexes stay right
        same = [e for e in report["evidence"] if e.get("path") == item["path"]]
        if same:
            same[0].update(item)
        else:
            report["evidence"].append(item)
    report.setdefault("task", task)
    write(repo, report)
    return {"id": rid, "copied": dest, "from": source, "log_lines": len(lines), "evidence": len(report["evidence"])}


def markdown(r):
    where = ", ".join(x for x in (f"task {r['task']}" if r.get("task") else "", f"step {r['step']}" if r.get("step")
                                  else "", f"round {r['round']}" if r.get("round") else "",
                                  f"machine {r['machine']}" if r.get("machine") else "") if x)
    out = [f"## {r['id']}. {r['title']} ({r['severity']}, {r['owner']}, {r['status']})", ""]
    for label, value in (("Where", where), ("Observed", r.get("observed")), ("Expected", r.get("expected")),
                         ("Impact", r.get("impact"))):
        if value:
            out.append(f"- **{label}**: {value}")
    cause = r.get("cause")
    if cause:
        refs = ", ".join(f"[{i}]" for i in cause["evidence"])
        out.append(f"- **Cause ({cause['confidence']})**: {cause['text']}" + (f" Evidence: {refs}." if refs else ""))
    repro = r.get("repro") or {}
    if repro.get("steps") or repro.get("fixture"):
        state = {True: "reproduced", False: "not reproduced", None: "not tried"}[repro.get("reproduced")]
        out.append(f"- **Repro** ({state}" + (f", fixture: {repro['fixture']}" if repro.get("fixture") else "") + "):")
        out += [f"  {i}. {s}" for i, s in enumerate(repro.get("steps", []), 1)]
    if r.get("fix"):
        out.append("- **Fix**:")
        out += [f"  - {f['status']} ({f['owner']}" + (f", {f['commit']}" if f.get("commit") else "") + f"): {f['text']}"
                for f in r["fix"]]
    if r.get("evidence"):
        out.append("- **Evidence**:")
        out += [f"  - [{i}] {e['kind']}: `{e['path']}`" + (f" — {e['note']}" if e.get("note") else "")
                for i, e in enumerate(r["evidence"])]
    if r.get("versions"):
        out.append("- **Versions**: " + ", ".join(f"{k} {v}" for k, v in r["versions"].items()))
    if r.get("links"):
        out.append("- **Links**: " + ", ".join(r["links"]))
    out.append(f"- **Created**: {r['created']}")
    return "\n".join(out) + "\n"


def main(argv):
    ap = argparse.ArgumentParser(prog="errors.py", description="agent-foreman error reports")
    ap.add_argument("command", choices=["new", "collect", "set", "add", "list", "show", "check"])
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--severity", choices=SEVERITIES)
    ap.add_argument("--owner", choices=OWNERS)
    ap.add_argument("--status", choices=STATUSES, help="list: only reports with this status")
    ap.add_argument("--task")
    ap.add_argument("--step")
    ap.add_argument("--machine")
    ap.add_argument("--observed")
    ap.add_argument("--expected")
    ap.add_argument("--to", choices=sorted(LISTS))
    ap.add_argument("--json", dest="value")
    args = ap.parse_args(argv)
    if not REPO.match(args.project):
        print(f"errors.py: --project must look like owner/name, not {args.project!r}", file=sys.stderr)
        return 2
    repo = args.project
    try:
        if args.command == "new":
            if not (args.title or "").strip():
                print("errors.py: new needs --title", file=sys.stderr)
                return 2
            report = new(repo, args.title.strip(), severity=args.severity, owner=args.owner, task=args.task,
                         step=args.step, machine=args.machine, observed=args.observed, expected=args.expected)
            print(json.dumps({"id": report["id"], "path": path_of(repo, report["id"])}, indent=2))
        elif args.command == "collect":
            print(json.dumps(collect(repo, args.id, args.task, args.machine), indent=2))
        elif args.command in ("set", "add"):
            report = load(repo, args.id)
            try:
                value = json.loads(args.value or "")
            except ValueError:
                print("errors.py: --json must be valid JSON", file=sys.stderr)
                return 2
            if args.command == "set":
                if not isinstance(value, dict) or {"id", "created"} & set(value):
                    print("errors.py: set takes a JSON object of fields, never id or created", file=sys.stderr)
                    return 2
                report.update(value)
            else:
                if not args.to:
                    print(f"errors.py: add needs --to ({', '.join(sorted(LISTS))})", file=sys.stderr)
                    return 2
                target = report.setdefault("repro", {"steps": [], "fixture": None, "reproduced": None}) \
                    if args.to == "repro" else report
                key = "steps" if args.to == "repro" else args.to
                if not isinstance(target.get(key), list):
                    target[key] = []
                target[key].append(value)
            write(repo, report)
            print(json.dumps({"id": report["id"], "written": path_of(repo, report["id"])}, indent=2))
        elif args.command == "list":
            rows = [r for r in all_reports(repo) if args.status in (None, r["status"]) and
                    args.owner in (None, r["owner"])]
            print("| Id | Severity | Owner | Status | Task | Title |\n| --- | --- | --- | --- | --- | --- |")
            for r in rows:
                print(f"| {r['id']} | {r['severity']} | {r['owner']} | {r['status']} | {r.get('task') or ''} | "
                      f"{r['title']} |")
        elif args.command == "show":
            print(markdown(load(repo, args.id)), end="")
        elif args.command == "check":
            bad = 0
            for name in sorted(os.listdir(folder(repo))) if os.path.isdir(folder(repo)) else []:
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(folder(repo), name), encoding="utf-8") as f:
                        found = problems(json.load(f))
                except ValueError as e:
                    found = [f"not valid JSON: {e}"]
                for p in found:
                    print(f"{name}: {p}")
                bad += bool(found)
            if bad:
                return 2
            print("ok")
    except LookupError as e:
        print(f"errors.py: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"errors.py: not written: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"errors.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
