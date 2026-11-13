# herdr-skills

Agent skills and Claude Code plugins for [herdr](https://herdr.dev), the
terminal workspace manager for coding agents. This repository is a Claude
Code plugin marketplace: add it once, then install the plugins you want.

| Plugin | What it does |
| --- | --- |
| [herdr-foreman](plugins/herdr-foreman) | Turns one Claude Code session into the foreman of your coding agents across herdr machines: it sizes each task, hands it to a lead agent in its own clone, checks the result in code, and merges it or hands the merge to you |

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
claude plugin validate --strict plugins/herdr-foreman
```

## License

MIT. See [LICENSE](LICENSE).
