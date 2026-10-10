---
name: oddsen-example-skill
description: One or two sentences on WHEN Claude should use this skill, with words a user would type (e.g. "value bet", "Oddsen", "odds", "kupong"). Max 1024 characters.
---

# <Skill title>

<One paragraph: what this skill does and what the user gets at the end.>

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/odds-math.md` for formulas. Don't re-derive them here.
- Confirm the inputs below with the user if they're missing.

## Inputs

| Input | Required | Default |
|---|---|---|
| Bankroll (NOK) | yes, if recommending stakes | none, so ask |
| ... | | |

## Steps

1. ...
2. ...
3. ...

## Output format

<Exactly what to return: a table, a short verdict, a CSV row. Include an example.>

| Match | Market | Oddsen odds | Fair odds | Edge | Stake (NOK / % bankroll) | Source & time |
|---|---|---|---|---|---|---|

## Edge cases

- Odds older than <N> minutes: re-fetch or flag as stale.
- Market suspended or missing on Oddsen: say so; don't guess.
- ...

## References

- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
