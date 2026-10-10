# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## What this repo is

A Claude Code plugin marketplace with one plugin, `oddsen`, containing skills that help users find value bets on Oddsen (Norsk Tipping). The same skills are also packaged as zips for upload to Claude.ai / Claude desktop.

## Conventions

- **One skill per folder:** `plugins/oddsen/skills/<skill-name>/SKILL.md`.
- **Naming:** kebab-case, prefixed `oddsen-` (e.g. `oddsen-value-check`). The folder name must equal the `name` in frontmatter.
- **Tipping skills:** skills for Norsk Tipping's pool games (tippekupong, gardering) use the prefix `oddsen-tipping-` (e.g. `oddsen-tipping-coupon`). Design in `docs/COUPON-ARCHITECTURE.md`; payout rules and their evidence in `shared/tipping-payout-rules.md`; pool math in `shared/tipping-pool-math.md` (Kelly does not apply there; the budget is rows × row price).
- **Network use:** the Tipping skills read two public sources, once per run: Norsk Tipping's public site data feed and a football-data.co.uk CSV. No login, no keys, no cookies, no posting. A test (`tests/test_fetchers.py`) fails if the fetch script starts handling credentials. Read other sites only with the same restraint, and say where data came from.
- **Tests:** `python3 -m unittest discover -s tests` must pass. Fresh-Claude test runs (a subagent that only sees the unzipped skills) are saved in `docs/test-runs/`; do one after changing a SKILL.md or the pipeline contract.
- **Frontmatter:** only `name` and `description` are required. The description says *when* to use the skill in one or two sentences (max 1024 chars) and includes trigger words a user would actually type ("value bet", "Oddsen", "odds", "spill").
- **Keep SKILL.md lean** (< ~300 lines). Put long material in `references/` inside the skill folder and link to it. Put executable helpers in `scripts/` inside the skill folder.
- **Shared references** live in `/shared`. Reference them from a skill as `references/<file>.md`; the packaging script copies them in. Don't duplicate their content inside a skill.
- **Language:** write skills in English; keep Norwegian Oddsen terms (H/U/B, Over/Under, etc.) as they appear on the site, with the English meaning alongside.

## Non-negotiables for every skill

1. Follow `shared/responsible-gambling.md`. Every skill that recommends a bet must show the stake as a share of a user-defined bankroll and must never suggest chasing losses or raising stakes after a loss.
2. Show the math: implied probability, fair probability, edge and EV, so the user can check the reasoning.
3. Never present a bet as certain. Use "estimated edge", not "sure thing".
4. Cite the data source and its timestamp for any odds or fixtures fetched. Odds move; stale data is a common source of false "value".
5. Don't automate placing bets. Skills research and recommend; the user places bets themselves. For coupons, a copyable row summary or a link to the public coupon page satisfies this; never log in on the user's behalf.

## Workflow for a new skill

1. Pick an item from `docs/ROADMAP.md` and move it to "In progress".
2. `mkdir plugins/oddsen/skills/<name> && cp templates/SKILL.template.md plugins/oddsen/skills/<name>/SKILL.md`
3. Write it, then run `python3 scripts/validate_skills.py`.
4. Build with `./scripts/package-skills.sh` and test the zip in Claude.ai, and the plugin in Claude Code.
5. Bump `version` in `plugins/oddsen/.claude-plugin/plugin.json` and update the roadmap.
