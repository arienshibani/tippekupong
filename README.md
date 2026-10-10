# Oddsen Skills

A shareable set of [Claude Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that help you find **value bets** on [Oddsen](https://www.norsk-tipping.no/sport/oddsen) (Norsk Tipping): bets where the odds offered are higher than the true probability of the outcome justifies.

The skills don't promise winners. They help you do the boring, disciplined parts well: turning odds into probabilities, comparing Oddsen against sharper markets, sizing stakes sensibly, and keeping an honest record of your results.

> **Status:** the Tipping coupon builder works end to end on live data (see below); the Oddsen value-bet skills in the roadmap are not built yet. Tested with fresh Claude sessions; not yet tried as an installed plugin in Claude.ai.

## What works today: build a Tipping coupon

Say "bygg kupongen for søndag, budsjett 50 kr, bankroll 3000 kr". The skills read the open round from Norsk Tipping's public data feed (no login, no key), add bookmaker odds where free ones exist, blend in Norsk Tipping's expert tips and the public split, apply any team news you give, and build the marks and half/full covers that give the best expected payout across the 12, 11 and 10-correct prizes. The report states the chance of winning a prize and the expected payout against following the public, and says plainly that a pool game pays out less than it takes in. You fill in the coupon yourself; nothing is placed for you. Rules and evidence: [shared/tipping-payout-rules.md](shared/tipping-payout-rules.md). Design and test history: [docs/COUPON-ARCHITECTURE.md](docs/COUPON-ARCHITECTURE.md), [docs/test-runs/](docs/test-runs/).

The data feed is an unofficial one the Norsk Tipping website itself uses; it can change or be blocked, and I could not read a clause on automated access in their terms. See the architecture doc for what is and is not checked.

## Install

### Claude Code (plugin marketplace)

```bash
/plugin marketplace add arienshibani/oddsen-skills
/plugin install oddsen@oddsen-skills
```

### Claude.ai / Claude desktop (upload a skill)

1. Download a skill zip from the [Releases](../../releases) page (or build it yourself, see below).
2. In Claude, go to **Settings → Capabilities → Skills** and upload the zip.

### Build the zips yourself

```bash
./scripts/package-skills.sh        # writes dist/<skill-name>.zip for every skill
```

Each zip is self-contained: the shared references in `shared/` are copied into every skill's `references/` folder at build time.

## Repository layout

```
.claude-plugin/marketplace.json     Marketplace manifest (Claude Code)
plugins/oddsen/
  .claude-plugin/plugin.json        Plugin manifest
  skills/<skill-name>/SKILL.md      One folder per skill
shared/                             References bundled into every skill
  odds-math.md                      Implied probability, margin, EV, Kelly
  oddsen-glossary.md                Oddsen / Norsk Tipping terms
  responsible-gambling.md           Guardrails every skill must follow
  tipping-payout-rules.md           How the Tipping prizes are paid (12/11/10 correct), with evidence
  tipping-pool-math.md              Pool maths and gardering
templates/SKILL.template.md         Starting point for a new skill
docs/ROADMAP.md                     Planned skills and open questions
docs/COUPON-ARCHITECTURE.md         How the Tipping coupon builder works
docs/test-runs/                     Fresh-Claude test reports and the fixes they led to
tests/                              python3 -m unittest discover -s tests
scripts/
  package-skills.sh                 Build uploadable zips into dist/
  validate_skills.py                Lint SKILL.md frontmatter and layout
```

## Contributing

Read [CLAUDE.md](CLAUDE.md) for conventions, then copy the template:

```bash
mkdir plugins/oddsen/skills/<skill-name>
cp templates/SKILL.template.md plugins/oddsen/skills/<skill-name>/SKILL.md
python3 scripts/validate_skills.py
```

## Play responsibly

You must be 18+ to play at Norsk Tipping. Only bet money you can afford to lose, and treat any edge as small and noisy. If gambling stops being fun, [Hjelpelinjen](https://hjelpelinjen.no) offers free, anonymous help (tel. 800 800 40). Norsk Tipping also lets you set your own loss limits and take breaks from your account settings.

## Disclaimer

This project is not affiliated with Norsk Tipping. Nothing here is financial advice. Odds, rules and limits change; always check Norsk Tipping's own pages before placing a bet.

## License

[MIT](LICENSE)
