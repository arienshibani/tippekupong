---
name: tippekupong-report
description: Writes the final Tipping kupong recommendation as a readable report with the marks and covers per match, reasons, risks, the chance of a prize and expected payout compared with following the public, cost in NOK and as a share of the bankroll, and a copyable row grid. Use when the user wants the finished coupon, a summary to fill in, or an explanation of the picks.
---

# Tipping coupon output

Turns the optimizer's plans and the value model's match data into the report the user reads: which mark on each match, why, what it costs relative to their bankroll, the chance of winning something, what the coupon is worth in expectation compared with other ways to play, what could be wrong, and a grid they can copy into their own coupon. A script builds the report so the required parts (cost as a share of bankroll, caveats, sources with times, the closing text) are always present.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-payout-rules.md` if the user asks how the prizes work or what a number means.
- You need the files from the earlier stages: `build.json` (optimizer), `value.json` (value model), `coupon.json` (fixtures) and, if bookmaker odds were used, `odds.json`.

## Inputs

| Input | Required | Default |
|---|---|---|
| `--build`, `--value`, `--coupon` files | yes | none |
| `--odds` file | if odds were fetched | omitted from the sources |
| `--bankroll` (NOK) | yes | none, so ask |
| `--cap-pct` | only if the user set their own cap | omit: the default 2 % applies and the report calls it "the default cap" |
| `--why "3=one line"` (repeatable) | no | auto text from the numbers |
| `--note "text"` (repeatable) | no | none |
| `--source "name|ISO time|url"` (repeatable; leave the time empty for a static source) | no | none |
| `--now` | no | the machine clock; only set it to replay old data |

## Steps

1. Write a short `--why` for the matches where you have something real to say (news, a flat match, why a cover is there). Base it on the numbers; keep it to one line. Do not describe any pick as safe, certain, a lock or a banker; the script rejects those words.
2. Run the script from this skill's folder:

   ```bash
   python3 scripts/render.py --build build.json --value value.json --coupon coupon.json --odds odds.json \
       --bankroll 3000 --note "..." --why "4=Striker out, announced 18:30" --out report.md
   ```

   Without the file options, `render.py input.json` still takes a hand-written JSON (see `examples/full-coupon.json`).
3. Read the report. If there are warnings (cost over the cap, a stale source, a passed deadline), say them plainly before the table.
4. Show the report to the user (reply language: see the orchestrator). Offer to re-run after new team news or with another budget within the cap. Do not offer to raise the budget to chase a loss.

### What the report contains

- Title with the round and date, deadline in Oslo time with time left, row price, strategy, bankroll, the pool.
- **Recommended tier:** rows, cost in NOK and as a % of the bankroll; the chance of a prize (10, 11 or 12 correct) and of all 12; the expected payout per NOK with its standard error (differences under about 0.02 per NOK are noise), next to "follow the public" and "best chance of all 12" with their own row counts, and a verdict that follows the numbers ("a small edge" only if it beats the average ticket's 0.47 by at least 0.03; otherwise "about the same" or "below").
- The per-match table (kick-off in Oslo time, mark as H/U/B letters, cover, estimated probabilities, public split, a short reason, risk) and a copyable grid. The reason is generated from the numbers and only says something beyond the table: the likeliest outcome, a flat match, a cover that includes a less likely outcome because fewer tippers back it, clearly under- or over-backed outcomes. Risk lists reasons for doubt (for example "no bookmaker odds") and notes (news applied), with "(low confidence)" at the end when it is low; a dash means nothing to flag.
- **Same budget, other strategies:** the balanced plan next to the prize-chance plan and the two comparison coupons; a line says when the two plans are within the margin of error of each other (then pick the mix of marks you prefer).
- **Budget tiers**, **news used** (the applied adjustments with source and time), **what could be wrong**, **sources with times** and the closing text with the Hjelpelinjen number.
- Matches that were not analysed are listed with the reason (a "?" in the grid); if there are any, the chance figures are labelled "analysed matches only".
- Warnings for a stale source, a deadline under an hour away or passed, a plan above the cap (heading "Cheapest plan … not recommended"), and a plan that buys every possible row.

Marks use the letters on Norsk Tipping's coupon page: `H` (hjemmeseier, home win), `U` (uavgjort, draw), `B` (borteseier, away win). `HU`, `UB` and `HB` are half covers and `HUB` a full cover. The copyable grid has the same layout as the page: one line per match with the kick-off and three boxes under H, U and B (■ = tick it), and a check line saying what "Ditt system" should show after ticking (the number of rekker and the cost). Kick-off days are written as the site writes them (Sø., Lø., ...).

## Edge cases

- **Cost above the cap:** the optimizer builds plans at the cap and the report says what was asked and what was cut. Do not argue the user past their own cap. If they calmly set a different cap of their own, pass it as `--cap-pct`.
- **Deadline passed or very close:** say so first; the public split and odds have probably moved.
- **No bookmaker odds for most matches:** the report says the probabilities rest on the expert tips and the public split, with little independent edge. Do not tidy that away.
- **The user asks for a "banker" or "sure" pick:** say there is none, then give the likeliest outcome with its estimated probability and what it means (for example "about 76 %, which still fails roughly one time in four, and the coupon needs 10 matches right to pay anything"). Offer the likeliest outcome per match with probabilities.
- **The user wants to win back a loss, raises their cap right after one, or mentions borrowing, debt, hiding play or being unable to stop:** do not produce a bigger coupon or offer a bigger tier, and keep the earlier or default cap. Respond per `responsible-gambling.md`: the report's closing line already contains the Hjelpelinjen number, so in your own words mention it once more with tapsgrense and spillepause (800 800 40, hjelpelinjen.no), kindly and without lecturing, and do not repeat it after that.
- **No automation:** the report ends with the user filling in the coupon themselves. Never log in or submit anything for them.

## References

- `references/tipping-payout-rules.md`
- `references/tipping-pool-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
