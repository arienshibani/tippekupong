---
name: oddsen-tipping-coupon-output
description: Writes the final Tipping kupong recommendation as a readable report with marks, half/full covers, reasoning, risks, cost in NOK and as a share of the bankroll, and a copyable row grid. Use when the user wants the finished coupon, a summary to fill in, or an explanation of the picks.
---

# Tipping coupon output

Turns the optimizer's plans and the value model's match data into the report the user actually reads: which mark on each match, why, how much it costs relative to their bankroll, what could be wrong, and a grid they can copy into their own coupon. A script builds the report so the required parts (cost as a share of bankroll, caveats, sources, closing text) are always present.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-pool-math.md` if the user asks what the numbers mean.
- You need the output of `oddsen-tipping-coupon-optimizer` (all tiers) and of `oddsen-tipping-value-model` (the `matches` and `excluded` lists). If either is missing, run that skill first.

## Inputs

| Input | Required | Default |
|---|---|---|
| Bankroll (NOK) | yes | none, so ask |
| Cap on coupon cost, % of bankroll | no | 2 |
| `optimizer_result` (all tiers) | yes | none |
| Value-model `matches` and `excluded` | yes, for reasons and risks | none |
| Coupon name, deadline (UTC), public coupon URL | no | omitted |
| Sources with names, URLs and fetch times | yes in practice | the report warns if missing |
| `why`: your own one-line reason per match | no | auto text from the numbers |
| `notes`: extra caveats | no | none |

## Steps

1. Collect the inputs. Never invent a source or a time; if a time is unknown, leave it out and the report will say so.
2. Write a short `why` for each match in your own words. Base it on the numbers (probability, public share, news) and keep it to one line. Do not describe any pick as safe, certain, a lock or a banker; the script rejects those words.
3. Build the JSON (see `examples/full-coupon.json`) and run:

   ```bash
   python3 scripts/render.py input.json            # markdown
   python3 scripts/render.py input.json --json     # markdown + warnings + recommended tier
   ```

4. Read the report. If there are warnings (cost over the cap, stale sources, passed deadline), say them plainly before the table.
5. Show the report to the user. Offer to re-run with a different budget tier, risk preference, or after new team news. Do not offer to raise the budget to chase a loss.

### What the script does

- Picks the recommended tier: the most expensive one that fits the cap, or the cheapest with a warning if none does.
- Prints the cost in NOK and as a % of the bankroll for every tier, and marks which tiers fit the cap.
- Builds the per-match table (mark, cover type, estimated probabilities, public split, reason, risk) and a copyable grid.
- Lists matches that had no usable market and reminds the user that the coupon still needs a mark for each, and that a single mark leaves the cost unchanged while a cover multiplies it.
- Adds caveats: independence assumption in the crowding numbers, estimated public splits, low-confidence matches, unconfirmed news, rules to verify.
- Warns when a source is older than the limit (default 6 h), when the deadline is under an hour away or has passed, and when a plan buys every possible row.
- Ends with the fixed closing text: estimated not certain, a pool loses on average, play only what you can afford, never raise the budget to win back a loss, and the Hjelpelinjen number.

## Output format

Present the script's markdown as is. Its layout is:

1. Title, deadline, row price, preference, bankroll.
2. Warnings (if any).
3. **Recommended tier:** rows, cost, % of bankroll, chance of a fully correct row ("about 1 in N"), crowding.
4. Table: `# | Match | Mark | Cover | p (est) 1/X/2 | Public 1/X/2 | Why | Risk`.
5. Copyable grid, then any uncovered matches, then the link to the public coupon page if given.
6. Budget tiers table.
7. What could be wrong; sources with times; closing text.

Marks use the coupon notation: `1` home win, `X` draw, `2` away win; `1X`, `X2`, `12` are half covers and `1X2` a full cover.

## Edge cases

- **Cost above the cap:** the report warns and recommends the cheapest tier. Do not argue the user past their own cap. If they set a different cap, pass it as `cap_pct`.
- **Deadline passed or very close:** say so first; odds and news are probably stale.
- **Estimated public split or low confidence:** keep those labels visible; do not tidy them away.
- **Matches with no market:** report them; never fill in a mark as if it had been analysed.
- **The user asks for a "banker" or "sure" pick:** explain that no pick is certain; offer to show the most likely outcome per match with its estimated probability instead.
- **The user mentions chasing losses, borrowing, or hiding play:** do not produce a bigger coupon. Respond per `responsible-gambling.md`, mention Hjelpelinjen (800 800 40, hjelpelinjen.no) and Norsk Tipping's tapsgrense and spillepause once, without lecturing.
- **No automation:** the report ends with the user filling in the coupon themselves. Never log in or submit anything for them.

## References

- `references/tipping-pool-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
