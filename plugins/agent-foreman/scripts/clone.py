#!/usr/bin/env python3
"""Every agent that touches files works in its own clone, which this script
makes, recognizes and removes.

A clone lives at `~/.cache/agent-foreman/work/<owner>-<repo>/<task>/<agent>`
on the agent's machine. It is cloned from a local repository (the project's
checkout on that machine, or the lead's clone for a role agent), then its
`origin` is set to the source's `origin` URL and fetched, so `git push` and
`gh` reach GitHub and not the source. It starts detached at --ref with no
local branch; the agent cuts its own. --no-push points origin's push URL
nowhere, for an agent that only judges: `gh` still finds the repository, and
`git push` to origin fails (a push to a URL named outright still works; this
is not a sandbox). A marker in `.git` records that agent-foreman made it.

Usage:
  clone.py make --project OWNER/REPO --task TASK --agent AGENT --ref REF
                [--from PATH] [--machine MACHINE] [--no-push] [--fresh] [--force]
  clone.py check PATH [--machine MACHINE]
  clone.py remove --project OWNER/REPO --task TASK [--agent AGENT] [--machine MACHINE] [--force]

make: --from defaults to the project's checkout on that machine (its
settings); --ref is what to check out (detached), such as `origin/main` or a
head SHA. An existing clone of the same agent is kept (status `exists`);
--fresh removes it first, under the same rules as remove.

check: whether PATH is a clone agent-foreman made under the work root. Only
such a folder's trust question may be answered for the person.

remove: one agent's clone, or with no --agent every clone of the task and
its run directory (`~/.cache/agent-foreman/runs/<owner>-<repo>/<task>`). It
refuses a folder without the marker, a folder holding the caller's working
directory, and, unless --force, a clone with changes to tracked files or
commits that are on no remote.

MACHINE is a herdr machine label, or `local` (the default); a remote machine
runs this same file over SSH. Prints one JSON object.

Exit codes: 1 = refused or git failed, 2 = bad arguments, 3 = setup needed.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time

WORK = "~/.cache/agent-foreman/work"
RUNS = "~/.cache/agent-foreman/runs"
MARK = "agent-foreman.json"
NO_PUSH = "no-push-from-this-clone"


# --- runs on the agent's machine; standard library only ---------------------

def _git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def _root():
    return os.path.realpath(os.path.expanduser(WORK))


def clone_path(key, task, agent):
    return os.path.join(_root(), key, task, agent)


def check(path):
    real = os.path.realpath(os.path.expanduser(path))
    if not real.startswith(_root() + os.sep):
        return {"ours": False, "path": real, "reason": f"not under {WORK}"}
    mark = os.path.join(real, ".git", MARK)
    if not os.path.isfile(mark):
        return {"ours": False, "path": real, "reason": "no agent-foreman marker in .git"}
    with open(mark, encoding="utf-8") as f:
        return {"ours": True, "path": real, **json.load(f)}


def _unsafe(path):
    """Why removing a clone would lose work, or ""."""
    changed = _git("diff", "--name-only", "HEAD", cwd=path)
    if changed:
        return "changes to tracked files: " + ", ".join(changed.splitlines()[:5])
    local = _git("rev-list", "--max-count=5", "HEAD", "--branches", "--not", "--remotes", cwd=path)
    if local:
        return "commits on no remote: " + ", ".join(sha[:9] for sha in local.splitlines())
    return ""


def _remove_one(path, force):
    found = check(path)
    if not found["ours"]:
        return found["reason"]
    here = os.path.realpath(os.getcwd())
    if here == found["path"] or here.startswith(found["path"] + os.sep):
        return "the working directory is inside it; run from outside"
    if not force:
        reason = _unsafe(found["path"])
        if reason:
            return reason + " (--force removes it anyway)"
    shutil.rmtree(found["path"])
    return ""


def remove(key, task, agent=None, force=False):
    task_dir = os.path.join(_root(), key, task)
    paths = [clone_path(key, task, agent)] if agent else (
        sorted(os.path.join(task_dir, d) for d in os.listdir(task_dir)) if os.path.isdir(task_dir) else [])
    removed, refused = [], []
    for path in paths:
        if not os.path.exists(path):
            continue
        reason = _remove_one(path, force)
        (refused.append({"path": path, "reason": reason}) if reason else removed.append(path))
    if not agent and not refused:
        runs = os.path.join(os.path.expanduser(RUNS), key, task)
        if os.path.isdir(runs):
            shutil.rmtree(runs)
            removed.append(runs)
    for empty in (task_dir, os.path.dirname(task_dir)):
        if os.path.isdir(empty) and not os.listdir(empty):
            os.rmdir(empty)
    return {"removed": removed, "refused": refused}


def make(key, task, agent, source, ref, fresh=False, force=False, no_push=False):
    dest = clone_path(key, task, agent)
    if os.path.exists(dest):
        if not fresh:
            found = check(dest)
            if not found["ours"]:
                return {"error": f"{dest} exists and is not a clone agent-foreman made: {found['reason']}"}
            return {"path": dest, "status": "exists", "head": _git("rev-parse", "HEAD", cwd=dest)}
        reason = _remove_one(dest, force)
        if reason:
            return {"error": f"cannot replace {dest}: {reason}"}
    source = os.path.realpath(os.path.expanduser(source))
    if not os.path.isdir(os.path.join(source, ".git")):
        return {"error": f"{source} is not a git checkout"}
    try:
        origin = _git("remote", "get-url", "origin", cwd=source)
    except RuntimeError:
        return {"error": f"{source} has no origin remote to push to"}
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        _git("clone", "--quiet", source, dest)
        _git("remote", "set-url", "origin", origin, cwd=dest)
        if no_push:
            _git("remote", "set-url", "--push", "origin", NO_PUSH, cwd=dest)
        _git("fetch", "--quiet", "--prune", "origin", cwd=dest)
        _git("checkout", "--quiet", "--detach", ref, cwd=dest)
        # The branch `git clone` made is the source's, not the agent's; the agent cuts its own.
        for branch in _git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=dest).split():
            _git("branch", "--quiet", "-D", branch, cwd=dest)
        with open(os.path.join(dest, ".git", MARK), "w", encoding="utf-8") as f:
            json.dump({"project": key, "task": task, "agent": agent, "source": source, "ref": ref, "push": not no_push,
                       "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f)
        head = _git("rev-parse", "HEAD", cwd=dest)
    except RuntimeError as e:
        shutil.rmtree(dest, ignore_errors=True)
        return {"error": str(e)}
    return {"path": dest, "status": "made", "origin": origin, "push": not no_push, "head": head}


def run(request):
    op = request.pop("op")
    try:
        return {"make": make, "check": check, "remove": remove}[op](**request)
    except (OSError, RuntimeError) as e:
        return {"error": str(e)}


# --- runs where the command is given ----------------------------------------

def on_machine(label, request, saved=None):
    if label == "local":
        return run(dict(request))
    if saved is None:
        from config import herdr_machines
        saved = herdr_machines()
    if label not in saved:
        raise ValueError(f"{label} is not a saved herdr machine")
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        source = f.read()
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", saved[label]["target"],
                        "python3 - _run " + shlex.quote(json.dumps(request))],
                       input=source, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{label}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout)


def main(argv):
    if argv[:1] == ["_run"]:
        print(json.dumps(run(json.loads(argv[1]))))
        return 0
    from config import EXIT_SETUP_NEEDED, NAME, REPO, load
    ap = argparse.ArgumentParser(prog="clone.py", description="agent-foreman agent clones")
    ap.add_argument("command", choices=["make", "check", "remove"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--task")
    ap.add_argument("--agent")
    ap.add_argument("--ref")
    ap.add_argument("--from", dest="source", metavar="PATH")
    ap.add_argument("--machine", default="local")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    def bad(message):
        print(f"clone.py: {message}", file=sys.stderr)
        return 2

    if args.command == "check":
        if not args.path:
            return bad("check needs a path")
        request = {"op": "check", "path": args.path}
    else:
        if not (args.project and REPO.match(args.project)):
            return bad("--project must look like owner/name")
        if not (args.task and NAME.match(args.task)):
            return bad("--task may hold letters, digits, '.', '_' and '-' only")
        if args.agent is not None and not NAME.match(args.agent):
            return bad("--agent may hold letters, digits, '.', '_' and '-' only")
        key = args.project.replace("/", "-")
        if args.command == "remove":
            request = {"op": "remove", "key": key, "task": args.task, "agent": args.agent, "force": args.force}
        else:
            if not (args.agent and args.ref):
                return bad("make needs --agent and --ref")
            source = args.source or load(args.project).get("machines", {}).get(args.machine)
            if not source:
                print(f"clone.py: no --from, and project {args.project} names no checkout on {args.machine}",
                      file=sys.stderr)
                return EXIT_SETUP_NEEDED
            request = {"op": "make", "key": key, "task": args.task, "agent": args.agent, "source": source,
                       "ref": args.ref, "fresh": args.fresh, "force": args.force, "no_push": args.no_push}
    try:
        out = on_machine(args.machine, request)
    except (ValueError, RuntimeError) as e:
        print(f"clone.py: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"machine": args.machine, **out}, indent=2))
    return 1 if out.get("error") or out.get("refused") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
