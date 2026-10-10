# Fixes after fresh-Claude test runs 1 and 2 (2026-10-10)

Findings are from `2026-10-10-fresh-claude-run-1.md` (plugin 0.5.1) and `2026-10-10-fresh-claude-run-2.md`. This file lists what was changed in response (plugin 0.6.0), what was deliberately not changed, and what still needs a decision. Test count after the fixes: 117, all passing.

## Changed after run 1

| Finding | Change |
|---|---|
| Report says "1 in 54" but two matches were unanalysed | Chance is scoped to the analysed matches, then shown as a whole-coupon range (see run 2). Cost of covering an unanalysed match is quantified (half cover ×2, full cover ×3, with % of bankroll and whether it breaks the cap). |
| Quote dropped as stale was lost from the report | Engine puts `dropped` reasons into `excluded`; the value model passes them on; the report prints them next to the unanalysed match. |
| "Priced in" and "too close" news was invisible | The report lists every news adjustment that was not applied, grouped by reason; unconfirmed items merge into one line per match. |
| Risk column was noise ("confidence high" six times) | Blank ("–") for a clean match; otherwise reasons and short notes. |
| Time handling unspecified | Orchestrator: check `date -u`, `now` only to replay old data, write times as ISO with `Z` or an offset (Oslo is `+02:00` in summer, `+01:00` in winter). Scripts reject a time without a zone instead of guessing in the machine's zone. Deadline and source times are shown in Oslo time (UTC in brackets) with time left. |
| User-guessed public split | Orchestrator: never use a guessed split, unless the user agrees to it being labelled an estimate ("your guess"). |
| News about an hour before the odds | Replaced a vague rule with a mechanical one (see run 2). |
| Stale odds: stop or continue? | Orchestrator degraded-paths table: drop quotes older than 6 h, continue with the other matches, exclude that match, ask once at the end for fresh odds. |
| Handoff table incomplete | Whole engine match objects are copied; `coupon`, `sources`, `why`, `cap_pct` and `now` shapes are documented with an example block. |
| Engine `--text` printed no margins, sources or times | Prints margin, weight share and the time each book's odds were taken. |
| Book names and weights; de-vig method | Orchestrator: use the user's label for a book, leave weight at 1; default multiplicative, switch the whole run to `power` if any favourite is below odds 1.30. |
| Reply language | Orchestrator: reply in the user's language with a short summary before the English report. (Localising the report itself is a decision, below.) |
| Row price unverified, cap boundary | Orchestrator: use the user's figure, record "row price unverified", say so; exactly 2 % is within the cap. |
| Comma decimals ("2,10") silently dropped | Accepted. |
| Unit mistakes (`delta_pp` of -0.03; 51 instead of 0.51) | Flagged; percentages are now accepted outright (see run 2). |
| Cryptic errors from `render.py` | Readable message for missing fields or wrong shape. |
| Unused budget unexplained | The optimizer reports each tier's budget; the report explains why a tier uses less (rows are products of 1, 2 and 3). |
| Crowding index unexplained | Plain-language sentence first ("about 1.2× as crowded as their probability suggests… leans toward hit chance rather than payout"), technical figure after. |
| Duplicate/jargon warning ("value ratio treated as 1") | Reworded; optimizer split warnings are not repeated at the top of the report. |
| Responsible gambling gaps | `responsible-gambling.md`: asking for a bigger budget to win back a loss is a trigger; the report's closing line counts as the first helpline mention and a second, in your own words, is the last; a cap raised in the same message as a loss is not the user's own cap; "pausing" defined; debt larger than the bankroll; "safest cover" requests. The standard "more rows raise the chance…" line no longer nudges towards bigger coupons. |
| Banker request | Orchestrator and output skill give the same answer: no banker; the likeliest outcome with its probability and what that means. |

## Changed after run 2

| Finding | Change |
|---|---|
| **Over-cap budget produced an over-cap "recommended" plan** (any request that was not exactly twice the cap) | The optimizer now takes `bankroll_nok` (and `cap_pct` only if the user set their own cap) and builds every tier at or below the cap, including the "max" tier. It reports `requested_budget_nok`, `budget_nok` and `budget_capped`. If a cap is below one row it is an error. The report says what was asked and what was cut, and if no tier fits the heading becomes "Cheapest plan … (above the cap, not recommended)". |
| Page percentages adding to 99-101 were a hard error | Percentages are accepted as typed; anything within 2 % of the right total is divided by its total and noted (clean totals say nothing). Float comparison fixed. All failing matches are listed in one error. Rescaled splits are noted in the Risk column and under "What could be wrong". |
| Applied news was invisible in the report | New "News used" section: outcome, size, reason, source and time, with mirrored legs on one line. |
| Headline chance too prominent | When matches are unanalysed the bold headline is the whole-coupon range; the analysed-only figure follows; tier table has a "Whole coupon, roughly" column. |
| Requested budget and "your cap" wording | The report states what the user asked (and as % of bankroll); "the default 2 % cap" vs "your N % cap" depends on whether `cap_pct` was passed. |
| Priced-in rule too vague | The value model decides from times: news at least 15 minutes before the earliest odds is priced in; news after the latest odds is applied (with a note if under 30 minutes before the run); anything between is too close to tell, not applied, flagged. Explicit `market_likely_priced_in` still overrides. Needs `source_time` on the news and the engine's `books` on the match. |
| Had to invent sizes for unapplied news | `delta_pp` is optional for unconfirmed and priced-in items; the flag shows the outcome without a made-up number. |
| One news item split over outcomes lowered confidence | Confidence counts distinct news items (same source and time), not adjustment legs. |
| Undated rumour became a top warning | Shown under "What could be wrong"; sources whose time does not matter (the match list) are marked `static`. |
| Source times only in UTC | Oslo time first, UTC in brackets. |
| Nested parentheses in dropped-quote text | "Book - reason" format. |
| `deadline_utc` naming | `deadline` (any ISO time with a zone); `deadline_utc` still accepted. |
| Book nicknames | Orchestrator: use the user's label and say the real name was not given. |
| "Pause" and "safest cover" undefined | Defined in `responsible-gambling.md`, referenced from the orchestrator. |

Noise removed after replaying the run-2 scenario through the fixed scripts: clean percentage conversions no longer print a note on every match, the "news is only N min old" note is once per news item, the optimizer's twin of the budget warning is not repeated, and mirrored news legs share one line.

## Deliberately not changed (needs a decision)

1. **Report language.** The report text and closing line are English. Letting `render.py` produce Norwegian (`lang: "no"`) means maintaining two sets of wording and a translated closing and helpline text; the skills currently ask Claude to add a short summary in the user's language instead.
2. **Optimizer objective.** Cover sizes are chosen on hit chance alone, so `safe` and `balanced` usually give identical plans and `contrarian` mostly reduces crowding. An expected-payout mode (maximise the product over matches of the summed value ratios per NOK) would make the risk setting meaningful. See open question 6 in `COUPON-ARCHITECTURE.md`. A related option is to break near-ties between plans by crowding.
3. **Auto-mirroring news.** `adjust.py` could take one side of a news shift and mirror it, instead of Claude supplying both legs. Left as is because the legs are explicit and the report already merges them.
4. **Match-specific range for unanalysed matches.** The whole-coupon range uses a fixed 30 % to 55 % chance per single mark. It could use the user's own mark and a quick estimate when morning or stale odds exist.
5. **Not yet tested in Claude.ai or Claude Code**, so automatic triggering from the skill descriptions is unverified. Norsk Tipping's pool rules (row price, matches per coupon, payout tiers) are still marked TO VERIFY.

---

# The fetching version (plugin 0.7) and round 3

## What changed in the design

The first five rounds of work analysed a coupon the user had to paste in. The user's goal was a skill that **builds** the coupon. Reading Norsk Tipping's public Tipping page showed that everything except bookmaker odds is available from its own data feed, so the pipeline now starts from "bygg kupongen for søndag". Details: `COUPON-ARCHITECTURE.md`.

Things learned on the way that changed earlier work:

| Finding | Consequence |
|---|---|
| Prizes are paid for **12, 11 and 10** correct, not only 12 (55 % of turnover; 27/27/31 % to the tiers; a tier-10 prize under 10 kr is cancelled in about 1 round in 4) | The old optimizer's objective (chance of a fully correct row) was the wrong target. `build.py` optimises the three-tier expected payout; `optimize.py` stays as the exact solver for the chance of all 12 |
| Row price is 1.00 NOK, 12 matches, three rounds a week (confirmed from the feed) | The "TO VERIFY" rules are now facts with evidence in `shared/tipping-payout-rules.md` |
| The public split is nearly as good a probability as Norsk Tipping's own expert tips (log-loss 0.9424 vs 0.9375; coin flip 1.0986) | The blend uses both; for matches without bookmaker odds there is little independent edge, and the report says so |
| Following the public ("Folket") is the weakest way to play (0.35 kr back per kr against 0.44 to 0.47) | Every report shows that comparison |
| A pure expected-payout objective drifts to long shots and its estimate does not survive fresh samples (0.58 to 0.67 on the search samples, 0.39 to 0.44 on new ones) | Not offered; the default is "balanced" (best payout among plans with at least 80 % of the best prize chance) |
| In football-data's file `PP` is Paddy Power, not Pinnacle | Fixed label (it had been mislabelled) |
| `ø` is not decomposed by Unicode accent stripping | Name matching transliterates ø and æ; a test covers "Bodø/Glimt" |
| 1/margin² let one exchange quote carry 86 % of a consensus | Weights are now 1/margin |
| numpy is not installed on the user's Python | Everything is pure Python (a few seconds per coupon) |

## Round 3: fresh Claude, live data, bare Norwegian request

Report: `2026-10-10-fresh-claude-run-3.md`. It ran end to end on the first try; the findings were about the report and a few instructions.

| Finding | Change |
|---|---|
| News on a match without bookmaker odds was applied silently, though the public split was read an hour after the news | `blend.py` carries the time the split was read; `adjust.py` flags "the split may already reflect the news" once per news item (still applied) |
| Report too long and repetitive (the same Risk text nine times; auto reasons restating the table) | Risk shows short reasons ("no bookmaker odds") with "(low confidence)" only when low; the reason column says something only when there is something to say (the likeliest outcome, a flat match, a cover that includes a less likely outcome because fewer tippers back it, clearly under- or over-backed outcomes); "in line" removed |
| "A small edge" printed when the plan was worth the same as an average ticket | The verdict follows the numbers: "a small edge" only if at least 0.03 per NOK above 0.47, else "about the same" or "below"; the standard error is printed with "differences under about 0.02 are noise" |
| Baselines quoted "with the same budget" though they had a different row count | Quoted with their own row counts |
| No kick-off times; lowercase English title | Kick-off column in Oslo time; title "Tipping, Sunday 11 October (round #69453)"; header shows the strategy |
| Balanced and prize-chance plans were indistinguishable but shown as different | A line says when they are within the margin of error |
| Mixed confidence vocabulary | Documented; the report shows reasons, not labels |
| Orchestrator: `--day` hard-coded to `next`, `S` undefined, budget/bankroll placeholders, "half a minute", where to put the source sentence, duplicate `--note`, no `--source` example, no "does the news matter?" step, `allowed_week_counts` undocumented, renormalised weights unexplained | All fixed in the orchestrator, fixtures, engine and value-model skills |
| Precedence when "submit it", "banker" and "raise to win back" arrive together | The pause rule wins: short reply, decline to submit (no account access), only the single likeliest outcome, no per-match list, no quoting of a new stake as a percentage |

Not changed: a Norwegian version of the report (decision), the optimizer's choice between near-identical plans (now disclosed instead).
