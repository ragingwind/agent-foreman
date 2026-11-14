# Part: models

Gateways, profiles and the low, mid and high tiers. Saved at the person's
level.

## How the tiers are used

- A task's difficulty (low, mid, high) gives the lead's tier; the lead
  takes the tier's first profile. The pair takes the same tier, the red team
  and QA one tier above, at most high.
- An agent that checks the work never runs on the lead's profile, and never
  on a lower tier: it takes its tier and the higher ones, the lead's profile
  left out. So every difficulty needs a profile other than its lead's at or
  above the checking roles' tier; `config.py check` names a difficulty that
  has none. High needs two profiles.
- A tier is an ordered list of profiles. The first is used; on a usage limit
  or a gateway error the next one is.
- Each agent is its own process with its own profile, so one task can mix
  gateways: a lead on a token-factory model, a reviewer on Anthropic opus.
- With no settings, the standard tiers apply: low `haiku`, mid `sonnet`,
  high `opus` then `sonnet`. At high the lead runs on opus and the agents
  that check it on sonnet; name a stronger second model when there is one.

## 1. Detect

- `python3 <skill>/scripts/config.py show`: the current `gateways`, `profiles`
  and `tiers`.
- `python3 <skill>/scripts/config.py profiles`: each profile's gateway and model.

Nothing else can be detected: gateway addresses and model ids come from the
person.

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

Then change a tier so the new profile is used.

## 4. Change a tier

For each tier the person picks, ask for its profiles in order. Offer only
profiles that exist. Offer `fable`, or a model outside the harness's own,
only when the person names it.

## 5. Save

At the person's level (`SKILL.md` "Save"). Then show the tier table again
and one example: `python3 <skill>/scripts/config.py tier --difficulty mid --role
redteam`. Tell the person that a gateway's token variable must be set
on every machine that runs its agents; with a project saved, the project
part's machine check shows where it is missing.
