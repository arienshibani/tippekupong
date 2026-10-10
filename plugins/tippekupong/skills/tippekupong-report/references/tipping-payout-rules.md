# Tipping payout rules (as observed)

How Norsk Tipping's Tipping pool (12 football matches, 1X2, full-time game) pays out, reverse-engineered from the public results of **60 finished rounds** (24 May to 9 October 2026) and checked against the live pages. Norsk Tipping's own rules are the authority; this describes what the numbers show. The test `tests/test_build.py` re-checks every figure below against the saved rounds in `tests/fixtures/nt_history_60_rounds.json`.

## The game

- 12 matches, one mark (H, U or B / 1, X or 2) per match per row, **1.00 NOK per row** (read from the API's `product.rowPrice`).
- Three rounds a week: Saturday, Sunday and midweek. Each has its own pool and deadline.
- You can play single rows ("Enkeltrekker") or a system: more than one mark in some matches (halvgardering = 2 marks, helgardering = 3), which buys every combination. Rows = the product of marks per match; cost = rows × 1 NOK.
- A separate half-time game exists; this repo only covers the full-time game.

## Who gets paid

Prizes go to rows with **12, 11 or 10 correct**. The chance of 12 correct on one random row is 1 in 531 441 (3^12).

| Tier | Share of the round's turnover | Typical prize per winner (recent rounds) |
|---|---|---|
| 12 correct | 14.85 % (27 % of the prize money) | about 1 750 kr, from a few hundred to millions |
| 11 correct | 14.85 % (27 %) | about 90 kr |
| 10 correct | 17.05 % (31 %) | about 10 kr |
| Bonus pool | 8.25 % (15 %) | paid out when one tipper is alone with 12 correct (carry-over); not modelled |

The prize money is **55 % of turnover**. Each winner gets the tier's pot divided by the number of winning rows in that tier, **rounded down to a multiple of 5 kr**.

**Cancellation.** If a tier-10 prize would be under **10 kr**, nobody in that tier is paid, and the tier's pot is split equally between the 12 and 11 tiers. In 15 of the 60 rounds the 10-correct tier was cancelled this way; in those rounds the 12 and 11 tiers each got about 23.4 % of turnover.

## Evidence

- Predicted prize per winner equals the actual prize in 60 of 60 rounds (tier 10), 59 of 60 (tier 11) and 46 of 50 (tier 12, rounds with more than one winner). The four tier-12 misses all paid *more* than predicted: bonus-pool carry-overs.
- The tier pots are tightly bounded: tier 10 between 17.047 % and 17.060 % of turnover; tiers 12 and 11 never above 14.85 %.

## How many other winners to expect

The public split ("Folket", the percentages the coupon page shows per match) predicts how many rows share each tier. Treat the other tippers as picking independently in each match. With `q` the public split and `o` the final result, a randomly picked public row has exactly k wrong picks with probability `c_k(o)` (the coefficient of x^k in `Π_i (q_i(o_i) + (1 − q_i(o_i))·x)`), so about `turnover × c_k(o)` other rows land in the tier of "12 − k correct".

Checked on the 60 rounds, the ratio of actual to predicted winners had a median of **0.97 (11 correct) and 1.03 (10 correct)**; for 12 correct it was 0.83 with large scatter (few winners). So the independence assumption is good for the 11 and 10 tiers and rougher for 12.

## What this means for building a coupon

- A coupon's expected payout depends on **which results it covers and how crowded those results are**: a row that wins when the public also wins shares the tier with many others.
- Following the public ("Folket") is the weakest way to play: on the Sunday 11 Oct coupon at 48 rows it was worth about 0.35 kr per kr staked, against 0.44 for the coupon with the best chance of 12 correct and 0.47 for the balanced coupon this repo builds. The average ticket is worth about 0.47 kr per kr before the bonus pool.
- The expected payout of a "jackpot-chasing" coupon (long shots only) is dominated by events that happen about once in thousands of rounds, so it cannot be estimated reliably (standard error above 15 %); on fresh samples it scored worse than the balanced plan. This repo does not offer it.
- Expected payout per krone barely depends on the pool size (your payout and the others' rows scale together), but the turnover is still needed for the 5 kr rounding, the 10 kr minimum and the tier-12 estimate. The final turnover is only known after the deadline; the fetch step estimates it from last week's comparable round.
