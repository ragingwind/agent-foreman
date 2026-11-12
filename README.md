# herdr-skills

Agent skills and Claude Code plugins for [herdr](https://herdr.dev), the
terminal workspace manager for coding agents. This repository is a Claude
Code plugin marketplace: add it once, then install the plugins you want.

| Plugin | What it does |
| --- | --- |
| [herdr-foreman](plugins/herdr-foreman) | Runs one Claude Code session as the foreman of many coding agents spread over your herdr machines: places tasks, hands out briefs and skills, watches state and reports per project |

## Install

In Claude Code:

```
/plugin marketplace add ragingwind/herdr-skills
/plugin install herdr-foreman@herdr-skills
```

From a shell:

```bash
claude plugin marketplace add ragingwind/herdr-skills
claude plugin install herdr-foreman@herdr-skills
```

Each plugin's README lists its requirements, first-run steps and what it
runs on your machines.

## Development

```bash
python3 -m unittest discover -s tests
claude plugin validate .
claude plugin validate plugins/herdr-foreman
```

## License

MIT. See [LICENSE](LICENSE).
