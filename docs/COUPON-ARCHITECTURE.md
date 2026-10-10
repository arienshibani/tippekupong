# Tipping coupon architecture

Design for a modular skill system that builds an optimized **Tipping pool coupon** (1X2 rows with hel-/halvgardering) from public data. Design only; no skill in this document is built yet. See `ROADMAP.md`, Phase 5.

## Goals and constraints

- **Product:** Norsk Tipping's pool game (Tipping), not Oddsen fixed-odds. A pool pays a share of a pot among winning rows, so the edge is picking outcomes the public under-backs relative to their true probability. Math: `shared/tipping-pool-math.md`.
- **Zero friction:** no API keys, no login, no BankID, no cookies. Data comes from anonymous public pages and feeds and from free open datasets (e.g. football-data.co.uk).
- **Output:** a structured recommendation plus a copyable row summary and, if a stable public URL exists, a link to the coupon page. The user fills it in themselves in an app where they are already logged in. Nothing is placed automatically.
- **Honesty:** a pool has a takeout, so the expected result is a loss. Skills report estimated edge and uncertainty, never certainty (`shared/responsible-gambling.md`).
- **Rules to verify** before any skill states them as fact: matches per coupon, row price, payout tiers, pool and jackpot rules, the exact coupon names (Lørdagskupongen, Stryktipset-style products, etc.).

## Pipeline

```
tipping-fixtures ─┬─> tipping-market-odds ───┐
                  ├─> tipping-public-split ──┼─> tipping-probability-engine ─> tipping-value-model
                  └─> tipping-team-context ──┘                                        │
                                                                                      ▼
                         tipping-coupon-output <─ tipping-coupon-optimizer <──────────┘
```

A thin orchestrator, `oddsen-tipping-coupon`, runs the stages in order. Each stage is also usable alone.

**Division of labour.** Scripts do everything numeric (de-vig, consensus, ratios, search) so results are reproducible and checkable. The LLM does what scripts cannot: reading team news, proposing bounded probability adjustments with reasons, and explaining the result in plain language. The LLM never writes a probability that the script did not compute or that it did not justify with a cited source.

**Adapters.** Every network fetcher sits behind a small adapter (`fetch(match_list) -> data + Source`). Public endpoints are undocumented and change; swapping a source must not touch the math.

## Common schemas

```
Source   { name, url, fetched_at (UTC ISO-8601), method: "public-api"|"page"|"dataset"|"pasted" }
Probs    { H, U, B }            # sums to 1 (±0.001)
Match    { id, league, home, away, kickoff_utc, coupon_slot, source: Source }
Coupon   { name, week, deadline_utc, row_price_nok, matches: Match[], pool_nok?: number }
```

Every object that holds fetched data carries a `Source`. Team names are normalised through `references/team-aliases.csv` (canonical name, aliases per source).

## Stage 1: `tipping-fixtures`

- **Input:** coupon name or "this week" (default: the open coupon).
- **Output:** `Coupon` (above).
- **Logic:**
  1. Read the public coupon page or JSON anonymously. Record the source and fetch time.
  2. If unreachable or blocked, ask the user to paste or screenshot the coupon and parse that (`method: "pasted"`).
  3. Normalise team names; assign `coupon_slot` 1..N in coupon order.
  4. Warn if the deadline has passed or is under 1 hour away.
- **Libraries:** Python `urllib`/`requests`, `json`; HTML parsing only if no JSON exists.

## Stage 2: `tipping-market-odds`

- **Input:** `Match[]`.
- **Output per match:** `[{ book, odds: {H,U,B} decimal, fetched_at, source }]` from several books.
- **Sources (no key):** public odds pages and feeds of several bookmakers, including Norsk Tipping's own public odds; football-data.co.uk for historical closing odds (used for validation, not live prices).
- **Logic:**
  1. Fetch each source politely: low rate, cache for the session, honour robots.txt and terms.
  2. Match fixtures across sources by normalised names plus kick-off within ±3 h.
  3. Drop any quote that is not a complete H/U/B triple or whose timestamp is more than 6 h old at run time (configurable; implemented in the probability engine), and say what was dropped.
  4. Never fill gaps by guessing. A match with no usable odds is flagged `no_market` and handled in stage 5.

## Stage 3: `tipping-public-split`

- **Input:** `Match[]`.
- **Output per match:** `{ q: Probs, source, fetched_at, estimated: bool }`.
- **Logic:**
  1. Read the public distribution percentages ("folkets fordeling") from the coupon page.
  2. If unavailable, set `estimated: true` and use a crowd model derived from the odds: start from implied probabilities and tilt toward the favourite and home side (public over-backs favourites; exact tilt is a documented parameter, default small, to be calibrated against pages that do publish the split).
  3. Normalise so `q` sums to 1. Floor at 0.02 so ratios cannot explode.
- Always show whether `q` is observed or estimated.

## Stage 4: `tipping-team-context`

- **Input:** `Match[]`.
- **Output per match:**
  ```
  { form_last6: {home, away}, h2h_last5, standings: {home, away},
    absences: [{team, player, status, source}], rotation_risk: "low"|"med"|"high",
    weather?, notes: string[], sources: Source[] }
  ```
- **Sources:** football-data.co.uk results for form and H2H; public standings and team-news pages; weather only when it plausibly matters.
- **Logic:** collect facts with sources and timestamps. Rotation risk comes from congestion (matches in the last 4 days), a cup or European tie next, or a dead-rubber table position. Qualitative items stay as text. They become numbers only in stage 6, bounded and explained.

## Stage 5: `tipping-probability-engine` (script)

- **Input:** quotes from stage 2.
- **Output per match:** `{ p_fair: Probs, margin_by_book, consensus_weights, spread, method }`.
- **Logic:**
  1. De-vig each book's H/U/B with the multiplicative method by default (`shared/odds-math.md`); allow Shin; always record `method`.
  2. Consensus = weighted mean of de-vigged probabilities. Weights favour low-margin (sharper) books, e.g. `w ∝ 1/margin²`, normalised.
  3. `spread` = max − min of de-vigged `p` across books for the most likely outcome; this is the uncertainty proxy shown to the user.
  4. `no_market` matches fall back to a baseline from open data (v1: league-average home/draw/away rates adjusted by Elo difference, clearly labelled low confidence). Poisson/Dixon–Coles comes later via `oddsen-football-model`.
- **Libraries:** standard library; `numpy` optional.

## Stage 6: `tipping-value-model`

- **Input:** `p_fair`, `q`, context from stage 4.
- **Output per match:** `{ p_est: Probs, adjustments: [{outcome, delta_pp, reason, source}], q: Probs, value_ratio: Probs, confidence }`.
- **Logic:**
  1. The LLM proposes adjustments to `p_fair`, each with an outcome, a size in percentage points, a reason and a source. Hard cap ±5 pp net per outcome and 8 pp in total (sum of absolute changes) per match. Anything larger needs the user's explicit OK. News the market has probably priced in is not applied.
  2. A script applies the adjustments, renormalises, and computes `value_ratio = p_est / q`.
  3. `confidence` combines: book spread (low is good), `q` observed vs estimated, news freshness, and number of adjustments (many adjustments lower confidence).
- Late news is the main reason a price looks wrong. If a key absence is unconfirmed, the adjustment is recorded as "unconfirmed" and the match gets a risk flag instead of a number.

## Stage 7: `tipping-coupon-optimizer` (script)

- **Input:** `p_est`, `q`, `row_price_nok`, `budget_nok`, `max_rows?`, preferences (`risk`: safe / balanced / contrarian).
- **Output:** one or more `CouponPlan`:
  ```
  { marks: [{slot, outcomes: ["H"|"U"|"B", ...]}], rows, cost_nok,
    p_all_correct, mean_row_value_index, tier: "cheap"|"base"|"max" }
  ```
- **Logic:**
  1. `max_rows = floor(budget / row_price)`. Start with the top outcome per match by a blended score: `score = (1-λ)·p + λ·p·value_ratio`, with λ from `risk` (0 safe, 0.5 balanced, 1 contrarian).
  2. Choose cover sizes per match (1, 2 or 3 outcomes; each cover marks the top-n outcomes by score) to maximise `P_cover = Π (Σ p over marked)` subject to `Π n_i ≤ max_rows`. This is solved exactly by dynamic programming over the row count (`oddsen-tipping-coupon-optimizer/scripts/optimize.py`), so no greedy approximation is needed.
  3. Report three tiers (about 50 %, 100 % and, only if the user allows, up to the cap) so the user sees diminishing returns.
  4. Compute `p_all_correct = Π (Σ p_est over marked outcomes)`, row count and cost. Report relative `row_value_index`. Report an absolute EV only if pool size and takeout are known, and mark it uncertain.
- **Complexity:** matches ≤ ~13 and three outcomes, so the search is trivially small. A brute-force check against the greedy result is a test.

## Stage 8: `tipping-coupon-output`

- **Input:** `CouponPlan`, stage 6 data, user bankroll.
- **Output (markdown):**

  | # | Match | Mark | Confidence | p (est) | Public | Why | Risk |
  |---|---|---|---|---|---|---|---|

  followed by a coupon summary:
  - Rows, cost in NOK **and as % of bankroll**, `P(all correct)` as a percentage and as "about 1 in N".
  - Row-grid text the user can copy, one line per match (`1`, `X`, `1X`, `1X2`).
  - A link to the public coupon page if one is stable.
  - A short "what could be wrong" section: stale odds, estimated public split, unconfirmed absences, independence assumption in `Q(r)`.
  - Sources with timestamps for all fetched data.
- **Rules:** never say "safe", "certain" or "lock"; no suggestion to raise stakes after a loss; state that a pool coupon is on average a loss. If the plan exceeds the default 2 % of bankroll, say so and offer a cheaper tier.

## Orchestrator: `oddsen-tipping-coupon`

- **Triggers:** "kupong", "tipping", "gardering", "analyser helgens kupong", "tippekupong".
- **Asks only for:** budget in NOK and bankroll (once, stored for the session). Everything else defaults.
- **Flow:** stages 1-8 in order; at the end of each stage, if it fell back to degraded data (pasted coupon, estimated `q`, `no_market` baseline), carry that into the final risk section.

## Guardrails mapped to CLAUDE.md

| Rule | Where it's met |
|---|---|
| 1. Responsible gambling, stake as % bankroll | Stage 8 prints cost as NOK and % of bankroll; 2 % default cap; no loss-chasing language |
| 2. Show the math | Stage 5-7 outputs carry `p_fair`, `q`, `value_ratio`, `P(all correct)`, methods used |
| 3. Never certain | "estimated" wording, spread and confidence shown |
| 4. Source and timestamp | `Source` on every fetched object; staleness warnings |
| 5. No automated betting | Output is a copyable summary and a link; no login, no form filling |

## Data-source risks

- **Norsk Tipping endpoints are undocumented** and may change or block automation. Check their terms before shipping a fetcher; keep rate low; the pasted-coupon fallback must always work.
- **Public split may not be published** for every coupon. The estimated fallback is labelled and is weaker than observed data.
- **Scraped pages break.** Adapters fail loudly with a clear message rather than returning partial data.
- **Team-name matching** is the most common silent error; the alias file and a "unmatched fixtures" report guard against it.

## Testing approach (when built)

- Unit tests for de-vig, consensus, `value_ratio`, `P_cover` using the worked example in `shared/tipping-pool-math.md`.
- Optimizer: brute-force every cover combination within budget on small coupons and compare to the greedy plan.
- Fixtures: saved snapshots of coupon pages and odds in `tests/fixtures/` so fetchers are tested offline.
- Backtest on football-data.co.uk history: calibration of de-vigged `p` per league.

## Open questions

1. Exact coupon products in scope and their rules (TO VERIFY): matches per coupon, row price, payout tiers, jackpot behaviour.
2. Whether Norsk Tipping publishes the public split for each coupon, and where.
3. Which public odds sources are stable enough to depend on without keys.
4. Whether a per-match crowd-bias model can be calibrated from past published splits.
5. Where session state (bankroll, budget) lives for Claude.ai vs Claude Code.
6. **Optimizer objective.** The optimizer maximises the chance of a fully correct row; the risk setting only changes which outcomes fill a cover. It does not allocate covers by expected payout. Under the independence assumption, expected coupon payout is proportional to `Π_i Σ_k (p/q)` over marked outcomes, which the same dynamic programme could maximise per NOK. A dry run on a 12-match example gave a mean row value index of about 0.46 for the balanced plan, so the current plan trades payout per row for hit chance. Decide whether to add an expected-payout objective as a separate mode.
