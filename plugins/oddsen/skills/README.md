# Skills

One folder per skill: `<skill-name>/SKILL.md`, plus optional `references/`, `scripts/` and `examples/`.

## Tipping (Norsk Tipping's pool game)

Start with `oddsen-tipping-coupon`: you say "bygg kupongen for søndag" with a budget and a bankroll, and it fetches the open round, estimates every match, builds the marks and covers, and explains the result. Install all of these together; the orchestrator runs the others.

| Skill | What it does |
|---|---|
| `oddsen-tipping-coupon` | The orchestrator: fetches, estimates, builds and reports. |
| `oddsen-tipping-fixtures` | Reads the open coupons from Norsk Tipping's public site data: matches, deadline, pool, row price, public split, expert tips. |
| `oddsen-tipping-market-odds` | Bookmaker odds for the matches that have them (football-data.co.uk, free). |
| `oddsen-tipping-probability-engine` | De-vigs the odds and blends them with the expert tips and the public split. |
| `oddsen-tipping-value-model` | Small, sourced team-news adjustments, with a check against what the market already knows. |
| `oddsen-tipping-coupon-optimizer` | Builds the coupon for the best expected payout across the 12, 11 and 10-correct prizes. |
| `oddsen-tipping-coupon-output` | The report: marks, reasons, risks, chance of a prize, expected payout vs following the public, cost as a share of the bankroll. |

To add a skill, start from [templates/SKILL.template.md](../../../templates/SKILL.template.md).
