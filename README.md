_A claude plugin for filling out Norsk Tipping betting slips_ 🎲

[![skills.sh](https://skills.sh/b/arienshibani/tippekupong)](https://skills.sh/arienshibani/tippekupong)


# Tippekupong

The math is deterministic: payout rules, probabilities, the search for the best marks, etc. **Claude does the judgement parts.** understanding your request, asking for budget and bankroll, checking team news, writing the short summary in Norwegian, and applying guardrails.


## Install

**1. Get the plugin.** In Claude Code:

```bash
claude plugin marketplace add arienshibani/tippekupong
claude plugin install tippekupong@tippekupong
```

Or with the [skills CLI](https://skills.sh), which installs the skills for Claude Code and other agents:

```bash
npx skills add arienshibani/tippekupong
```

**2. Start a new Claude Code session.** Sessions that were already open do not pick up new plugins.

## Usage

```
"Bygg kupongen for søndag. Budsjett 50 kr, bankroll 3000 kr."
```

Within a minute Claude answers with a short summary and the full report.

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


Heres your pre-filled betting slip 🔗 
https://www.norsk-tipping.no/sport/tipping/spill?day=2&rows=%5BUB,HU,H,HB,H,B,H,H,B,HB,HUB,UB%5D
```
The full report also has a reason and a risk note for every match, a second strategy for the same budget, a cheaper tier, and every source with its time.

## Skills

The plugin currently contain the following skills:

- **[tippekupong](plugins/tippekupong/skills/tippekupong/SKILL.md)**: asks for round, budget and bankroll, runs everything below, and explains the result in your language.
- **[tippekupong-fixtures](plugins/tippekupong/skills/tippekupong-fixtures/SKILL.md)**: reads the open rounds from Norsk Tipping's public site data: matches, deadline, pool, row price, public split and expert tips.
- **[tippekupong-odds](plugins/tippekupong/skills/tippekupong-odds/SKILL.md)**: finds bookmaker odds for the matches the free football-data.co.uk file covers, and flags the rest.
- **[tippekupong-probabilities](plugins/tippekupong/skills/tippekupong-probabilities/SKILL.md)**: strips the bookmaker margin and blends odds, expert tips and the public split into one probability per match.
- **[tippekupong-news](plugins/tippekupong/skills/tippekupong-news/SKILL.md)**: applies team news within strict caps and checks it against what the market already knew.
- **[tippekupong-optimizer](plugins/tippekupong/skills/tippekupong-optimizer/SKILL.md)**: builds the marks and covers for the best expected payout over the 12, 11 and 10-correct prizes.
- **[tippekupong-report](plugins/tippekupong/skills/tippekupong-report/SKILL.md)**: writes the report in the coupon page's layout, with reasons, risks, cost as a share of your bankroll and the comparison.

Prize rules and evidence: [shared/tipping-payout-rules.md](shared/tipping-payout-rules.md). How it all fits: [docs/COUPON-ARCHITECTURE.md](docs/COUPON-ARCHITECTURE.md).


## Development

```bash
python3 -m unittest discover -s tests     # 182 tests
python3 scripts/validate_skills.py
python3 scripts/sync_references.py        # after editing anything in shared/
./scripts/package-skills.sh               # zips into dist/
```

Conventions are in [CLAUDE.md](CLAUDE.md).

## Play responsibly ✨

Do not bet money you can not afford to loose. Not affiliated with Norsk Tipping. Not financial advice. Rules and odds change; check Norsk Tipping's own pages. [MIT license](LICENSE).
