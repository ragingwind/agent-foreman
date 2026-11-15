import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "plugins", "agent-foreman", "scripts")
sys.path.insert(0, SCRIPTS)


class TempHome:
    """XDG directories in a temporary folder, so no test touches real settings."""

    def __init__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = self.dir.name
        self.env = {
            "XDG_CONFIG_HOME": os.path.join(self.root, "config"),
            "XDG_STATE_HOME": os.path.join(self.root, "state"),
            "XDG_CACHE_HOME": os.path.join(self.root, "cache"),
        }
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def close(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.dir.cleanup()

    def write(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return path


def task_loop(cfg=None, difficulty="mid", trivial=False, lead=None, repo="o/r", task="7", base="main"):
    """A task's loop.json data, as `loop.py render --json` makes it, with every
    default skill from the kit."""
    import config
    import loop
    cfg = cfg or config.load()
    lead = lead or config.lead_profile(cfg, difficulty)
    resolved = {n: ("kit", n) for n in loop.KIT}
    profiles = {r: config.role_candidates(cfg, difficulty, r, lead=lead) for r in cfg["loop"]["roles"]}
    return loop.as_data(cfg, task, difficulty, trivial, resolved, lambda src, v: "foreman-kit:" + v, repo, base,
                        lead, profiles)


def providers(*extra, tiers=None, **anthropic):
    """A providers.json: Claude's own models (each with the keys given by its
    name, `sonnet={"agent": "x"}`), then the `extra` providers."""
    claude = [{"id": m, **anthropic.get(m, {})} for m in ("opus", "sonnet", "haiku")]
    return {"providers": [{"id": "anthropic", "models": claude}, *extra],
            "tiers": tiers or {"low": ["haiku"], "mid": ["sonnet"], "high": ["opus", "sonnet"]}}


def run(script, *args, env=None, stdin=None, cwd=None, workdir=None):
    """Run a script from `cwd` (default: the plugin's scripts) in the
    directory `workdir` (default: this one)."""
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run([sys.executable, os.path.join(cwd or SCRIPTS, script), *args],
                          capture_output=True, text=True, env=full, input=stdin, cwd=workdir)
