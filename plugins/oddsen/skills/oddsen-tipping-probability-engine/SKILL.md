---
name: oddsen-tipping-probability-engine
description: Turns 1X2 bookmaker odds from several books into fair (margin-free) probabilities per match, with a weighted consensus and a disagreement measure. Use when the user has odds for a kupong or a match and wants true probabilities, de-vigging, margin, or the input for building a Tipping coupon.
---

# Tipping probability engine

Takes decimal 1X2 (H/U/B: home win / draw / away win) odds from one or more bookmakers for each match, removes each book's margin, and combines the books into one fair probability per outcome. It also says how much the books disagree and drops stale or broken quotes. The result feeds `oddsen-tipping-coupon-optimizer`.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/odds-math.md` for implied probability, margin and the de-vig methods. Don't re-derive them here.
- Odds come from the user (pasted, screenshot) or from a public page you can cite. Never invent or "fill in" odds.

## Inputs

| Input | Required | Default |
|---|---|---|
| Per match: label and slot (position on the coupon) | yes | none |
| Per match: one or more quotes `{book, odds{H,U,B}, fetched_at}` | yes | none; a match with no usable quote is reported, not guessed |
| De-vig method: `multiplicative`, `additive`, `power`, `shin` | no | `multiplicative` |
| Max quote age in hours | no | 6 |
| Optional per-quote `weight` (e.g. 2 for a book you trust more) | no | 1 |

Every quote needs a source and a timestamp. If the user pasted odds with no time, ask when they were taken; if unknown, the script keeps the quote but marks it "undated" and lowers confidence.

## Steps

1. Collect quotes and write the JSON the script expects (see `examples/two-matches.json`). Odds are decimal and must be above 1.00. Do not convert fractional or American odds silently: convert them and say so.
2. Run the script:

   ```bash
   python3 scripts/engine.py input.json --text     # readable
   python3 scripts/engine.py input.json            # JSON, for further use
   ```

3. Read the result before presenting it. Look for `low` confidence, dropped quotes, and `no_market` matches.
4. Present the output format below. State the de-vig method and the run time.
5. To build a coupon, pass `optimizer_matches` from the JSON to `oddsen-tipping-coupon-optimizer`, adding the public split `q` per match if you have it.

### What the script does

- **Margin per book:** `Σ(1/odds) − 1`.
- **De-vig each book** with the chosen method. If a method cannot be applied (additive would give a negative probability; a market with no positive margin) it falls back to multiplicative and says so.
  - Multiplicative spreads the margin evenly. Power and Shin move probability toward the favourite and away from long shots, which matches the favourite-longshot bias seen in practice. Use them when a match has a heavy favourite.
- **Drops quotes** that are incomplete, have odds ≤ 1, have an unreadable timestamp, or are older than the max age at run time. Each drop is listed with a reason.
- **Consensus** is a weighted mean of the de-vigged probabilities. A quote's weight is `weight / max(margin, 1 %)²`, so low-margin (sharper) books count more.
- **Spread** is the largest gap between books on the most likely outcome. Confidence is `low` for a single book, a spread above 5 percentage points, or any undated quote.

## Output format

State: method, run time, and the number of quotes used and dropped.

| # | Match | H | U | B | Books | Spread | Confidence | Sources and time |
|---|---|---|---|---|---|---|---|---|

Then list, per match, anything dropped and why, and any match with no usable market ("not on the coupon plan until odds are available").

Close with a one-line reminder: these are estimated fair probabilities from market prices, not certainties, and they are only as fresh as the quotes behind them.

## Edge cases

- **One book only:** fine, but say it is a single-book estimate. The shown margin is that book's, not a market-wide one.
- **Books disagree strongly:** show the spread and the individual books; don't average it away silently. Suggest checking for stale quotes or a team-news difference.
- **Match with no usable odds:** exclude it and say so. Do not copy another match's numbers or invent a baseline.
- **Odds look like a mistake** (e.g. all three outcomes near 1.50, or a negative margin): the script flags a missing margin; ask the user to re-check the source.
- **Late news** (injuries, rotation) can make any quote stale in minutes. Odds taken a day before kick-off are a weaker basis than odds taken close to it.
- **Extra time or void rules** are not modelled; 1X2 here means the 90-minute result.

## References

- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
