---
name: tippekupong-news
description: Adjusts fair match probabilities for team news (injuries, suspensions, rotation, weather) within strict caps, then compares them with the public split to show which outcomes are under- or over-backed on a Tipping kupong. Use after de-vigging odds, when the user mentions team news, lineups, "folkets fordeling", or wants value ratios before gardering.
---

# Tipping value model

Sits between the probability engine and the coupon optimizer. It takes each match's fair probabilities (market consensus), applies a small number of justified, sourced adjustments for news the market may not have priced in, and compares the result with the public split. The output says, per outcome, how likely it is and how crowded it is. In a pool, an outcome that is likelier than the crowd thinks is the useful kind of edge.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/tipping-pool-math.md` for `value_ratio = p / q` and why it matters in a pool.
- Fair probabilities come from `tippekupong-probabilities` (or the user). The public split comes from the coupon page or the user; if you estimated it, say so.

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
   - **Is it new to the market?** Odds already reflect widely known news, so adjusting for it again double counts. Give each piece of news its `source_time` (an ISO time with a zone, when it was announced) and keep the engine's `books` (with the times the odds were taken) on the match; the script then decides:
     - announced **at least 15 minutes before the earliest odds**: priced in, not applied;
     - announced **after the latest odds**: new to the market, applied (and noted as "only N min old" if it is under 30 minutes before the run, since the market may not have fully moved);
     - **anywhere in between**: too close to tell, not applied, and flagged.
     - **no odds on this match** (most Eliteserien and OBOS-ligaen matches): there is nothing to compare the news time with, so it is applied, but if the public split was read **after** the news the script flags that the split may already reflect it (the adjustment may double count). Say so to the user.
     Set `market_likely_priced_in` yourself only to override this (true = never apply; false = apply regardless), and say why. Without times the script does not guess: then use your judgement, ask the user, and say what you assumed.
   - **Is it confirmed?** An official announcement is `confirmed`. A rumour, a "doubtful" tag or a journalist's guess is `unconfirmed`: the script records it as a risk flag and does **not** change any number.
   - **How big?** Small. As a guide: a key starter out, 2 to 3 pp; a rotated-heavily side, 2 to 4 pp; weather, 0 to 1 pp. Shift probability between the affected side and the opposing outcome(s) so the change is balanced: give both sides as separate adjustments (affected outcome down, opposing outcome up). If the opposing side has two outcomes (draw and away), put the whole shift on the more affected one or split it in proportion to their probabilities. One news item split over several outcomes counts as one item for confidence, and the report merges a mirrored pair into one line. Every applied adjustment needs a size (`delta_pp`), a reason, a source and a time. Unconfirmed or priced-in items need no size: do not invent one for news you do not intend to apply.
3. Run the script on the blend output. Put the news in a small file keyed by slot number (see `examples/three-matches.json` for the adjustment fields):

   ```bash
   python3 scripts/adjust.py blend.json --news news.json > value.json     # JSON for the next stage
   python3 scripts/adjust.py blend.json --news news.json --text            # readable
   ```

   `news.json` looks like `{"4": [{"outcome": "H", "delta_pp": -3, "reason": "...", "source": "...", "source_time": "2026-10-10T18:30:00+02:00"}, {"outcome": "B", "delta_pp": 3, ...}]}`. Without news, run it without `--news`. `blend.json` already carries `p_fair`, `q`, `confidence`, `confidence_reasons` and `notes`, which are passed through (low confidence from a missing bookmaker price is reported with its own reason). The older input shape (engine matches plus `q` and `adjustments` written by hand) still works.

4. Read the result. Report what was applied, what was not applied and why, any capped adjustments, and the confidence level per match.
5. To build a coupon, pass `optimizer_matches` from the JSON (which includes `p`, `q` and `q_estimated`) to `tippekupong-optimizer`.

### What the script does

- Applies only adjustments that have an outcome, a number, a reason and a source, are `confirmed`, and are not marked as already priced in. Everything else is listed under `rejected` with the reason, and the final report shows the priced-in and incomplete ones; unconfirmed items become a single risk flag per match.
- Flags an adjustment smaller than 0.5 pp as a probable unit mistake (`delta_pp` is percentage points: 3 means 3 pp, not 0.03).
- Carries the dropped-quote reasons of a match with no market through to `excluded`, so the report can say why it was left out.
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
