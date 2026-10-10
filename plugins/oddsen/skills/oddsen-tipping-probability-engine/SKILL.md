---
name: oddsen-tipping-probability-engine
description: Turns 1X2 bookmaker odds from several books into fair (margin-free) probabilities per match, with a weighted consensus and a disagreement measure, and blends them with Norsk Tipping's expert tips and the public split into one probability per Tipping match. Use when the user has odds for a kupong or a match and wants true probabilities, de-vigging, margin, or the input for building a Tipping coupon.
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

Times are ISO times **with a zone**: `Z` for UTC or an offset such as `+02:00` for Oslo summer time (`+01:00` in winter). A time without a zone is dropped with a reason, never guessed. The script uses the machine's clock for "now"; the optional top-level `"now"` is only for replaying old data. A quote's age is measured against it.

## Steps

1. Collect quotes and write the JSON the script expects (see `examples/two-matches.json`). Odds are decimal and must be above 1.00; Norwegian decimal commas ("2,10") are accepted. Do not convert fractional or American odds silently: convert them and say so.
2. Run the script:

   ```bash
   python3 scripts/engine.py input.json --text     # readable
   python3 scripts/engine.py input.json            # JSON, for further use
   ```

3. Read the result before presenting it. Look for `low` confidence, dropped quotes, and `no_market` matches. Matches with no usable quote come back in `excluded` together with the reasons their quotes were dropped (for example "stale (8.0 h old)"); pass these on, because the final report shows them.
4. Present the output format below. State the de-vig method and the run time.
5. To build a coupon, pass `optimizer_matches` from the JSON to `oddsen-tipping-coupon-optimizer`, adding the public split `q` per match if you have it.

### What the script does

- **Margin per book:** `Σ(1/odds) − 1`.
- **De-vig each book** with the chosen method. If a method cannot be applied (additive would give a negative probability; a market with no positive margin) it falls back to multiplicative and says so.
  - Multiplicative spreads the margin evenly and is the default. Power and Shin move probability toward the favourite and away from long shots, which matches the favourite-longshot bias seen in practice. Use `power` for the whole run if any match has a favourite below odds 1.30 (for example 1.25 gives about 79 % with power against 76 % with multiplicative), and say which method you used.
- **Drops quotes** that are incomplete, have odds ≤ 1, have an unreadable timestamp, or are older than the max age at run time. Each drop is listed with a reason.
- **Consensus** is a weighted mean of the de-vigged probabilities. A quote's weight is `weight / max(margin, 1 %)`, so low-margin (sharper) books count more (a 1 % margin counts about five times a 5 % margin).
- **Spread** is the largest gap between books on the most likely outcome. Confidence is `low` for a single book, a spread above 5 percentage points, or any undated quote.

## Blend with the expert tips and the public split

Most Tipping matches have no free bookmaker odds (Eliteserien, OBOS-ligaen, qualifiers), so the pipeline blends three ingredients into one probability per match:

```bash
python3 scripts/blend.py --coupon coupon.json --engine engine.json --out blend.json --text
```

`coupon.json` comes from `oddsen-tipping-fixtures` (it has each match's `public` and `expert` split) and `engine.json` from running `engine.py` on `odds.json` from `oddsen-tipping-market-odds`. If there are no odds at all, pass an engine file with an empty `matches` list (`{"matches": []}`).

| Situation | Weights |
|---|---|
| Bookmaker consensus from 2 or more books | market 55 %, expert 25 %, public 20 % |
| One bookmaker | market 40 %, expert 30 %, public 30 % |
| No bookmaker odds | expert 50 %, public 50 % |

When the odds are more than 24 hours old the market weight is cut by a quarter first and the weights are then renormalised (so 55 % becomes about 48 %, not 41 %). The blend's `confidence` is `ok` or `low`; the value model turns the number of reasons for doubt into `high`, `medium` or `low`, and the report shows only the reasons, with "(low confidence)" when it is low. These weights are judgement, printed in the output. The evidence behind the ingredients: on 720 finished Tipping matches the expert tips (log-loss 0.9375) and the public split (0.9424) were both well calibrated against 1.0986 for a coin flip, and an even mix scored 0.9353. Bookmaker consensus is the only independent signal, so it counts most when it exists. For matches with no odds there is **little independent edge**: the probability is mostly the crowd's own view. Say so.

The output (`blend.json`) has one entry per match with `p_fair`, `q` (the public split), `confidence` (`ok` only for 2+ books), `confidence_reasons`, `notes`, `weights` and the components. It is already in the shape `oddsen-tipping-value-model` reads.

## Output format

State: method, run time, and the number of quotes used and dropped. The `--text` output already prints one line per match (H/U/B, number of books, spread, confidence) and, under it, each book's margin, weight and the time its odds were taken. Present it as a table if the user wants one:

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
