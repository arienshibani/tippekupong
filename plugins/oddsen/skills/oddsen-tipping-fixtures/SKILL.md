---
name: oddsen-tipping-fixtures
description: Reads this week's open Tipping coupons straight from Norsk Tipping's public site, with no login and no key: the 12 matches, kick-offs, deadline, pool size, row price, the public split ("folkets fordeling") and Norsk Tipping's expert tips. Use when the user asks what is on the kupong, wants this week's Tipping matches, or you need the coupon data to build one.
---

# Tipping fixtures

Fetches the open Tipping coupons (Saturday, Sunday and midweek) from the same anonymous endpoint Norsk Tipping's own Tipping page calls, and turns them into a clean `coupon.json` the rest of the pipeline reads. It replaces pasting the match list, deadline, row price and public split by hand.

## Before you start

- Read `references/responsible-gambling.md` and follow it.
- This reads a **public, undocumented endpoint** of Norsk Tipping's website (the site's own data feed), not a published developer API. Norsk Tipping's `robots.txt` does not restrict the Tipping pages, but I could not read a clause on automated access in their terms. So: one request per run (a second one for last week's comparable turnover), cached for 60 seconds, an honest user-agent, no login of any kind. Tell the user once that the data comes from there, and that they can paste the coupon instead if they prefer. It can change or be blocked without notice; if it fails, use the paste fallback below.
- Never ask for a login, BankID or cookies. Nothing is bought or posted.

## Inputs

| Input | Required | Default |
|---|---|---|
| Which round: `sunday`, `midweek`, `saturday`, `next` or `all` (also `midtuke`, `lørdag`, `søndag`) | no | `next`: the open round with the nearest deadline |

## Steps

1. Run the script from this skill's folder:

   ```bash
   python3 scripts/fetch_coupon.py --day next --out coupon.json --text
   ```

   `--text` prints a summary; `coupon.json` is what the later stages read. `--no-estimate` skips the extra request for last week's turnover.
2. Show the user the matches, the deadline in Oslo time and the pool size. Say the data's source and the time it was read (the file's `source.fetched_at`).
3. Read the warnings. Typical ones: the deadline has passed, the coupon is not open, a match has started, a public split is missing, or there are not 12 matches. Do not build a coupon for a closed round.
4. Hand `coupon.json` to the next stage (`oddsen-tipping-market-odds`, then `oddsen-tipping-probability-engine`).

## Output (`coupon.json`)

```json
{
  "source": {"name": "...", "url": "...", "fetched_at": "2026-10-10T16:26:03+00:00", "method": "public-api"},
  "warnings": [],
  "coupons": [{
    "day": "SUNDAY", "game_id": 69453, "status": "OPENED", "deadline": "2026-10-11T14:25:00+02:00",
    "row_price_nok": 1.0, "turnover_nok": 709717.0, "turnover_estimate_nok": 2621076.0,
    "turnover_estimate_basis": "last week's comparable round (turnover so far is lower)",
    "matches": [{"slot": 1, "label": "Lillestrøm - Molde", "home": "Lillestrøm", "away": "Molde",
                 "league": "NOR Eliteserien", "kickoff": "2026-10-11T19:15:00+02:00", "status": "NOT_STARTED",
                 "public": {"H": 0.39, "U": 0.24, "B": 0.37}, "expert": {"H": 0.31, "U": 0.29, "B": 0.40}}]
  }]
}
```

`public` is what other tippers are picking now (it moves until the deadline); `expert` is Norsk Tipping's expert split. Both are fractions that add to 1. The turnover grows until the deadline, which is why the final turnover is estimated from last week's round.

## Fallback: the user pastes the coupon

If the script fails (network blocked, the site changed, the user prefers not to use it), ask the user to paste the matches, the deadline, and the public split per match, plus the row price if they know it. Write a `coupon.json` in the shape above by hand: at minimum `source` (name `"pasted by user"`, `fetched_at`, method `"pasted"`), one coupon with `day`, `game_id` (any number), `status: "OPENED"`, `deadline`, `row_price_nok`, `turnover_nok`, `turnover_estimate_nok`, and `matches` with `slot`, `label`, `home`, `away`, `league`, `kickoff`, `public` (and `expert` if known). Percentages may be entered as fractions. Say the row price is unverified if the user is not sure; the real price is 1.00 NOK at the time of writing, according to the API.

## Edge cases

- **Network blocked** (for example in Claude.ai's sandbox): the script exits with a message saying so; use the paste fallback.
- **Closed or started round:** warn plainly; do not recommend marks for matches that have begun.
- **A match withdrawn or postponed:** the status field shows it; leave that match's mark to the user and say so.
- **Several rounds open:** `--day next` picks the nearest deadline; ask if the user meant another.
- **Public split changes:** it is a snapshot. Tell the user it can move before the deadline and offer to re-run.
- **Rules:** the payout rules are in `references/tipping-payout-rules.md`; do not restate them from memory.
- **`allowed_week_counts`** (1, 5, 10) is the multi-week option on the site. It is ignored here: only the single round is built.

## References

- `references/tipping-payout-rules.md`
- `references/oddsen-glossary.md`
- `references/responsible-gambling.md`
