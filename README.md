# Skills for lazy gamblers

The perfect Claude plugin for lazy gamblers.

## What this is 



## Install

Claude Code:

```bash
claude plugin marketplace add arienshibani/oddsen-skills
claude plugin install oddsen@oddsen-skills
```

The repo is private, so you need GitHub access. From a local clone, use the folder path instead of `arienshibani/oddsen-skills`. Then start a **new** Claude Code session.

Claude.ai: run `./scripts/package-skills.sh` and upload the seven zips from `dist/` under Settings → Capabilities → Skills. This needs code execution with network access, and I have not tested it there.

## Use it

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

Open the Sunday coupon here and tick the boxes: https://www.norsk-tipping.no/sport/tipping/spill?day=2

The report also has a reason and a risk note for every match, the same budget under a second strategy, a cheaper tier, and the sources with times.

## Other things to say

| You say | What happens |
|---|---|
| `Bygg kupongen for lørdag, 24 kr, bankroll 2000 kr` | Builds the Saturday round. `midtuke` builds the midweek round. |
| `Budsjett 100 kr, bankroll 3000 kr` | The 2 % cap is 60 kr, so it builds at the cap and tells you what it cut. |
| `Fredrikstads toppscorer ble meldt ute kl. 17:45` | Adjusts that match, unless the market already priced it in, and says which. |
| `Betyr nyheten noe?` | Re-runs without the news and tells you whether your marks changed. |
| `Kjør den på nytt` | Fetches fresh data; the public split moves until the deadline. |
| `Hvilken kamp er banker?` | There is none. It names the likeliest outcome and what that probability means. |
| `Jeg tapte sist, kan jeg øke til 300 kr?` | It keeps your cap, builds nothing bigger, and points you to Hjelpelinjen. |

## How it works

1. **Fetch the round** from Norsk Tipping's public site data: matches, deadline, pool, row price (1 kr), the public split and Norsk Tipping's expert tips.
2. **Add bookmaker odds** from football-data.co.uk where the free file covers the match (on Sunday, only the 3 Premier League matches).
3. **Blend** odds, expert tips and the public split into one probability per match.
4. **Apply team news** you give it, checked against what the market already knew.
5. **Build the coupon** that gives the best expected payout across the prizes for 12, 11 and 10 correct, while keeping a good chance of winning something. The prizes are shared, so it avoids results many other tippers also cover.
6. **Write the report** in the layout of the coupon page.

Prize rules, worked out from 60 finished rounds: [shared/tipping-payout-rules.md](shared/tipping-payout-rules.md). Design and test history: [docs/COUPON-ARCHITECTURE.md](docs/COUPON-ARCHITECTURE.md) and [docs/test-runs/](docs/test-runs/).

## Limits

- **A pool pays out less than it takes in.** An average ticket returns about 0.47 kr per kr staked. This tool avoids the worst way to play (copying the crowd, about 0.36) and aims for a decent chance of a prize. It does not beat the pool.
- **Little edge on most matches.** Eliteserien and OBOS-ligaen have no free bookmaker odds, so those matches rest on Norsk Tipping's own expert tips and the public split. The report says so.
- **The data feed is unofficial.** It is the one Norsk Tipping's website uses. It can change or be blocked, and I could not read a clause on automated access in their terms. If it fails, Claude asks you to paste the coupon instead. Nothing logs in and nothing is bought.
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
