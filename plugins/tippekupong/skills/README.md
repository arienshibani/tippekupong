# Skills

One folder per skill: `<skill-name>/SKILL.md`, plus optional `references/`, `scripts/` and `examples/`.

## Tipping (Norsk Tipping's pool game)

Start with `tippekupong`: you say "bygg kupongen for søndag" with a budget and a bankroll, and it fetches the open round, estimates every match, builds the marks and covers, and explains the result. Install all of these together; the orchestrator runs the others.

| Skill | What it does |
|---|---|
| `tippekupong` | The orchestrator: fetches, estimates, builds and reports. |
| `tippekupong-fixtures` | Reads the open coupons from Norsk Tipping's public site data: matches, deadline, pool, row price, public split, expert tips. |
| `tippekupong-odds` | Bookmaker odds for the matches that have them (football-data.co.uk, free). |
| `tippekupong-probabilities` | De-vigs the odds and blends them with the expert tips and the public split. |
| `tippekupong-news` | Small, sourced team-news adjustments, with a check against what the market already knows. |
| `tippekupong-optimizer` | Builds the coupon for the best expected payout across the 12, 11 and 10-correct prizes. |
| `tippekupong-report` | The report: marks, reasons, risks, chance of a prize, expected payout vs following the public, cost as a share of the bankroll. |

To add a skill, start from [templates/SKILL.template.md](../../../templates/SKILL.template.md).
