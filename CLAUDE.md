# CLAUDE.md

Guidance for Claude (and humans) working in this repository.

## What this repo is

A Claude Code plugin marketplace with one plugin, `tippekupong`, containing skills that build Norsk Tipping Tipping coupons from live data. The same skills are also packaged as zips for upload to Claude.ai / Claude desktop.

## Conventions

- **One skill per folder:** `plugins/tippekupong/skills/<skill-name>/SKILL.md`.
- **Naming:** kebab-case, prefixed `tippekupong` (the orchestrator is `tippekupong`; the others are `tippekupong-fixtures`, `tippekupong-odds`, ...). The folder name must equal the `name` in frontmatter. A future skill for Oddsen (a different Norsk Tipping product) would use its own prefix, not this one.
- **Tipping skills:** skills for Norsk Tipping's pool game (tippekupong, gardering). Design in `docs/COUPON-ARCHITECTURE.md`; payout rules and their evidence in `shared/tipping-payout-rules.md`; pool math in `shared/tipping-pool-math.md` (Kelly does not apply there; the budget is rows × row price).
- **Network use:** the Tipping skills read two public sources, once per run: Norsk Tipping's public site data feed and a football-data.co.uk CSV. No login, no keys, no cookies, no posting. A test (`tests/test_fetchers.py`) fails if the fetch script starts handling credentials. Read other sites only with the same restraint, and say where data came from.
- **Tests:** `python3 -m unittest discover -s tests` must pass. Fresh-Claude test runs (a subagent that only sees the unzipped skills) are saved in `docs/test-runs/`; do one after changing a SKILL.md or the pipeline contract.
- **Frontmatter:** only `name` and `description` are required. The description says *when* to use the skill in one or two sentences (max 1024 chars) and includes trigger words a user would actually type ("value bet", "Oddsen", "odds", "spill").
- **Keep SKILL.md lean** (< ~300 lines). Put long material in `references/` inside the skill folder and link to it. Put executable helpers in `scripts/` inside the skill folder.
- **Shared references** live in `/shared`. Reference them from a skill as `references/<file>.md`. A plugin install contains only `plugins/tippekupong/`, so each skill carries committed copies in its own `references/` folder: after editing anything in `/shared`, run `python3 scripts/sync_references.py` (CI and `tests/test_references.py` fail if a copy is missing or stale). Never edit a copy; edit `/shared`. Don't write the same content into a SKILL.md.
- **Language:** write skills in English; keep Norwegian Oddsen terms (H/U/B, Over/Under, etc.) as they appear on the site, with the English meaning alongside.

## Non-negotiables for every skill

1. Follow `shared/responsible-gambling.md`. Every skill that recommends a bet must show the stake as a share of a user-defined bankroll and must never suggest chasing losses or raising stakes after a loss.
2. Show the math: implied probability, fair probability, edge and EV, so the user can check the reasoning.
3. Never present a bet as certain. Use "estimated edge", not "sure thing".
4. Cite the data source and its timestamp for any odds or fixtures fetched. Odds move; stale data is a common source of false "value".
5. Don't automate placing bets. Skills research and recommend; the user places bets themselves. For coupons, a copyable row summary or a link to the public coupon page satisfies this; never log in on the user's behalf.

## Workflow for a new skill

1. Pick an item from `docs/ROADMAP.md` and move it to "In progress".
2. `mkdir plugins/tippekupong/skills/<name> && cp templates/SKILL.template.md plugins/tippekupong/skills/<name>/SKILL.md`
3. Write it, then run `python3 scripts/validate_skills.py`.
4. Build with `./scripts/package-skills.sh` and test the zip in Claude.ai, and the plugin in Claude Code.
5. Bump `version` in `plugins/tippekupong/.claude-plugin/plugin.json` and update the roadmap.

## Releases

A GitHub release is created automatically when a version without a tag lands on `main` (`.github/workflows/release.yml`; it runs the checks and tests, builds the zips, tags `vX.Y.Z` and attaches `tippekupong-plugin.zip` plus one zip per skill).

To release:

1. Write what changed under `## Unreleased` in `CHANGELOG.md`. Write for users: what they can now do or what was fixed.
2. `python3 scripts/release.py bump patch` (or `minor` / `major`). It dates the section and updates `plugin.json` and `marketplace.json` together.
3. Commit and push to `main`. The workflow publishes the release; the changelog section is the release notes.

Bump `minor` for a new skill or behaviour users will notice, `patch` for fixes. Never change the plugin `name`: installs are recorded under it.

## Commits in this repo

Claude may be credited as co-author here (this repo only). End commit messages made with Claude's help with:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```
