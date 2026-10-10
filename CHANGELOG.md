# Changelog

Releases are made by `.github/workflows/release.yml` when a new version lands on `main`. To release: write the entries under "Unreleased", then run `python3 scripts/release.py bump patch` (or `minor`, `major`).

## Unreleased

## 0.7.1 - 2026-10-11

First public release.

### What it does

- Builds a Norsk Tipping **Tipping** coupon from a request like "bygg kupongen for søndag, budsjett 50 kr, bankroll 3000 kr": reads the open round, estimates all 12 matches, and returns the H/U/B boxes to tick, with half and full covers, in the layout of the coupon page.
- Optimises expected payout across the prizes for 12, 11 and 10 correct, using payout rules worked out from 60 finished rounds (`shared/tipping-payout-rules.md`), and shows the comparison with following the public.
- Reads Norsk Tipping's public site data and football-data.co.uk bookmaker odds; no login, no keys. Matches without free odds are priced from Norsk Tipping's expert tips and the public split, and the report says so.
- Applies team news within strict caps and checks it against what the market already knew.
- Guardrails: 2 % bankroll cap, nothing bigger after a loss, no "banker", never places a bet.
- Seven skills in one plugin: `tippekupong`, `tippekupong-fixtures`, `tippekupong-odds`, `tippekupong-probabilities`, `tippekupong-news`, `tippekupong-optimizer`, `tippekupong-report`.

### Fixed

- Three skill descriptions contained an unquoted colon and space, which strict YAML parsers reject; the skills.sh CLI skipped those skills. Reworded, and the validator now catches it.

### Added

- Plugin-level README and LICENSE, with a disclosure of the two hosts the scripts read.

## 0.7.0 and earlier

Development versions, not released.
