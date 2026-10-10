---
name: oddsen-tipping-market-odds
description: Finds bookmaker 1X2 odds for the matches on a Tipping kupong from the free football-data.co.uk fixtures file (Premier League, Championship and other major leagues; no key, no login) and flags matches it cannot price. Use when the user wants market odds for a coupon, or before building a Tipping coupon, or asks which matches have bookmaker odds.
---

# Tipping market odds

Looks up the bookmakers' pre-match odds for the coupon's matches in football-data.co.uk's public `fixtures.csv` (Bet365, Betfred, BetVictor, Bwin, Paddy Power, SkyBet and the Betfair Exchange). The output goes straight into `oddsen-tipping-probability-engine`. Matches it cannot price are reported, never guessed.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- Read `references/odds-math.md` if the user asks what margin or de-vigging means.
- You need `coupon.json` from `oddsen-tipping-fixtures`.

## Inputs

| Input | Required | Default |
|---|---|---|
| `coupon.json` from `oddsen-tipping-fixtures` | yes | none |
| Odds the user pastes for matches the file does not cover (decimal H/U/B, one or more books, with the time taken) | no | none |

## Steps

1. Run the script from this skill's folder:

   ```bash
   python3 scripts/fetch_odds.py --coupon coupon.json --out odds.json --text
   ```

   One download of a public CSV. Offline: `--fixtures-file fixtures.csv`.
2. Read the summary. Matched matches show their books; `unmatched` lists the rest with a reason. On a typical round roughly a quarter to a half of the matches are matched: the file covers the major English, German, Spanish, Italian, French, Dutch, Belgian, Portuguese, Turkish, Greek and Scottish leagues, **not Eliteserien, OBOS-ligaen or European qualifiers**. That is expected.
3. Say how old the odds are: the file carries no timestamp per odds, so the script uses the file's last-modified time (often a day old). Odds more than 24 hours old are reported with a note, and the probability blend trusts them a quarter less.
4. For unmatched matches, offer to take pasted odds: add them to `odds.json` as `{"slot": N, "label": "...", "quotes": [{"book": "name", "odds": {"H": 2.1, "U": 3.4, "B": 3.5}, "fetched_at": "<ISO time with a zone>"}]}` in the `matches` list. Ask when they were taken; do not invent a time.
5. Run the engine on `odds.json`: `python3 <probability-engine>/scripts/engine.py odds.json > engine.json`. If nothing matched, the engine returns no matches and the blend falls back to the expert tips and the public split for every match.

## Output (`odds.json`)

```json
{
  "source": {"name": "football-data.co.uk fixtures.csv ...", "url": "...", "fetched_at": "...",
             "odds_file_last_modified": "2026-10-09T09:20:28+00:00", "odds_age_hours": 31.1, "method": "public-csv"},
  "max_age_hours": 72,
  "matches": [{"slot": 10, "label": "Liverpool - Manchester City",
               "quotes": [{"book": "Bet365", "odds": {"H": 2.7, "U": 3.6, "B": 2.45}, "fetched_at": "2026-10-09T09:20:28+00:00"}]}],
  "unmatched": [{"slot": 1, "label": "Lillestrøm - Molde", "league": "NOR Eliteserien", "reason": "not in football-data.co.uk's upcoming fixtures"}],
  "notes": ["the odds file is 31.1 h old ..."]
}
```

## Edge cases

- **Team names differ between sources:** the script normalises accents (including ø, æ) and uses an alias table (Manchester City = Man City, Nottingham F = Nott'm Forest, ...). A match whose names do not map is reported as unmatched, not matched to the wrong fixture. If you see a match that should have odds but does not, tell the user which names failed.
- **Fixture date mismatch:** a fixture more than 36 hours from the coupon's kick-off is not matched (the same pair can play twice a season).
- **Missing cells:** a book with an empty cell for a match is skipped for that match.
- **Download fails:** the script exits with a message; carry on without odds (the blend then uses the expert tips and the public split) and say so.
- **Column labels:** `PP` in the file is Paddy Power, not Pinnacle (football-data's notes say so); the script labels it correctly.

## References

- `references/odds-math.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
