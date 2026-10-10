# Roadmap

The goal: a small set of skills that take you from "what's on tonight?" to "this is a value bet at this stake, and here's how my past bets have done".

## How value is found

The core method throughout is **market comparison**: estimate the fair probability of an outcome from sharper, lower-margin markets (e.g. Pinnacle, betting exchanges, or a consensus of many books), then compare it with Oddsen's price. Where Oddsen pays more than fair odds by a safe margin, that's a candidate. Own models (Poisson, Elo) come later and only for markets with no good reference price.

```
oddsen-fixtures ──┐
                  ├─> oddsen-value-scan ─> oddsen-stake ─> oddsen-bet-journal
reference-odds ───┘           ▲                                   │
                              │                                   ▼
                  oddsen-value-check (one bet)          oddsen-clv-review
```

## Phase 1: Foundations (no external data)

| Skill | What it does | Inputs → output |
|---|---|---|
| `oddsen-odds-math` | Converts odds, computes margin, de-vigs a market, computes EV and fair odds. The building block every other skill calls. | Odds for a market → implied/fair probabilities, margin, fair odds |
| `oddsen-value-check` | Judges **one** bet: is the Oddsen price above fair odds by enough? | Oddsen odds + reference odds (pasted or screenshot) → verdict, edge, EV, suggested stake |
| `oddsen-stake` | Bankroll and staking: flat or fractional Kelly, per-bet and daily caps, combo warnings. | Bankroll, edge, odds → stake in NOK and % |

## Phase 2: Data (fetch games and odds)

| Skill | What it does | Open questions |
|---|---|---|
| `oddsen-fixtures` | Lists upcoming events and current Oddsen odds for chosen sports/leagues and a time window. | Which source? Options: Norsk Tipping's public site/endpoints (check terms first), the user's browser via Claude in Chrome, or pasted/screenshotted coupons as a fallback. |
| `oddsen-reference-odds` | Fetches sharp/consensus odds for the same events to use as "fair" prices. | Provider, e.g. [The Odds API](https://the-odds-api.com) (free tier, needs key) or similar. How to match team names across sources. |
| `oddsen-value-scan` | Joins the two, de-vigs the reference market, ranks Oddsen selections by edge, and filters by min edge, max odds, leagues and kick-off window. | Default thresholds (e.g. edge ≥ 3 %, odds 1.5–5.0). Handling stale odds. |

## Phase 3: Discipline and feedback

| Skill | What it does |
|---|---|
| `oddsen-bet-journal` | Logs bets to a local CSV (date, event, market, odds, stake, fair odds at bet time, result). Never committed: `data/` is git-ignored. |
| `oddsen-clv-review` | Weekly/monthly review: ROI, hit rate vs expected, closing line value, by league/market. Flags drift from the staking plan. |

## Phase 4: Optional extras

| Skill | What it does |
|---|---|
| `oddsen-football-model` | Poisson/Dixon–Coles goal model for leagues without a reliable sharp line (e.g. lower Norwegian divisions). |
| `oddsen-news-check` | Checks lineups, injuries and suspensions before a bet, since late news is the main reason a "value" price is actually just stale. |
| `oddsen-session-check` | Start-of-session check: bankroll, limits, recent results, and a gentle stop if staking rules have been broken. |

## Phase 5: Tipping coupons (pool game)

Design: [`COUPON-ARCHITECTURE.md`](COUPON-ARCHITECTURE.md). Pool math: `shared/tipping-pool-math.md`. Zero-config: no API keys, no login; anonymous public data only. Different problem from Phases 1-4: the edge is picking outcomes the public under-backs, and Kelly does not apply.

| Skill | What it does |
|---|---|
| `oddsen-tipping-fixtures` | Reads the open coupon (matches, deadline, row price) from public sources, with pasted-coupon fallback. |
| `oddsen-tipping-market-odds` | Public 1X2 odds from several books, matched across sources by normalised team names. |
| `oddsen-tipping-public-split` | Public distribution ("folkets fordeling") per match; odds-implied crowd model if unpublished. |
| `oddsen-tipping-team-context` | Form, H2H, standings, absences, rotation risk, weather, all with sources. |
| `oddsen-tipping-probability-engine` | De-vigs each book, builds a weighted consensus and a spread/uncertainty measure. |
| `oddsen-tipping-value-model` | Bounded, justified adjustments to the consensus; computes `p_est / public share`. |
| `oddsen-tipping-coupon-optimizer` | Chooses single marks and half/full covers within a budget; reports `P(all correct)`. |
| `oddsen-tipping-coupon-output` | Final recommendation: marks, confidence, reasoning, risks, cost in NOK and % of bankroll. |
| `oddsen-tipping-coupon` | Orchestrator that runs the above; asks only for budget and bankroll. |

Suggested build order: pool math + optimizer first (pure maths, testable offline), then the probability engine and the value model (offline, take pasted odds and news), then fixtures with the pasted fallback, then the fetchers for odds and public split, then context.

## Decisions to make before Phase 2

1. **Sports and leagues in scope** for v1 (suggestion: football only: Eliteserien, OBOS-ligaen, Premier League, Championship, top 5 leagues).
2. **Oddsen data source.** Prefer something that respects Norsk Tipping's terms. Browser-assisted reading of the user's own session is the safest fallback.
3. **Reference odds provider** and whether users need their own API key (likely yes; document in each skill).
4. **Where the journal lives:** local CSV (simple, private) vs. a Google Sheet / Claude artifact.
5. **Default thresholds:** minimum edge, max stake %, max bets per day.

## Decisions to make before Phase 5

1. **Coupon products and rules (TO VERIFY):** which pool games, matches per coupon, row price, payout tiers, jackpot behaviour.
2. **Public split availability:** does Norsk Tipping publish it per coupon, and where? If not, how to calibrate the crowd model.
3. **Anonymous sources:** which public odds and fixtures endpoints are stable, and what Norsk Tipping's terms allow for automated reading.
4. **Default coupon cap:** proposed 2 % of bankroll per coupon, user-overridable.
5. **Prefix:** Tipping skills use `oddsen-tipping-` (recorded in CLAUDE.md).

## Status

| Skill | Status |
|---|---|
| `oddsen-tipping-coupon` (orchestrator) | Built; works on pasted data; needs testing in Claude.ai and Claude Code |
| `oddsen-tipping-coupon-output` | Built, tested; needs testing in Claude.ai and Claude Code |
| `oddsen-tipping-value-model` | Built, tested; needs testing in Claude.ai and Claude Code |
| `oddsen-tipping-probability-engine` | Built, tested; needs testing in Claude.ai and Claude Code |
| `oddsen-tipping-coupon-optimizer` (pool math in `shared/tipping-pool-math.md`) | Built, tested; needs testing in Claude.ai and Claude Code |
| `oddsen-tipping-fixtures`, `-market-odds`, `-public-split`, `-team-context` (the fetchers) | Not started; blocked on checking Norsk Tipping terms and public endpoints |
| Phases 1-4 | Not started |
