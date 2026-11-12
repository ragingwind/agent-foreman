---
name: setup-models
description: >-
  Set up the models herdr-foreman's agents run on: gateways (Anthropic, or an
  Anthropic-compatible gateway such as a token factory; token variable names
  only), profiles, and the low, mid and high tiers that each task's
  difficulty picks from. The standard tiers are the harness's own models
  (haiku, sonnet, opus); fable and other gateways' models join a tier only
  when the person names them. Use for /setup-models, to add a gateway or a
  model, or to change which models a tier uses.
---

# setup-models

Writes the model part of the person's settings, `gateways`, `profiles` and
`tiers`, in `~/.config/herdr-foreman/config.json`. Nothing else.

`<hf>` is the herdr-foreman skill's directory: `../herdr-foreman` from this
file. Run its scripts with `python3`.

## How the tiers are used

- A task's difficulty (low, mid, high) gives the lead's tier. Reviewers and
  retracers take one tier above, capped at high.
- A tier is an ordered list of profiles. The first is used; on a usage limit
  or a gateway error the next one is.
- Each agent is its own process with its own profile, so one task can mix
  gateways: a lead on a token-factory model, a reviewer on Anthropic opus.
- With no settings, the standard tiers apply: low `haiku`, mid `sonnet`,
  high `opus`.

## 1. Detect

- `python3 <hf>/scripts/config.py show`: the current `gateways`, `profiles`
  and `tiers`.
- `python3 <hf>/scripts/config.py profiles`: each profile's gateway and model.

Nothing else can be detected: gateway addresses and model ids come from the
person. Never ask for, read, print or store a token value; a gateway holds
only the name of the environment variable that carries it.

## 2. Show and ask once

Show one table: each tier, its profiles in order, and each profile's gateway
and model. Then ask with AskUserQuestion:

- Keep the tiers as they are (current)
- Add a gateway or a model
- Change a tier

## 3. Add a gateway or a model

Only when the person asked for it. Ask for:

- **Gateway**: a name, the kind (`anthropic` or `anthropic-compatible`), the
  base URL, the auth (`bearer` or `x-api-key`), and the token variable's
  name.
- **Models** on it: an alias, the model id and the context size in tokens.
- **Profile** for each model the person wants to use: a name, the gateway,
  the model, and for an `anthropic-compatible` gateway the model for each
  role alias (`opus`, `sonnet`, `haiku`). Claude Code maps a subagent's
  `model: opus` to that role model, so a subagent stays on the same gateway.

Then go to step 4 so the new profile joins a tier.

## 4. Change a tier

For each tier the person picks, ask for its profiles in order. Offer only
profiles that exist. Offer `fable`, or a model outside the harness's own,
only when the person names it.

## 5. Validate and write

Build the person's settings as they should be in effect (the `show` output
with the changes), as one JSON object in a scratch file:

```bash
python3 <hf>/scripts/config.py save user --dry-run < <file>
```

On a non-zero exit, fix the printed problems with the person and run it
again. On exit 0, `written` is what will be stored: only what differs from
the standard. Then run it without `--dry-run`.

## 6. Confirm

Show the tier table again and one example:
`python3 <hf>/scripts/config.py tier --difficulty mid --role reviewer`.
Tell the person:

- Tasks started from now use the new tiers; agents already running keep
  their profile.
- A gateway's token variable must be set on every machine that runs that
  gateway's agents; `launch.py` exits with 4 where it is missing.
