---
name: oddsen-tipping-value-model
description: Adjusts fair match probabilities for team news (injuries, suspensions, rotation, weather) within strict caps, then compares them with the public split to show which outcomes are under- or over-backed on a Tipping kupong. Use after de-vigging odds, when the user mentions team news, lineups, "folkets fordeling", or wants value ratios before gardering.
---

# Tipping value model

Sits between the probability engine and the coupon optimizer. It takes each match's fair probabilities (market consensus), applies a small number of justified, sourced adjustments for news the market may not have priced in, and compares the result with the public split. The output says, per outcome, how likely it is and how crowded it is. In a pool, an outcome that is likelier than the crowd thinks is the useful kind of edge.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-pool-math.md` for `value_ratio = p / q` and why it matters in a pool.
- Fair probabilities come from `oddsen-tipping-probability-engine` (or the user). The public split comes from the coupon page or the user; if you estimated it, say so.

## Inputs

| Input | Required | Default |
|---|---|---|
| Per match: `p_fair` (H/U/B, sums to 1), from the engine, with its source and time | yes | none |
| Per match: public split `q` (H/U/B), observed or estimated, with source and time | no | none; value ratios are then missing and confidence drops |
| Proposed adjustments, each `{outcome, delta_pp, reason, source, source_time, status}` | no | none (probabilities are passed through unchanged) |
| `user_approved: true` on a match to allow adjustments above the caps | no | false |

## Steps

1. Collect `p_fair` and `q` for every match. Carry over the engine's `confidence` and `spread_top_outcome`.
2. Gather team news only from sources you can cite. For each piece, decide whether to propose an adjustment. Use this test:
   - **Is it new to the market?** Odds already reflect widely known news (an injury announced days ago, a long-term suspension). Adjusting for it again double counts, so set `market_likely_priced_in: true` or leave it out. Late lineup news, rotation signals and local conditions are the cases where an adjustment can make sense.
   - **Is it confirmed?** An official announcement is `confirmed`. A rumour, a "doubtful" tag or a journalist's guess is `unconfirmed`: the script records it as a risk flag and does **not** change any number.
   - **How big?** Small. As a guide: a key starter out, 2 to 3 pp; a rotated-heavily side, 2 to 4 pp; weather, 0 to 1 pp. Shift probability between the affected side and the opposing outcome(s) so the change is balanced. Every adjustment needs a reason, a source and a time.
3. Build the JSON (see `examples/three-matches.json`) and run:

   ```bash
   python3 scripts/adjust.py input.json --text     # readable
   python3 scripts/adjust.py input.json            # JSON, for further use
   ```

4. Read the result. Report what was applied, what was not applied and why, any capped adjustments, and the confidence level per match.
5. To build a coupon, pass `optimizer_matches` from the JSON (which includes `p`, `q` and `q_estimated`) to `oddsen-tipping-coupon-optimizer`.

### What the script does

- Applies only adjustments that have an outcome, a number, a reason and a source, are `confirmed`, and are not marked as already priced in. Everything else is listed under `rejected` with the reason.
- Enforces caps: at most 5 pp net per outcome and 8 pp in total (sum of absolute changes) per match. Larger requests are scaled down and flagged; they apply in full only if the user explicitly approves that match (`user_approved: true`).
- Computes `p_est = normalise(p_fair + deltas)`, flooring each outcome at 1 %. Because the result is renormalised, an unbalanced adjustment also moves the other outcomes a little. `change_pp` shows the actual net change.
- Computes `value_ratio = p_est / q`, flooring `q` at 2 % so a tiny public share cannot blow up a ratio. A ratio above 1 means under-backed relative to its probability, below 1 means over-backed.
- Rates confidence `high`, `medium` or `low` by counting reasons for doubt: low engine confidence, missing or estimated split, three or more adjustments, unconfirmed news, capped adjustments.

## Output format

| # | Match | p_fair (H/U/B) | p_est (H/U/B) | Public (H/U/B) | Value ratio (H/U/B) | Confidence |
|---|---|---|---|---|---|---|

Under the table, per match with changes or flags:

- **Applied:** outcome, size, reason, source and time.
- **Not applied:** what and why (unconfirmed, priced in, missing source, capped).
- **Risk flags:** anything the user should check before kick-off (for example "lineup due 90 minutes before the deadline").

State whether `q` is observed or estimated next to every ratio. End with: "Estimated, not certain. News adjustments are judgement calls; the market consensus is the stronger signal."

## Edge cases

- **No news:** pass probabilities through unchanged. That is a fine result.
- **Many adjustments in one match:** a sign of overfitting a story. Keep the strongest one or two and say the rest are noise.
- **Conflicting reports:** treat as unconfirmed.
- **Adjustment larger than the caps:** do not stretch the caps yourself. Ask the user, and set `user_approved: true` only after a clear yes.
- **No public split:** value ratios are missing; the optimizer will then optimise for hit probability only. Say so.
- **Estimated split:** keep the "estimated" label with every crowding number.
- **Match with no market (`p_fair` missing):** excluded, reported, never guessed.
- **Late news after the run:** probabilities are only as fresh as their sources; tell the user to re-run if the lineups change before the deadline.

## References

- `references/tipping-pool-math.md`
- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
