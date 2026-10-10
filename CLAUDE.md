# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## What this repo is

A Claude Code plugin marketplace with one plugin, `oddsen`, containing skills that help users find value bets on Oddsen (Norsk Tipping). The same skills are also packaged as zips for upload to Claude.ai / Claude desktop.

## Conventions

- **One skill per folder:** `plugins/oddsen/skills/<skill-name>/SKILL.md`.
- **Naming:** kebab-case, prefixed `oddsen-` (e.g. `oddsen-value-check`). The folder name must equal the `name` in frontmatter.
- **Frontmatter:** only `name` and `description` are required. The description says *when* to use the skill in one or two sentences (max 1024 chars) and includes trigger words a user would actually type ("value bet", "Oddsen", "odds", "spill").
- **Keep SKILL.md lean** (< ~300 lines). Put long material in `references/` inside the skill folder and link to it. Put executable helpers in `scripts/` inside the skill folder.
- **Shared references** live in `/shared`. Reference them from a skill as `references/<file>.md`; the packaging script copies them in. Don't duplicate their content inside a skill.
- **Language:** write skills in English; keep Norwegian Oddsen terms (H/U/B, Over/Under, etc.) as they appear on the site, with the English meaning alongside.

## Non-negotiables for every skill

1. Follow `shared/responsible-gambling.md`. Every skill that recommends a bet must show the stake as a share of a user-defined bankroll and must never suggest chasing losses or raising stakes after a loss.
2. Show the math: implied probability, fair probability, edge and EV, so the user can check the reasoning.
3. Never present a bet as certain. Use "estimated edge", not "sure thing".
4. Cite the data source and its timestamp for any odds or fixtures fetched. Odds move; stale data is a common source of false "value".
5. Don't automate placing bets. Skills research and recommend; the user places bets themselves.

## Workflow for a new skill

1. Pick an item from `docs/ROADMAP.md` and move it to "In progress".
2. `mkdir plugins/oddsen/skills/<name> && cp templates/SKILL.template.md plugins/oddsen/skills/<name>/SKILL.md`
3. Write it, then run `python3 scripts/validate_skills.py`.
4. Build with `./scripts/package-skills.sh` and test the zip in Claude.ai, and the plugin in Claude Code.
5. Bump `version` in `plugins/oddsen/.claude-plugin/plugin.json` and update the roadmap.
