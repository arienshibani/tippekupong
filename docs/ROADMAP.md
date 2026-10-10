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

## Phase 5: Tipping coupons (pool game): built

Design and results: [`COUPON-ARCHITECTURE.md`](COUPON-ARCHITECTURE.md). Rules: `shared/tipping-payout-rules.md`. Zero-config: no API keys, no login. Different problem from Phases 1-4: the prizes are shared, so the edge is in avoiding the results many others cover; Kelly does not apply.

| Skill | What it does | Status |
|---|---|---|
| `tippekupong` | Orchestrator: fetch, estimate, build, report. | Built; fresh-Claude tested on live data (3 rounds) |
| `tippekupong-fixtures` | Open rounds from Norsk Tipping's public site data, with a paste fallback. | Built |
| `tippekupong-odds` | Free multi-bookmaker odds (football-data.co.uk) for the leagues it covers. | Built |
| `tippekupong-probabilities` | De-vig, consensus, and the blend with expert tips and public split. | Built |
| `tippekupong-news` | Bounded, sourced news adjustments with a priced-in check. | Built |
| `tippekupong-optimizer` | Builds the coupon for expected payout over the 12/11/10 tiers. | Built |
| `tippekupong-report` | The report. | Built |

Ideas not built: a rating model (Elo/Poisson) from `football-data.co.uk/new/NOR.csv` for Eliteserien matches, which have no free odds; team-news fetching from public pages; a Norwegian version of the report; the half-time game; multi-week play.

## Decisions to make before Phase 2

1. **Sports and leagues in scope** for v1 (suggestion: football only: Eliteserien, OBOS-ligaen, Premier League, Championship, top 5 leagues).
2. **Oddsen data source.** Prefer something that respects Norsk Tipping's terms. Browser-assisted reading of the user's own session is the safest fallback.
3. **Reference odds provider** and whether users need their own API key (likely yes; document in each skill).
4. **Where the journal lives:** local CSV (simple, private) vs. a Google Sheet / Claude artifact.
5. **Default thresholds:** minimum edge, max stake %, max bets per day.

## Decisions still open for Phase 5

1. **Terms of use.** Is reading Norsk Tipping's public site data feed once per run acceptable? The `robots.txt` allows the Tipping pages; the terms text could not be read. Ask Norsk Tipping or read their full terms.
2. **Report language.** Norwegian output (`--lang no`) means maintaining two sets of wording.
3. **Rating model for Eliteserien.** Worth building only if it beats the expert-plus-public blend on the 720 saved matches.
4. **Bonus pool.** Not modelled; check whether the API exposes its size.

## Status

| Area | Status |
|---|---|
| Tipping coupon builder (Phase 5) | Built and tested (173 unit tests; 3 fresh-Claude rounds, the last on live data). Not yet tried as an installed plugin in Claude.ai or Claude Code. |
| Phases 1-4 (Oddsen value bets) | Not started |
