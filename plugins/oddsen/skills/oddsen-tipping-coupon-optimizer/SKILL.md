---
name: oddsen-tipping-coupon-optimizer
description: Chooses single marks and half/full covers (halvgardering, helgardering) for a Norsk Tipping Tipping pool coupon (tippekupong, 1X2) within a budget, given each match's estimated probabilities and the public split. Use when the user asks to build, garder or optimise a kupong, or asks where to spend extra rows.
---

# Tipping coupon optimizer

Given estimated probabilities (and, ideally, the public split) for each match on a Tipping coupon, this skill picks the marks that give the best chance of a fully correct row for a fixed budget, and shows how crowded the chosen rows are likely to be. It is pool maths, not fixed-odds maths: the price per row is fixed, so there is no Kelly staking here, and the edge (if any) comes from outcomes the public under-backs.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-pool-math.md` for the formulas and a worked example. Don't re-derive them here.
- Read `references/odds-math.md` if you need to turn bookmaker odds into probabilities (de-vig) first.
- Pool rules are **TO VERIFY** on Norsk Tipping's site (matches per coupon, row price, payout tiers). Ask the user for the row price if you cannot read it from a source you can cite; never assume it.

## Inputs

| Input | Required | Default |
|---|---|---|
| Matches with estimated `p` for H/U/B (sums to 1) and a source and timestamp | yes | none, so ask or compute from odds |
| Public split `q` per match (H/U/B), with source and timestamp | no | none; value ratios are then neutral and a warning is shown |
| Row price (NOK) | yes | none, so ask |
| Budget (NOK) for the coupon | yes | none, so ask |
| Bankroll (NOK) | yes, to show cost as a share | none, so ask |
| Risk: `safe`, `balanced`, `contrarian` | no | `balanced` |
| Optional higher budget for a "max" tier | no | none |

If the user only has bookmaker odds, de-vig them first (say which method) and use the result as `p`. If the user pastes a public split, use it as `q` and say it is observed. If you had to estimate `q` from odds, mark `q_estimated: true`.

## Steps

1. Collect the inputs above. Keep a source and timestamp for every probability and for `q`. If anything is older than a few hours before the deadline, say so.
2. Build the JSON the script expects (see `examples/three-match.json`). Probabilities must sum to 1 (±0.01). Do not invent numbers: a match without a usable `p` is left out and reported.
3. Run the script:

   ```bash
   python3 scripts/optimize.py input.json --text     # readable
   python3 scripts/optimize.py input.json            # JSON, for further use
   ```

   It prints one plan per budget tier (`cheap` ≈ half the budget, `base`, and `max` if a higher budget was given). Tiers that would be identical are merged.
4. Check the cost of each plan as a share of the bankroll. If the `base` plan is above 2 % of the bankroll (the default cap in `responsible-gambling.md`), say so and recommend the cheaper tier unless the user has set their own cap.
5. Present the result using the output format below, then the caveats.

### What the script does

- Ranks outcomes in each match by `score = (1 − λ)·p + λ·p·(p/q)` with λ = 0 / 0.5 / 1 for safe / balanced / contrarian. A cover of size n marks the top n.
- Finds the cover sizes (1, 2 or 3 per match) that maximise `P = Π (Σ p over marked outcomes)` subject to rows ≤ budget ÷ row price. The search is exact, not greedy.
- Reports, per plan: rows, cost, `P(a fully correct row)` and "about 1 in N", and two crowding measures:
  - `mean_row_value_index`: the average of `Π(p/q)` over your rows. Above 1 means your rows are less crowded than their probability suggests.
  - `win_value_index`: the same, weighted toward the rows that are most likely to hit.
- Floors `q` at 2 % per outcome so a tiny public share cannot blow up a ratio.

## Output format

Start with the assumptions, then one table per tier, then the caveats.

**Assumptions:** probabilities from `<source, method>` at `<time>`; public split `<observed | estimated>` from `<source>` at `<time>`; row price `<x> NOK`; risk `<mode>`.

| # | Match | Mark | Cover | p covered | p (H/U/B) | Public (H/U/B) | Value ratio (H/U/B) |
|---|---|---|---|---|---|---|---|

Then, for each tier:

- Rows, cost in NOK **and as % of bankroll**, `P(fully correct row)` and "about 1 in N".
- Crowding: `mean_row_value_index` and `win_value_index`, with a one-line reading.
- A copyable grid, one mark per line (`1`, `X`, `2`, `1X`, `X2`, `12`, `1X2`).

Close with: "Estimated, not certain. A pool coupon has a takeout, so on average it loses money; even a well-built coupon is unlikely to hit."

## Edge cases

- **Budget below one row:** the script errors; tell the user, don't round up.
- **No public split:** value ratios default to 1, so the plan optimises only for hit probability. Say that the crowding numbers are missing.
- **Public split estimated:** keep the "estimated" label next to every crowding number.
- **Very flat match (all outcomes ≈ 1/3):** the cover goes there first; say it is a coin-flip match rather than implying insight.
- **Match with no usable probability:** exclude it and say so; don't fill a guess.
- **Independence:** the crowding numbers assume tippers pick matches independently. Real tippers correlate (they pile onto the same favourites), so popular rows are probably more crowded than shown.
- **Budget above the 2 % cap, or the user asks to raise the budget after a loss:** don't help escalate. Restate the cap and offer the cheaper tier (see `responsible-gambling.md`).
- **Output is a recommendation:** the user fills in the coupon themselves. Never log in or place anything.

## References

- `references/tipping-pool-math.md`
- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
