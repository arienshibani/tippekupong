# Norsk Tipping - Claude Skills 

Tell Claude your budget. It reads this week's Norsk Tipping **Tipping** round, does the maths, and hands back the exact boxes to tick. You place it yourself. nothing is bought for you.

## What this is

Most coupon advice is gut feeling, or a button that copies what everyone else picked. This is a plugin of small skills that do it properly: they read the real round, price every match, use the real prize rules, and tell you plainly what the coupon is worth, including when the answer is "not much".

The skills are small, composable, and each one works alone. They show their sources and their uncertainty. They never place a bet, never log in, and never tell you a match is a sure thing.

## Install

**1. Get the plugin** (Claude Code):

```bash
claude plugin marketplace add arienshibani/tippekupong
claude plugin install tippekupong@tippekupong
```

The repo is private, so you need GitHub access. From a local clone, use the folder path instead of `arienshibani/tippekupong`.

**2. Start a new Claude Code session.** Sessions that were already open do not pick up new plugins.

**3. Ask for a coupon.**

Claude.ai: run `./scripts/package-skills.sh` and upload the seven zips from `dist/` under Settings → Capabilities → Skills. This needs code execution with network access, and it is untested there.

## See it work

```
You:    Bygg kupongen for søndag. Budsjett 50 kr, bankroll 3000 kr.
```

Within a minute Claude answers with a short summary and the full report. This is the real output, shortened, for Sunday 11 October 2026 (round #69453, deadline 14:25):

```
Recommended: 48 rows, 48 NOK = 1.60 % of bankroll (cap 2 %)

Chance of winning a prize (10, 11 or 12 correct): 15 %, about 1 in 7.
All 12 correct: about 1 in 197.
Expected payout: about 20 NOK on 48 NOK staked (0.42 per NOK).
  Following the public with 48 rows:   0.36 per NOK
  Best chance of all 12 (48 rows):     0.41 per NOK
  An average ticket:                   about 0.47 per NOK

Copy into your own coupon (■ = tick the box):

                                              H  U  B
 1  Lillestrøm - Molde             Sø. 19:15  □  ■  ■
 2  Aalesund - Sarpsborg 08        Sø. 17:00  ■  □  ■
 3  Start - HamKam                 Sø. 17:00  ■  □  □
 4  Fredrikstad - Tromsø           Sø. 14:30  □  ■  ■
 5  Kongsvinger - Ranheim          Sø. 17:00  ■  □  □
 6  Lyn - Strømsgodset             Sø. 17:00  □  □  ■
 7  Odd - Bryne                    Sø. 17:00  ■  □  □
 8  Stabæk - Strømmen              Sø. 17:00  ■  □  □
 9  Sandnes Ulf - Haugesund        Sø. 17:00  □  □  ■
10  Liverpool - Manchester City    Sø. 17:30  ■  □  ■
11  Crystal Palace - Nottingham F  Sø. 15:00  ■  ■  ■
12  Hull - Everton                 Sø. 15:00  □  □  ■

H = hjemmeseier, U = uavgjort, B = borteseier. After you tick the boxes,
"Ditt system" on the page should say 48 rekker (48 kr).
```

Open the Sunday coupon and tick the boxes: https://www.norsk-tipping.no/sport/tipping/spill?day=2

The full report also has a reason and a risk note for every match, a second strategy for the same budget, a cheaper tier, and every source with its time.

### Other things to say

| You say | What happens |
|---|---|
| `Bygg kupongen for lørdag, 24 kr, bankroll 2000 kr` | Builds the Saturday round. `midtuke` builds the midweek round. |
| `Budsjett 100 kr, bankroll 3000 kr` | The 2 % cap is 60 kr, so it builds at the cap and tells you what it cut. |
| `Fredrikstads toppscorer ble meldt ute kl. 17:45` | Adjusts that match, unless the market already priced it in, and says which. |
| `Betyr nyheten noe?` | Re-runs without the news and tells you whether your marks changed. |
| `Kjør den på nytt` | Fetches fresh data; the public split moves until the deadline. |
| `Hvilken kamp er banker?` | There is none. It names the likeliest outcome and what that probability means. |
| `Jeg tapte sist, kan jeg øke til 300 kr?` | It keeps your cap, builds nothing bigger, and points you to Hjelpelinjen. |

## Why this exists

### The coupon page leaves all the thinking to you

**The problem.** Twelve matches, three boxes each, a deadline, and a budget. Most people go on feel, or use the "Folket" button.

**The fix.** `tippekupong` reads the round, estimates every match, and builds the marks and half and full covers that fit your budget. You get a grid that looks like the page.

### Copying the crowd is the worst way to play

**The problem.** The prize for each tier is shared among everyone with the same result. Picks the public loves are picks you share with the most people. On the Sunday round above, following the public is worth 0.36 kr per kr staked; the built coupon is worth 0.42.

**The fix.** The optimizer avoids results many others cover, and every report prints the comparison so you can see it.

> [!NOTE]
> The honest part: an average ticket returns about 0.47 per krone, and this coupon came in below that. A pool pays out less than it takes in. The plugin makes you play it better, not profitably.

### Everyone chases 12 correct

**The problem.** Twelve right is a 1 in 531 441 shot per row. Rows with 10 and 11 right pay too, and the 10-correct prize is cancelled in about one round in four when too many people share it.

**The fix.** `tippekupong-optimizer` models all three tiers with the payout rules reverse-engineered from 60 finished rounds (55 % of turnover paid out, 27 / 27 / 31 % to the tiers, rounded down to 5 kr, 10 kr minimum). The test suite re-checks that rule against the real prizes.

### AI tips love to sound sure

**The problem.** Ask a chatbot for a pick and you get confidence it has not earned.

**The fix.** There is no banker, and the plugin says so. It prints the chance of winning something and a standard error, flags matches with no bookmaker odds, caps a coupon at 2 % of your bankroll, and will not build a bigger one after a loss.

### You cannot check a black box

**The problem.** A number with no source is a guess.

**The fix.** Every source is listed with its time in Oslo time, stale odds are weighted down and flagged, and the 182 tests include the payout rule against 60 real rounds. Three test rounds with a fresh Claude that only saw the skills are in [docs/test-runs/](docs/test-runs/), with every fix they led to.

## Reference

You talk to the first one. The rest it uses, and each also works alone.

- **[tippekupong](plugins/tippekupong/skills/tippekupong/SKILL.md)**: asks for round, budget and bankroll, runs everything below, and explains the result in your language.
- **[tippekupong-fixtures](plugins/tippekupong/skills/tippekupong-fixtures/SKILL.md)**: reads the open rounds from Norsk Tipping's public site data: matches, deadline, pool, row price, public split and expert tips.
- **[tippekupong-odds](plugins/tippekupong/skills/tippekupong-odds/SKILL.md)**: finds bookmaker odds for the matches the free football-data.co.uk file covers, and flags the rest.
- **[tippekupong-probabilities](plugins/tippekupong/skills/tippekupong-probabilities/SKILL.md)**: strips the bookmaker margin and blends odds, expert tips and the public split into one probability per match.
- **[tippekupong-news](plugins/tippekupong/skills/tippekupong-news/SKILL.md)**: applies team news within strict caps and checks it against what the market already knew.
- **[tippekupong-optimizer](plugins/tippekupong/skills/tippekupong-optimizer/SKILL.md)**: builds the marks and covers for the best expected payout over the 12, 11 and 10-correct prizes.
- **[tippekupong-report](plugins/tippekupong/skills/tippekupong-report/SKILL.md)**: writes the report in the coupon page's layout, with reasons, risks, cost as a share of your bankroll and the comparison.

Prize rules and evidence: [shared/tipping-payout-rules.md](shared/tipping-payout-rules.md). How it all fits: [docs/COUPON-ARCHITECTURE.md](docs/COUPON-ARCHITECTURE.md).

## Limits

- **Little edge on most matches.** Eliteserien and OBOS-ligaen have no free bookmaker odds, so those rest on Norsk Tipping's expert tips and the public split. On Sunday that was 9 of 12 matches. The report says so.
- **The data feed is unofficial.** It is the one Norsk Tipping's website uses. It can change or be blocked, and I could not read a clause on automated access in their terms. If it fails, Claude asks you to paste the coupon instead.
- **Free odds can be a day old.** The report shows their age.

## Develop

```bash
python3 -m unittest discover -s tests     # 182 tests
python3 scripts/validate_skills.py
python3 scripts/sync_references.py        # after editing anything in shared/
./scripts/package-skills.sh               # zips into dist/
```

Conventions are in [CLAUDE.md](CLAUDE.md).

## Play responsibly

You must be 18 to play. Only play money you can afford to lose. If gambling stops being fun, [Hjelpelinjen](https://hjelpelinjen.no) offers free, anonymous help (800 800 40), and Norsk Tipping lets you set a loss limit (tapsgrense) or take a break (spillepause) in your account.

Not affiliated with Norsk Tipping. Not financial advice. Rules and odds change; check Norsk Tipping's own pages. [MIT license](LICENSE).
