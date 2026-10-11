<!-- Logo: add docs/logo.png and uncomment.
<p align="center">
  <a href="https://github.com/arienshibani/tippekupong" rel="noopener">
    <img width="200px" height="200px" src="docs/logo.png" alt="Tippekupong logo">
  </a>
</p>
-->

<h3 align="center">Tippekupong 💸</h3>

<div align="center">

  [![skills.sh](https://skills.sh/b/arienshibani/tippekupong)](https://skills.sh/arienshibani/tippekupong)

</div>

---

<p align="center"> A Claude plugin for filling out Norsk Tipping betting slips 🎲
    <br>
    Tell it your budget. Get back a link to a pre-filled slip.
</p>

## About <a name = "about"></a>

**The math is deterministic**: payout rules, probabilities and the search for the best marks run as small Python scripts. **Claude does the judgement parts**: understanding your request, asking for budget and bankroll, checking team news, writing the short summary in Norwegian, and applying guardrails.


## 🏁 Getting Started <a name = "getting_started"></a>

With the [skills CLI](https://skills.sh)

```bash
npx skills add arienshibani/tippekupong
```

## 🎈 Usage <a name="usage"></a>
Ask for a coupon:

```
Bygg kupongen for søndag. Budsjett 50 kr, bankroll 3000 kr.
```

Within a minute Claude answers with a short summary and the full report. This is the real output, shortened, for Sunday 11 October 2026:

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

Here is your pre-filled betting slip 🔗 Open it, and login to purchase it

https://www.norsk-tipping.no/sport/tipping/spill?day=2&rows=%5BUB,HB,H,UB,H,B,H,H,B,HB,HUB,B%5D
```

The full report also has a reason and a risk note for every match, a second strategy for the same budget, a cheaper tier, and every source with its time.



## ⚙️ How It Works <a name = "how_it_works"></a>
1. **Fetch the round** from Norsk Tipping's public site data: matches, deadline, pool, row price (1 kr), the public split and the expert tips.
2. **Add bookmaker odds** from football-data.co.uk where its free file covers the match.
3. **Blend** odds, expert tips and the public split into one probability per match.
4. **Apply team news** you give it, checked against what the market already knew.
5. **Build the coupon** with the best expected payout across the prizes for 12, 11 and 10 correct, while keeping a good chance of winning something.
6. **Write the report** in the layout of the coupon page, with the pre-filled link.

Design and decisions: [docs/COUPON-ARCHITECTURE.md](docs/COUPON-ARCHITECTURE.md). Test rounds with a fresh Claude and the fixes they led to: [docs/test-runs/](docs/test-runs/).

## 🔧 Tests <a name = "tests"></a>
```bash
python3 -m unittest discover -s tests     # unit tests
python3 scripts/validate_skills.py        # skill frontmatter and layout
python3 scripts/sync_references.py        # after editing anything in shared/
./scripts/package-skills.sh               # zips into dist/
```

The tests include the payout rule checked against 60 real rounds, the crowd model against real winner counts, the Monte Carlo evaluator against full enumeration, and the whole chain from live-shaped data to report. Conventions for contributing are in [CLAUDE.md](CLAUDE.md); issues and pull requests are welcome.

## 🚀 Releases <a name = "releases"></a>
A GitHub release is published automatically when a new version lands on `main`: the workflow runs the checks, builds the zips, tags the version and uses the [changelog](CHANGELOG.md) as the notes. Each release attaches `tippekupong-plugin.zip` (the whole plugin) and one zip per skill. See [Releases](https://github.com/arienshibani/tippekupong/releases).


## ⛏️ Built Using <a name = "built_using"></a>
- [Claude Code](https://code.claude.com) - Plugin and skills runtime
- [Python 3](https://www.python.org/) - The maths, standard library only
- [Norsk Tipping](https://www.norsk-tipping.no/sport/tipping) - Public Tipping data: rounds, public split, expert tips, results
- [football-data.co.uk](https://www.football-data.co.uk/) - Free bookmaker odds
- [GitHub Actions](https://github.com/features/actions) - Tests and releases

---

**Play responsibly ✨**  Do not bet money you cannot afford to lose.
