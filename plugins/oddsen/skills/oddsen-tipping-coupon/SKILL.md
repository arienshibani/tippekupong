---
name: oddsen-tipping-coupon
description: Builds a complete Tipping kupong for the user: reads this week's matches, odds and public split from Norsk Tipping and open data, picks the marks and half/full covers (gardering) within their budget, and explains the result. Use when the user says "bygg kupongen", "lag en tippekupong", "gardering", "tipping", "hva bør jeg tippe", or asks what to play on this week's coupon.
---

# Tipping coupon (orchestrator)

The user should not have to bring a coupon: this skill fetches the open round itself, estimates each match, and **builds** the coupon (the marks, with half and full covers) that fits their budget. It asks only for what it must (which round, budget, bankroll), runs the stages below as commands, and explains the result. This skill adds no maths of its own.

Install all `oddsen-tipping-*` skills together. Each stage is a script in its own skill's folder:

| Stage | Skill | Script |
|---|---|---|
| 1. Read the open coupons | `oddsen-tipping-fixtures` | `scripts/fetch_coupon.py` |
| 2. Bookmaker odds where they exist | `oddsen-tipping-market-odds` | `scripts/fetch_odds.py` |
| 3. Fair probabilities, blended with the expert tips and the public split | `oddsen-tipping-probability-engine` | `scripts/engine.py`, `scripts/blend.py` |
| 4. Team news adjustments | `oddsen-tipping-value-model` | `scripts/adjust.py` |
| 5. Build the coupon | `oddsen-tipping-coupon-optimizer` | `scripts/build.py` |
| 6. The report | `oddsen-tipping-coupon-output` | `scripts/render.py` |

## Before you start

- Read `references/responsible-gambling.md` and follow it. The pool is a negative-expectation game on average (an average ticket is worth about 0.47 kr per kr staked); say so once, early, without lecturing.
- Read `references/tipping-payout-rules.md` if you need to explain how the prizes work (12, 11 **and 10** correct pay; the prizes are shared with everyone who has the same tier).
- **Where the data comes from.** Stage 1 reads Norsk Tipping's public Tipping page data feed (the same data the website shows), with no login, once per run. It is an unofficial feed that can change or be blocked, and I could not read a clause on automated access in their terms. Tell the user this once in a sentence, and that they can paste the coupon instead if they prefer. Stage 2 downloads a public CSV from football-data.co.uk.
- **Working folder.** Make a scratch folder, `cd` into it, and run every command there. Set `S` once to the folder that contains the `oddsen-tipping-*` folders (`export S=/path/to/skills`): it is the parent of this skill's own folder, whose path is shown when the skill loads (for a plugin install it is under `~/.claude/plugins/`). Pass files, not typed JSON: each script reads the previous stage's output.
- **Time.** Scripts use the machine clock, which is right. Run `date -u` once to see it. Times you write into files (news times, pasted odds times) need a zone: `Z` or an offset, e.g. `2026-10-10T17:00:00+02:00` (Oslo is `+02:00` in summer time, until the last Sunday of October, then `+01:00`). A time without a zone is rejected.
- **Language.** Reply in the user's language. The report is generated in English: show it as is, with a short summary in the user's language before it (what the coupon is, cost as a share of bankroll, the chance of a prize, the main risks). Keep marks and numbers unchanged and do not alter the closing text.
- Nothing here logs in, uses an account, or places a bet. The user fills in the coupon themselves.

## Ask for (once)

| Input | Notes |
|---|---|
| Which round | Saturday, Sunday or midweek. Default: the open round with the nearest deadline (`--day next`). |
| Budget for this coupon (NOK) | The row price is 1 NOK, so the budget is the number of rows. Pass what the user asked for; the optimizer cuts it to the cap and tells you. |
| Bankroll (NOK) | Needed for the cap (2 % by default; exactly 2 % is within it). |
| Own cap | Only if the user states one calmly, not in the same message as a loss or a wish to win one back: pass `--cap-pct`. Otherwise omit it. |

Never ask the user to log in, share a password, or hand over account access.

## Steps

The scripts take a few seconds in all. In the commands below, replace `--day next` with the user's round (`--day sunday`, `--day saturday` or `--day midweek`; `next` only when they did not say), and `50` and `3000` with the user's **budget** and **bankroll**. Run:

```bash
python3 $S/oddsen-tipping-fixtures/scripts/fetch_coupon.py --day next --out coupon.json --text
python3 $S/oddsen-tipping-market-odds/scripts/fetch_odds.py --coupon coupon.json --out odds.json --text
python3 $S/oddsen-tipping-probability-engine/scripts/engine.py odds.json > engine.json
python3 $S/oddsen-tipping-probability-engine/scripts/blend.py --coupon coupon.json --engine engine.json --out blend.json --text
python3 $S/oddsen-tipping-value-model/scripts/adjust.py blend.json --news news.json > value.json      # omit --news if none
python3 $S/oddsen-tipping-coupon-optimizer/scripts/build.py --value value.json --coupon coupon.json --budget 50 --bankroll 3000 --out build.json --text
python3 $S/oddsen-tipping-coupon-output/scripts/render.py --build build.json --value value.json --coupon coupon.json --odds odds.json --bankroll 3000 --out report.md
```

1. **Coupon.** If the deadline has passed or the round is not open, stop and say so. Otherwise do not send a separate message: put the round, deadline (Oslo time), pool, and the one sentence about where the data comes from at the top of your final answer.
2. **Odds.** Only some matches have free bookmaker odds (mostly English and other major leagues; **not** Eliteserien, OBOS-ligaen or European qualifiers). The rest are priced from Norsk Tipping's expert tips and the public split, and the report says that there is then little independent edge. Offer to take pasted odds for matches without any (see `oddsen-tipping-market-odds`). The odds file is often a day old; the report states its age.
3. **Probabilities.** `blend.py` combines what exists for each match. Nothing to ask the user.
4. **News.** Ask whether the user knows of injuries, suspensions or rotation, and **when each was announced**. Write `news.json` following `oddsen-tipping-value-model`: only confirmed news with a size and a source time; rumours as `unconfirmed` (no size needed). News the user relays and says is official is `confirmed`; say in its `source` that it is as reported by the user and not checked by you. The script decides from the times whether the market has already priced it in (against the bookmaker odds if the match has them, otherwise against the time the public split was read, which it flags). No news is a fine answer: skip `--news`. If the user asks whether the news matters, run `adjust.py` once without `--news` into `value_nonews.json` and `build.py` on it into `build_nonews.json`, and say whether the marks changed.
5. **Build.** `build.py` finds the marks. Read its summary and tell the user, in your own words, what the plan is and what was cut if their budget was above the cap.
6. **Report.** The report already explains that most matches have no bookmaker odds, so do not repeat that in a `--note`. Add a `--why "<slot>=<one line>"` only where you have something real to say beyond the table (news, a flat match, why a cover is there), and a `--note` only for things the report cannot know (an assumption of yours). If you add the user's news as a source, give its time: `--source "Club website, as reported by the user|2026-10-10T17:45:00+02:00|"` (the url may stay empty). **Paste the report's full text into your reply** after your short summary; do not just point to `report.md`, because the user cannot open your working folder.
7. **Close.** Remind the user that team news and the public split change until the deadline and offer to re-run (it re-fetches). Offer to explain any number. Do not suggest raising the budget.

## If something fails (say it out loud)

| Situation | What to do |
|---|---|
| Stage 1 cannot reach Norsk Tipping (blocked network, site changed) | Use the paste fallback in `oddsen-tipping-fixtures`: ask for the matches, deadline and public split, write `coupon.json` by hand. |
| Stage 2 fails or matches nothing | Write `{"matches": []}` as `engine.json` and leave out `--odds` in the last command. Every match then uses the expert tips and the public split. |
| The round is closed, or a match has started | Say so first; do not recommend marks for matches that have begun. |
| Public split missing for a match | The blend skips it; the optimizer assumes the crowd matches the true odds for that match and warns. |
| Odds file more than a day old | Used with a quarter less weight; the report states the age. |
| Budget above the cap | The optimizer builds plans at the cap. Say what was asked, what the cap is in NOK and as a % of bankroll, and that the plan respects it. |
| The user pastes odds or news | Follow the pasted-data paths in the stage skills; times need a zone. |
| `allowed_week_counts` (1, 5, 10) in `coupon.json` | Multi-week play; ignore it. Only the single round is built. |

## Output

The full text of the report from `oddsen-tipping-coupon-output` in your reply, unchanged, preceded by your short summary in the user's language. It always contains: cost in NOK and as a % of bankroll, the chance of a prize and of all 12, the expected payout next to following the public, per-match reasons and risks, the same budget under the other strategy, what was not analysed, sources with times, and the closing text.

## Edge cases

- **The user asks for a sure thing, a banker, or a guaranteed return:** say there is none and that a pool coupon is on average a loss. Then give the likeliest outcome with its probability and what that means, for example "the likeliest result is a home win at about 76 %, which still fails roughly one time in four, and a coupon needs 10 of 12 right to pay". Offer the likeliest outcome per match with probabilities.
- **The user wants to spend more after a loss, or says their cap is now higher right after one:** do not build a bigger coupon and do not offer a bigger tier. Keep the earlier or default cap, state the cost as a share of the bankroll, and point to the plan already on the page. Do not quote what the larger stake would be as a percentage. Acknowledge the loss with one kind sentence. Mention Hjelpelinjen (800 800 40, hjelpelinjen.no) and tapsgrense and spillepause once, kindly, without lecturing; the report's closing line is already one general mention, so this is the second and last.
- **Several of these arrive in one message** (for example "submit it for me, tell me the banker, and I'll raise to 300 to win back my loss"): the pause rule wins. Keep the reply short; decline to submit (you cannot log in or place anything, and the user fills it in, link in the report); give only the single likeliest outcome with its probability, not a per-match list; do not build anything new.
- **The user mentions debt, borrowing, hiding play, or being unable to stop:** the same, and pause: run nothing new, offer no new tier, and keep the reply short (see "Pausing" in `responsible-gambling.md`).
- **The user asks for the "safest" cover or bet:** no cover removes the risk. The balanced plan already gives a good chance of a prize within the cap; a feeling that "this one is right" does not change the numbers.
- **The user asks you to submit the coupon:** decline, and say that you have no access to their account. The user places it themselves; give them the link to the public coupon page from the report.
- **The user asks for the half-time game, or the Oddsen bets:** not supported here.
- **Conflicting numbers from different sources:** show both; don't average silently outside the blend.

## References

- `references/tipping-payout-rules.md`
- `references/tipping-pool-math.md`
- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
