# Odds math reference

All odds on Oddsen are **decimal odds** (e.g. `2.40`). A winning bet returns `stake × odds`, stake included.

## Implied probability

```
implied_p = 1 / odds
```

`2.40` → 41.7 %.

## Bookmaker margin (overround)

For a market with outcomes `i = 1..n`:

```
overround = Σ (1 / odds_i)
margin    = overround − 1
```

A 1X2 (H/U/B) market at `2.40 / 3.30 / 3.00` → 0.417 + 0.303 + 0.333 = 1.053 → 5.3 % margin.

## Removing the margin ("de-vigging")

To estimate *fair* probabilities from a market, remove the margin. Methods, simplest first:

| Method | Formula | Notes |
|---|---|---|
| Multiplicative (proportional) | `p_i = (1/odds_i) / overround` | Default. Spreads margin evenly. |
| Additive | `p_i = 1/odds_i − margin/n` | Can go negative on long shots. |
| Power | find `k` so `Σ (1/odds_i)^k = 1`, `p_i = (1/odds_i)^k` | Handles favourite–longshot bias better. |
| Shin | iterative, models insider share `z` | Best on markets with long shots; more work. |

Use multiplicative unless a skill says otherwise, and always say which method was used.

## Fair odds

```
fair_odds = 1 / fair_p
```

## Edge and expected value

Given your estimate of the true probability `p` and offered odds `o`:

```
EV per 1 kr staked = p × o − 1
edge               = p × o − 1        (same thing, shown as %)
```

A bet is a **value bet** when `EV > 0`. In practice use a threshold (e.g. `EV ≥ 3 %`) to cover estimation error and odds movement.

Example: fair `p = 0.45` from a sharp market, Oddsen offers `2.40` → `0.45 × 2.40 − 1 = +8 %`.

## Stake sizing (Kelly)

Full Kelly fraction of bankroll:

```
f* = (p × o − 1) / (o − 1)
```

Full Kelly is far too aggressive when `p` is only an estimate. Use **fractional Kelly** (¼ or less) and cap any single bet (e.g. ≤ 2 % of bankroll). Flat staking (same small stake every bet) is a fine alternative.

## Accumulators (kombinasjoner)

Odds multiply, and so does the bookmaker's margin. A 4-leg combo at 5 % margin per leg carries roughly `1.05⁴ − 1 ≈ 21.6 %` margin. Only combine legs that are each value on their own.

## Closing line value (CLV)

```
CLV = odds_taken / fair_closing_odds − 1
```

Consistently beating the closing line (positive CLV) is the best short-term evidence that your bets have real value, long before profit/loss becomes meaningful.
