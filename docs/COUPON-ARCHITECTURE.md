# Tipping coupon builder: how it works

The user says "bygg kupongen for søndag, budsjett 50 kr, bankroll 3000 kr". The skills read the open round, estimate every match, build the marks and half/full covers (gardering) that fit the budget, and explain the result. Nothing needs to be pasted, no login, no API keys. The user fills the coupon in themselves.

This document describes what is built (plugin 0.7). The decisions behind it, with the evidence, are in the second half.

## Pipeline

Every stage is a script in its own skill; each reads the previous stage's file.

```
fetch_coupon.py ──> coupon.json ─────────────────────────────────────────────┐
      │                                                                       │
      └─> fetch_odds.py ──> odds.json ──> engine.py ──> engine.json           │
                                                │                             │
                          blend.py <────────────┴──── coupon.json             │
                              │                                               │
                          blend.json ──> adjust.py [--news news.json] ──> value.json
                                                                              │
                          build.py --value value.json --coupon coupon.json ───┤
                              │                                               │
                          build.json ──> render.py --build --value --coupon --odds ──> report.md
```

| Stage | Skill | What it does |
|---|---|---|
| 1 | `tippekupong-fixtures` | One GET of the data feed Norsk Tipping's own Tipping page uses: the open rounds (Saturday, Sunday, midweek) with 12 matches each, kick-offs, deadline, pool so far, **row price (1.00 NOK)**, the **public split** and Norsk Tipping's **expert split** per match. A second GET for last week's comparable round gives an estimate of the final turnover. |
| 2 | `tippekupong-odds` | One download of football-data.co.uk's `fixtures.csv`: 1X2 odds from up to seven bookmakers for the major leagues. Names are matched with accents and an alias table; anything unmatched is reported, never guessed. |
| 3 | `tippekupong-probabilities` | De-vigs each book (multiplicative by default), builds a consensus weighted by 1/margin, then `blend.py` mixes it with the expert and public splits. |
| 4 | `tippekupong-news` | Applies small, sourced, capped team-news adjustments, and decides from the times whether the market already priced the news in. |
| 5 | `tippekupong-optimizer` | Builds the coupon (see the payout model below). |
| 6 | `tippekupong-report` | The report. |
| - | `tippekupong` | The orchestrator: asks for the round, budget and bankroll, runs the commands, explains the result in the user's language. |

If a stage fails there is a fallback: a pasted coupon (written by hand into the same `coupon.json` shape), pasted odds, or no odds at all (then every match is priced from the expert and public splits).

## Data sources and what they cover

| Source | Gives | Does not give |
|---|---|---|
| Norsk Tipping public site data feed (`api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/...`) | Matches, kick-offs, deadline, pool, row price, public split, expert split, past rounds with turnover, winners and prizes | Odds; any information about the bonus pool |
| football-data.co.uk `fixtures.csv` | Multi-bookmaker 1X2 odds for the next few days in major leagues (English, German, Spanish, Italian, French, Dutch, ...) | Eliteserien, OBOS-ligaen, European qualifiers; a timestamp per odds (the file's last-modified time is used, often a day old) |

On the Sunday 11 October coupon that means 3 of 12 matches have bookmaker odds; the other 9 are priced from the expert and public splits alone. The report says so.

**Terms.** The feed is the website's own, undocumented, and can change or be blocked. Its `robots.txt` does not restrict the Tipping pages and sets no crawl delay; the terms page could not be read in full (it loads dynamically), so a clause on automated access is unchecked. The skills read it once per run, cache for 60 seconds as the server asks, send an honest User-Agent, and never log in. This should be confirmed with Norsk Tipping.

## The probability for each match

`blend.py` mixes the ingredients by availability (weights are judgement, printed in the output):

| Situation | market | expert | public |
|---|---|---|---|
| 2 or more bookmakers | 0.55 | 0.25 | 0.20 |
| one bookmaker | 0.40 | 0.30 | 0.30 |
| none | n/a | 0.50 | 0.50 |

Odds more than 24 hours old lose a quarter of their weight, then the weights are renormalised.

Evidence from 720 finished matches (60 rounds):

- Expert tips: log-loss 0.9375. Public split: 0.9424. Coin flip: 1.0986. An even mix: 0.9353. Both are well calibrated (a 60-69 % expert call came true 67 % of the time).
- The public is very slightly wrong in a predictable way: outcomes it rates under 25 % win about 14 % more often than it thinks (ratio 1.13 to 1.15); 55-64 % outcomes win less (0.85). Small, and not used directly.
- So for the matches with no odds there is **little independent edge**: the probability is mostly the crowd's own view.

## The payout model

Rules and evidence are in `shared/tipping-payout-rules.md`: prizes for 12, 11 **and 10** correct; 55 % of the turnover paid out; 27 / 27 / 31 % of that to the three tiers; prizes shared and rounded down to 5 kr; a tier-10 prize under 10 kr is cancelled and its pot goes to the other two tiers (15 of 60 rounds).

`build.py` computes the expected payout of a candidate system (a set of marks per match):

- for every possible result `o`, the other rows in each tier are Poisson with mean `turnover × c_k(o)`, where `c_k` comes from the public split treating tippers as independent per match (checked: actual winners over predicted had a median of 0.97 for 11 correct and 1.03 for 10 correct);
- tier 12 is summed exactly over the user's own rows; tiers 11 and 10 by Monte Carlo with the estimated true probabilities (5 000 samples to search, 100 000 independent samples for the reported numbers, so the search does not flatter itself);
- it runs in pure Python in a few seconds (numpy is not assumed).

**Strategies.** The search finds two systems per budget tier and shows both:

- `balanced` (the default): the highest expected payout among systems that keep at least 80 % of the best prize chance. Among nearly equally likely choices it prefers the outcomes fewer other tippers pick.
- `prize-chance`: the best chance of winning something, weighting tiers by typical prize sizes (exact, ignores the crowd).

Every plan is shown next to **following the public** (what the site's "Folket" button does) and **the coupon with the best chance of all 12**, with the same samples.

**What the numbers say (Sunday 11 Oct, 48 rows).** Following the public: about 0.35 kr back per kr staked. Best chance of all 12: 0.44. Balanced: 0.46 to 0.47. An average ticket: about 0.47 before the bonus pool. The honest conclusion: the crowd is quite efficient, a good coupon beats the *worst* way to play (copying the crowd) by about a third, and is roughly as good as an average ticket, not a profit. The report says that. The chance of winning something is about 10 to 17 % for 24 to 54 rows on a mixed coupon.

**Why there is no "maximise expected payout" strategy.** Maximising expected payout alone drifts to long shots and a coupon with about a 0.4 % chance of winning anything. Its payout is dominated by events that happen about once in thousands of rounds, so its standard error is above 15 %. In testing the plan found that way *looked* like 0.58 to 0.67 per kr on the samples it was searched on, and scored 0.39 to 0.44 on fresh samples, below the balanced plan (the optimizer's curse). It would be a lottery ticket sold with a number that cannot be trusted, so it is not offered.

## Guardrails

| Non-negotiable | Where |
|---|---|
| Stake shown as a share of the bankroll | Every plan's cost and % in the report; the cap (2 % by default) is applied by `build.py`, which cuts any over-cap budget and says so |
| No chasing losses | Orchestrator and output skill: no bigger coupon or tier after a loss; a cap raised in the same message as a loss does not count; "pause" defined in `responsible-gambling.md` |
| Show the math, never certain | Probabilities, public split, expected payout with its standard error, comparisons, "(analysed matches only)" where it applies; words like safe, certain, lock, banker are rejected in free text |
| Source and timestamp | Every source with a time, in Oslo time; stale odds weighted down and reported |
| No automation | Read-only fetches, no login, nothing posted; the report ends with a link to the public coupon page |

## Limits to keep in mind

- The expected payout assumes other tippers pick independently match by match. It is an average over many rounds; one round most likely pays nothing.
- The bonus pool (paid when one tipper is alone with 12 correct) is not modelled; it is upside.
- The final turnover is estimated from last week's comparable round; the result barely depends on it.
- Odds from the free file are often a day old; the public split moves until the deadline. Re-running re-fetches.
- Only the full-time game and single rounds are built, not the half-time game or multi-week play.

## Testing

- `python3 -m unittest discover -s tests` (173 tests). Notable: the payout rule must reproduce the prize per winner in 60 real rounds (`tests/fixtures/nt_history_60_rounds.json`); the crowd model must predict winner counts within a few per cent; the Monte Carlo evaluator must agree with full enumeration on small coupons; the whole chain runs as commands passing only files.
- Fresh-Claude test rounds (a subagent that sees only the unzipped skills) are saved in `docs/test-runs/`, together with the fixes each led to. Round 3 ran on live data from a bare Norwegian request.
- Not yet done: an installed-plugin test in Claude Code or Claude.ai (whether the skill triggers from its description, and whether Claude.ai's sandbox allows the network access the fetch steps need).

## Open questions

1. Terms of use for the data feed (above).
2. A Norwegian version of the report (`--lang no`).
3. A rating model for Eliteserien matches (`football-data.co.uk/new/NOR.csv` has five seasons of results): worth building only if it beats the expert-plus-public blend on the saved matches.
4. Whether the API exposes the bonus pool size.
