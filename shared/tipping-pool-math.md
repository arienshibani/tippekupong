# Tipping pool math

Math for Norsk Tipping's pool games (Tipping: 1X2 rows on a fixed list of matches). Read `odds-math.md` first for implied probability, margin and de-vig.

**Rules marked TO VERIFY must be checked against Norsk Tipping's current game rules before a skill states them as fact:** number of matches per coupon, price per row, payout tiers (all correct vs. one or two wrong), whether payout is a fixed share of a pool, jackpot/carry-over rules.

## Fixed odds vs. pool

| | Fixed odds (Oddsen) | Pool (Tipping) |
|---|---|---|
| Payout | `stake × odds`, known when you bet | A share of the pool split among winning rows, known only after the matches |
| Edge comes from | Price above fair odds | Outcomes the public under-backs relative to true probability |
| Staking | Fractional Kelly applies | Fixed price per row, so Kelly does not apply. Budget = rows × row price |
| Margin | Bookmaker overround | Pool takeout (the share not paid out) (TO VERIFY) |

Consequence: a pool is a negative-EV game on average because of the takeout. A coupon can only be *less bad* or, rarely, slightly positive when the pool is boosted (jackpot/carry-over) and the picks are well under-owned. Say this plainly in every output.

## Quantities

For each match `i` and outcome `k` in `{H, U, B}`:

- `p[i][k]`: estimated true probability (de-vigged market consensus, optionally adjusted). Sums to 1 per match.
- `q[i][k]`: public share, the percentage of the crowd tipping that outcome ("folkets fordeling"). Sums to 1 per match.
- `value_ratio[i][k] = p[i][k] / q[i][k]`. Above 1 means under-owned (good for a pool), below 1 means over-owned.

For a **row** `r` that picks outcome `k_i` in each match:

- `P(r) = Π p[i][k_i]`: probability the row is fully correct.
- `Q(r) = Π q[i][k_i]`: expected share of the crowd holding the same row. **Independence assumption**: real tippers correlate their picks (they pile on favourites together), so this understates how crowded popular rows are. Flag it.
- `row_value_index(r) = P(r) / Q(r) = Π value_ratio[i][k_i]`.

Expected payout of a fully correct row is roughly proportional to `pool_after_takeout / (N_players × Q(r))`, where `N_players` is the number of rows played. So at equal `P(r)`, the lower-`Q` row pays more when it hits. `N_players` and pool size are often unknown; when they are, say so and report only the relative `row_value_index`, not an absolute EV.

## Gardering (covers)

A cover marks more than one outcome in a match.

- Single mark: 1 outcome. Half cover (halvgardering): 2 outcomes (1X, X2 or 12). Full cover (helgardering): all 3.
- Rows = Π (outcomes marked in match `i`). Cost = rows × row price.
- Probability that the coupon contains a fully correct row: `P_cover = Π (Σ p[i][k] over marked k)`.
- Marginal gain of widening match `i`: `ΔP / Δrows`. Spend the budget where this is highest. Covers are best placed on matches where the top outcome is least dominant (the most uncertain matches), not on the ones where the favourite is already ~70 %.
- Tension: the outcome you add as a cover is usually the less likely one, but often the more under-owned one. That's why `value_ratio` is part of the choice, not just `p`.

## Worked example (illustrative numbers, not real matches)

Three matches. `p` is estimated true probability, `q` is public share.

| Match | p (H/U/B) | q (H/U/B) | value_ratio (H/U/B) |
|---|---|---|---|
| 1 | .55 / .25 / .20 | .70 / .18 / .12 | 0.79 / 1.39 / 1.67 |
| 2 | .40 / .30 / .30 | .45 / .27 / .28 | 0.89 / 1.11 / 1.07 |
| 3 | .30 / .28 / .42 | .20 / .20 / .60 | 1.50 / 1.40 / 0.70 |

Single rows:

| Row | P(r) | Q(r) | row_value_index |
|---|---|---|---|
| H, H, H | 0.0660 | 0.063 | 1.05 |
| H, H, B (public's favourite pick in match 3) | 0.0924 | 0.189 | 0.49 |
| B, H, H | 0.0240 | 0.0108 | 2.22 |

`H,H,B` is the most likely single row but the most crowded: if it hits, you share the pool with many. `B,H,H` is unlikely but rarely shared.

Covers, starting from `H,H,H` (1 row, `P_cover` 0.066):

| Change | Rows | P_cover | ΔP per extra row |
|---|---|---|---|
| Match 3 → H+B | 2 | 0.1584 | +0.0924 |
| Match 1 → H+U | 2 | 0.0960 | +0.0300 |

With a one-extra-row budget, the cover goes on match 3 (the least dominant match), not match 1.

Reproduce: `P_cover = Π (Σ p over marked outcomes)`, e.g. `(.55) × (.40) × (.30+.42) = 0.1584`.

## What to state in outputs

- Which `p` source and de-vig method; which `q` source, or that `q` is an odds-implied estimate.
- That `Q(r)` assumes independence.
- Cost in NOK and as a % of the user's bankroll.
- That the expected result of a pool coupon is a loss, and that `P(all correct)` is small even for a good coupon.
