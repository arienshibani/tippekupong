---
name: oddsen-tipping-coupon
description: Builds a full Tipping kupong recommendation end to end, from the week's matches, odds and public split to marks, gardering (half/full covers) within a budget, and a report. Use when the user says "analyser kupongen", "lag en tippekupong", "gardering", "tipping", or asks what to play on this week's coupon.
---

# Tipping coupon (orchestrator)

Runs the Tipping pipeline in order and keeps the user in control. It asks only for what it must (budget, bankroll, row price), gathers the data, and hands each stage to a specialist skill. This skill adds no maths of its own.

Install all `oddsen-tipping-*` skills together. This skill calls them by name:

1. `oddsen-tipping-probability-engine`: odds to fair probabilities.
2. `oddsen-tipping-value-model`: news adjustments and value ratios against the public split.
3. `oddsen-tipping-coupon-optimizer`: marks and covers within the budget.
4. `oddsen-tipping-coupon-output`: the final report.

## Before you start

- Read `references/responsible-gambling.md` and follow it. The pool is a negative-expectation game on average; say so once, early, without lecturing.
- Read `references/tipping-pool-math.md` and `references/odds-math.md` only if you need to explain a number.
- Nothing in this pipeline logs in, uses an account, or places a bet. The user fills in the coupon themselves.

## Inputs to ask for (once)

| Input | Notes |
|---|---|
| Budget for this coupon (NOK) | Ask. If it exceeds 2 % of their bankroll, say so and offer a cheaper tier. |
| Bankroll (NOK) | Ask. Needed to show cost as a share of it. |
| Row price (NOK) | Ask or read it from a source you can cite. **TO VERIFY** against Norsk Tipping's current rules. |
| Risk preference | `cautious` maximises the hit chance, `balanced` is the default, `contrarian` favours under-backed outcomes. Map to the optimizer's `safe`, `balanced`, `contrarian`. |

Never ask the user to log in, share a password, or hand over account access.

## Steps

1. **Get the coupon.** Ask the user to paste or screenshot this week's matches (the list in order, the deadline). Use their wording for team names and keep the slot order. Note where it came from and when. Automatic fetching of the coupon is not built yet; do not scrape Norsk Tipping unless the user explicitly asks and the site's terms allow it.
2. **Get 1X2 odds.** For each match, collect decimal H/U/B odds from one or more bookmakers, pasted or from a public page you can cite, with the time they were taken. Odds from several books are better than one. Convert other odds formats and say so. Anything missing for a match means that match gets no analysis; say so.
3. **Fair probabilities.** Run `oddsen-tipping-probability-engine`. Keep its `confidence` and dropped-quote notes.
4. **Public split.** Ask for the "folkets fordeling" shown on the coupon page, per match. If the user has none, run without it and say that crowding numbers will be missing. Only if the user agrees, use a rough odds-based estimate and mark it `q_estimated: true`.
5. **Team news.** Ask whether the user has relevant news, or look for it only on public pages you can cite. Propose small, sourced adjustments and mark rumours `unconfirmed`. Do not adjust for news the market has had days to price in. Then run `oddsen-tipping-value-model`.
6. **Optimise.** Run `oddsen-tipping-coupon-optimizer` with the value model's `optimizer_matches`, the row price, the budget (and a higher "max" budget only if the user asks for one) and the risk preference.
7. **Report.** Run `oddsen-tipping-coupon-output` with the bankroll and cap, the optimizer result, the value-model `matches` and `excluded`, the sources, and your one-line reasons. Show the report.
8. **Close.** Remind the user that lineups can change before the deadline and offer to re-run. Offer to explain any number. Do not suggest raising the budget.

## Degraded paths (say each one out loud)

| Situation | What to do |
|---|---|
| Coupon pasted by hand | Fine. Note "pasted" as the source with the time. |
| One bookmaker only | Continue; the report shows low confidence. |
| No odds for a match | Exclude it; the report lists it and the user must mark it themselves. |
| No public split | Continue; hit chance only, no crowding numbers. |
| Estimated public split | Continue; label it "estimated" wherever it appears. |
| Odds older than a few hours | Ask for fresh ones; the engine drops quotes older than 6 h. |
| Deadline close or passed | Say so first. |

## Output

The report from `oddsen-tipping-coupon-output`, unchanged. Always include: cost in NOK and as a % of bankroll, chance of a fully correct row as "about 1 in N", per-match reasons and risks, matches that were not analysed, sources with times, and the closing text.

## Edge cases

- **The user wants a sure thing, a banker, or a guaranteed return:** explain there is none and that a pool coupon is on average a loss. Offer the most likely outcomes with their estimated probabilities.
- **The user wants to spend more after a loss, or mentions debt, borrowing, hiding play, or being unable to stop:** do not build a bigger coupon. Follow `responsible-gambling.md`: mention Hjelpelinjen (800 800 40, hjelpelinjen.no) and Norsk Tipping's tapsgrense and spillepause once, without lecturing.
- **The user asks you to submit the coupon:** decline. The user places it themselves.
- **Conflicting numbers from different sources:** show both; don't average silently outside the engine.
- **A rule you are unsure of (matches per coupon, payout tiers, jackpot):** say it is unverified and point the user to Norsk Tipping's rules.

## References

- `references/tipping-pool-math.md`
- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
