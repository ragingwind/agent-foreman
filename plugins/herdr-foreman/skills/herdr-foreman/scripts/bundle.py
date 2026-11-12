#!/usr/bin/env python3
"""Build a project's skill bundle and put it on a herdr machine once.

A bundle holds the project's skills (each skill directory whole, with its
scripts) in the layout the agent kind loads (its adapter's bundle_layout; for
claude, a plugin named foreman-kit), the agents' loop, launch.py with the
project's launch settings and the adapters, and transcript.py. `bundle.json`
names the agent kind. Its name is a hash of its content: a machine that
already holds it is not sent it again, and any change makes a new one.

Usage:
  bundle.py build --project OWNER/REPO [--skills REF,...] [--agent KIND]
  bundle.py push MACHINE --project OWNER/REPO [--skills REF,...] [--agent KIND]

MACHINE is a herdr machine label, or `local`. --skills adds skills for one
task to the project's own. Prints one JSON object.

Exit codes: 1 = a machine could not be reached or written, 2 = bad
arguments, 3 = setup needed (project settings, an unknown skill).
"""
import argparse
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile

import adapters
from config import (EXIT_SETUP_NEEDED, LOCAL, REPO, SKILL_DIR, cache_dir, project_path, project_skills,
                    herdr_machines, load, local_skills, plugin_list, plugin_dirs, validate)

HERE = os.path.dirname(os.path.abspath(__file__))
REMOTE_CACHE = "~/.cache/herdr-foreman"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
SKIP_FILES = {".DS_Store"}
SSH = ["ssh", "-o", "BatchMode=yes"]


def fail(code, message):
    print(f"bundle.py: {message}", file=sys.stderr)
    sys.exit(code)


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _tree(src):
    """Every file under a skill directory: relative path -> bytes."""
    out = {}
    for root, dirs, names in os.walk(src, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name in SKIP_FILES or name.endswith(".pyc"):
                continue
            out[os.path.relpath(os.path.join(root, name), src)] = _read(os.path.join(root, name))
    return out


def contents(cfg, skill_dirs, kind=adapters.DEFAULT):
    """Every file of the bundle: relative path -> bytes."""
    adapter = adapters.get(kind)
    files = {
        "bundle.json": json.dumps({"agent": kind}).encode() + b"\n",
        "config.json": json.dumps({k: cfg[k] for k in ("gateways", "profiles", "launch")},
                                  indent=2, sort_keys=True).encode() + b"\n",
        "loop.md": _read(os.path.join(SKILL_DIR, "agent", "loop.md")),
    }
    for name in ("config.py", "launch.py", "transcript.py"):
        files[f"scripts/{name}"] = _read(os.path.join(HERE, name))
    for rel, data in _tree(os.path.join(HERE, "adapters")).items():
        files[f"scripts/adapters/{rel}"] = data
    files.update(adapter.bundle_layout({ref.split(":")[-1]: _tree(src) for ref, src in skill_dirs.items()}))
    return files


def digest(files):
    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode() + b"\0" + files[rel] + b"\0")
    return h.hexdigest()[:16]


def write_local(bundle_hash, files):
    """Unpack the bundle into this machine's cache once. Returns (path, status)."""
    root = os.path.join(cache_dir(), "bundles")
    path = os.path.join(root, bundle_hash)
    if os.path.isfile(os.path.join(path, "bundle.json")):
        return path, "cached"
    os.makedirs(root, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=root, prefix=f".{bundle_hash}.")
    for rel, data in files.items():
        dest = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
    try:
        os.rename(tmp, path)
    except OSError:
        shutil.rmtree(tmp)  # another run put the same bundle there first
    return path, "built"


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, files[rel])
    return buf.getvalue()


def ssh(target, command):
    r = subprocess.run(SSH + [target, command], capture_output=True, text=True)
    if r.returncode != 0:
        fail(1, f"ssh {target} failed ({r.returncode}): {r.stderr.strip()[:300]}")
    return r.stdout


def push_remote(target, bundle_hash, files):
    """Put the bundle on a remote machine once. Returns (absolute path, status)."""
    h = shlex.quote(bundle_hash)
    probe = (f"mkdir -p {REMOTE_CACHE}/bundles {REMOTE_CACHE}/briefs && cd {REMOTE_CACHE}/bundles && pwd && "
             f"if test -f {h}/bundle.json; then echo cached; else echo missing; fi")
    lines = ssh(target, probe).split()
    if len(lines) != 2:
        fail(1, f"unexpected answer from {target}: {lines!r}")
    remote_root, state = lines
    path = f"{remote_root}/{bundle_hash}"
    if state == "cached":
        return path, "cached"
    with tempfile.NamedTemporaryFile(suffix=".zip") as tmp:
        tmp.write(zipped(files))
        tmp.flush()
        r = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", tmp.name,
                            f"{target}:{remote_root}/{bundle_hash}.zip"], capture_output=True, text=True)
        if r.returncode != 0:
            fail(1, f"scp to {target} failed: {r.stderr.strip()[:300]}")
    ssh(target, f"cd {shlex.quote(remote_root)} && rm -rf {h}.tmp && python3 -m zipfile -e {h}.zip {h}.tmp && "
                f"{{ test -d {h} || mv {h}.tmp {h}; }} && rm -rf {h}.tmp {h}.zip && "
                f"test -f {h}/bundle.json")
    return path, "uploaded"


def build(repo, extra, kind=adapters.DEFAULT):
    if not os.path.exists(project_path(repo)):
        fail(EXIT_SETUP_NEEDED, f"project {repo} has no settings yet; run herdr-foreman-setup")
    cfg = load(repo)
    problems = validate(cfg, project=True)
    if problems:
        fail(EXIT_SETUP_NEEDED, f"project {repo}: {problems[0]}")
    refs = project_skills(cfg, extra)
    available = local_skills(plugin_list(plugin_dirs(cfg))) if refs else {}
    missing = [r for r in refs if r not in available]
    if missing:
        fail(EXIT_SETUP_NEEDED, f"skill not available on this machine: {', '.join(missing)} "
                                f"(config.py skills lists the ones that are; a plugin loaded with --plugin-dir "
                                f"goes in plugin_dirs: /herdr-foreman-setup plugin dirs)")
    shorts = [r.split(":")[-1] for r in refs]
    if len(set(shorts)) != len(shorts):
        fail(EXIT_SETUP_NEEDED, f"two skills share one name in the bundle: {', '.join(refs)}")
    files = contents(cfg, {r: available[r] for r in refs}, kind)
    return digest(files), files, [adapters.get(kind).skill_name(r) for r in refs]


def main(argv):
    ap = argparse.ArgumentParser(prog="bundle.py", description="herdr-foreman skill bundles")
    ap.add_argument("command", choices=["build", "push"])
    ap.add_argument("machine", nargs="?")
    ap.add_argument("--project", required=True, metavar="OWNER/REPO")
    ap.add_argument("--skills", default="", metavar="REF,...")
    ap.add_argument("--agent", default=adapters.DEFAULT, choices=adapters.KINDS)
    args = ap.parse_args(argv)
    if not REPO.match(args.project):
        fail(2, f"--project must look like owner/name, not {args.project!r}")
    if args.command == "push" and not args.machine:
        fail(2, "push needs a machine label, or local")
    extra = [s.strip() for s in args.skills.split(",") if s.strip()]

    bundle_hash, files, skills = build(args.project, extra, args.agent)
    out = {"hash": bundle_hash, "agent": args.agent, "skills": skills}
    if args.command == "build" or args.machine == LOCAL:
        path, status = write_local(bundle_hash, files)
        out.update(machine=LOCAL, path=path, status=status, cache=cache_dir())
    else:
        machines = herdr_machines()
        m = machines.get(args.machine)
        if m is None:
            fail(2, f"{args.machine!r} is not a saved herdr machine ({', '.join(machines) or 'none saved'})")
        if not m["enabled"]:
            fail(2, f"herdr machine {args.machine} is disabled")
        path, status = push_remote(m["target"], bundle_hash, files)
        out.update(machine=args.machine, path=path, status=status, cache=os.path.dirname(os.path.dirname(path)),
                   target=m["target"])
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
