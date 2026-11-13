#!/usr/bin/env python3
"""Score a task's difficulty: likelihood L from the change's size, spread and
fix history, impact I from the paths it touches, then a level and low, mid
or high. The foreman adds what paths cannot show and decides.

Usage:
  score.py estimate --project OWNER/REPO [--issue N] [--paths P,...] [--lines N]
                    [--files N] [--bug] [--previous low|mid|high]
  score.py diff [--base REF] [--cwd DIR] [--project OWNER/REPO] [--previous low|mid|high]

`estimate` is for an issue before any code: the foreman gives the paths it
expects and a size estimate; `--issue` reads the issue's labels and title.
`diff` measures `git diff BASE...HEAD` in a checkout (default base
`origin/main`) and the touched files' fix history. With --previous the
difficulty never goes down.

Level = I when L is 0 or 1, else I + 1, at most 3. Difficulty: low = level 0,
mid = 1, high = 2 or 3. Thresholds and path patterns come from the settings'
`difficulty` section (or the bundle's `config.json` when run from a bundle).

Prints one JSON object. Exit codes: 2 = bad arguments, 1 = git or gh failed.
"""
import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

LEVELS = ["low", "mid", "high"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def settings(project=None):
    """The `difficulty` settings: from the bundle this runs in, or merged."""
    marker = os.path.join(ROOT, "bundle.json")
    if os.path.isfile(marker) and os.path.isfile(os.path.join(ROOT, "config.json")):
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f)["difficulty"]
    from config import load
    return load(project)["difficulty"]


def matches(path, pattern):
    """A glob where `**/` may match nothing: `**/auth/**` matches `auth/x.py`."""
    pat = pattern[3:] if pattern.startswith("**/") else pattern
    return fnmatch.fnmatch("/" + path, "*/" + pat) or fnmatch.fnmatch(path, pat)


def any_match(path, patterns):
    return [p for p in patterns if matches(path, p)]


def impact(paths, cfg):
    """(I, reasons, docs_only). Paths alone cannot see user-visible behavior;
    the foreman adds that."""
    if not paths:
        return 1, ["no paths known; impact 1 until the paths are"], False
    reasons, level = [], 0
    for path in paths:
        hit = any_match(path, cfg["critical"])
        if hit:
            level = 3
            reasons.append(f"{path}: critical ({hit[0]})")
            continue
        hit = any_match(path, cfg["public"])
        if hit:
            level = max(level, 2)
            reasons.append(f"{path}: public surface ({hit[0]})")
            continue
        if not any_match(path, cfg["docs_tests"]):
            level = max(level, 1)
    docs_only = all(any_match(p, cfg["docs"]) for p in paths)
    if level == 1 and not reasons:
        reasons.append("runtime code")
    if level == 0:
        reasons.append("docs or tests only")
    return level, reasons, docs_only


def likelihood(lines, files, dirs, bug, recent_fixes, cfg):
    """(L, reasons): one point each for size, spread and fix history."""
    reasons = []
    if lines is not None and lines > cfg["lines"]:
        reasons.append(f"{lines} changed lines > {cfg['lines']}")
    spread = []
    if files is not None and files > cfg["files"]:
        spread.append(f"{files} files > {cfg['files']}")
    if dirs is not None and dirs >= cfg["top_dirs"]:
        spread.append(f"{dirs} top-level directories >= {cfg['top_dirs']}")
    if spread:
        reasons.append("; ".join(spread))
    history = []
    if bug:
        history.append("a bug fix")
    if recent_fixes:
        history.append(f"fixes in the last {cfg['fix_days']} days: {', '.join(recent_fixes[:5])}")
    if history:
        reasons.append("; ".join(history))
    return min(3, len(reasons)), reasons


def result(L, l_reasons, I, i_reasons, docs_only, previous, metrics, judge):
    level = I if L <= 1 else min(3, I + 1)
    difficulty = LEVELS[min(2, level)]
    if previous and LEVELS.index(previous) > LEVELS.index(difficulty):
        difficulty = previous
        judge = judge + [f"kept {previous}: the difficulty never goes down"]
    return {"difficulty": difficulty, "level": level, "likelihood": L, "likelihood_reasons": l_reasons,
            "impact": I, "impact_reasons": i_reasons, "trivial_candidate": docs_only,
            "person_approves_merge": difficulty == "high", "metrics": metrics, "judge": judge}


def _git(cwd, *args):
    out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    if out.returncode != 0:
        print(f"score.py: git {' '.join(args)} failed: {out.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    return out.stdout


def fix_words(cfg):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in cfg["fix_words"]) + r")\b", re.I)


def diff_metrics(cwd, base, cfg):
    numstat = _git(cwd, "diff", "--numstat", f"{base}...HEAD")
    paths, lines = [], 0
    for row in numstat.splitlines():
        added, deleted, path = row.split("\t", 2)
        if " => " in path:  # a rename: score the new path
            path = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", path).split(" => ")[-1]
        paths.append(path)
        if added != "-":
            lines += int(added) + int(deleted)
    words = fix_words(cfg)
    subjects = _git(cwd, "log", "--format=%s", f"{base}..HEAD").splitlines()
    bug = any(words.search(s) for s in subjects)
    recent = []
    existing = [p for p in paths if os.path.exists(os.path.join(cwd, p))]
    if existing:
        history = _git(cwd, "log", f"--since={cfg['fix_days']}.days.ago", "--format=%h %s", base, "--", *existing)
        recent = [line.split(" ", 1)[0] for line in history.splitlines() if words.search(line)]
    dirs = len({p.split("/", 1)[0] if "/" in p else "." for p in paths})
    return paths, lines, dirs, bug, recent


def issue_facts(project, number, cfg):
    out = subprocess.run(["gh", "issue", "view", str(number), "--repo", project, "--json", "title,labels"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(f"score.py: gh issue view failed: {out.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(out.stdout)
    words = fix_words(cfg)
    texts = [data.get("title", "")] + [l.get("name", "") for l in data.get("labels", [])]
    return any(words.search(t) for t in texts)


def main(argv):
    ap = argparse.ArgumentParser(prog="score.py", description="agent-foreman difficulty score")
    ap.add_argument("mode", choices=["estimate", "diff"])
    ap.add_argument("--project", metavar="OWNER/REPO")
    ap.add_argument("--issue", type=int)
    ap.add_argument("--paths", default="")
    ap.add_argument("--lines", type=int)
    ap.add_argument("--files", type=int)
    ap.add_argument("--bug", action="store_true")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--cwd", default=".")
    ap.add_argument("--previous", choices=LEVELS)
    args = ap.parse_args(argv)
    if args.mode == "estimate" and not args.project:
        print("score.py: estimate needs --project", file=sys.stderr)
        return 2
    cfg = settings(args.project)

    if args.mode == "estimate":
        paths = [p.strip() for p in args.paths.split(",") if p.strip()]
        bug = args.bug or (issue_facts(args.project, args.issue, cfg) if args.issue else False)
        files = args.files if args.files is not None else (len(paths) or None)
        dirs = len({p.split("/", 1)[0] if "/" in p else "." for p in paths}) if paths else None
        L, l_reasons = likelihood(args.lines, files, dirs, bug, [], cfg)
        I, i_reasons, docs_only = impact(paths, cfg)
        judge = ["user-visible behavior, a public API or a shared library the path patterns miss (impact 2)",
                 "more than an hour of human work (likelihood)",
                 "estimate mode: score again with `diff` once the change exists"]
        metrics = {"paths": paths, "lines": args.lines, "files": files, "dirs": dirs, "bug": bug}
    else:
        paths, lines, dirs, bug, recent = diff_metrics(args.cwd, args.base, cfg)
        L, l_reasons = likelihood(lines, len(paths), dirs, bug, recent, cfg)
        I, i_reasons, docs_only = impact(paths, cfg)
        judge = ["user-visible behavior, a public API or a shared library the path patterns miss (impact 2)"]
        metrics = {"base": args.base, "lines": lines, "files": len(paths), "dirs": dirs, "bug": bug,
                   "recent_fixes": recent}
    print(json.dumps(result(L, l_reasons, I, i_reasons, docs_only, args.previous, metrics, judge), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
