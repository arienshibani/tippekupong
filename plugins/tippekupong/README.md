# tippekupong

Builds a Norsk Tipping **Tipping** coupon for you. Say "bygg kupongen for søndag, budsjett 50 kr, bankroll 3000 kr" and Claude reads the open round, estimates the 12 matches, and returns the boxes to tick (H, U, B, with half and full covers) for your budget, plus the chance of winning a prize and what the coupon is worth in expectation. You fill in the coupon yourself on Norsk Tipping's page. The plugin never places a bet, never logs in and never handles money.

The plugin contains seven skills and no agents, hooks or MCP servers. Start with `tippekupong`; it runs the others.

## What it runs and what it connects to

Everything runs on your machine as small Python 3 scripts (standard library only) that Claude starts with its shell tool. The scripts read and write files in a working folder.

Two scripts make network requests. Both are plain read-only GET requests, at most a few per run, and they send no information about you or your conversation:

| Script | Reads | Why |
|---|---|---|
| `tippekupong-fixtures/scripts/fetch_coupon.py` | `https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/...` (the data feed Norsk Tipping's own Tipping page uses) | The open round: matches, deadline, pool, row price, public split, expert tips, and last week's turnover |
| `tippekupong-odds/scripts/fetch_odds.py` | `https://www.football-data.co.uk/fixtures.csv` | Bookmaker odds for the matches that file covers |

They send a generic User-Agent (`tippekupong/0.7 ...`), no cookies and no credentials, and cache the Norsk Tipping response for 60 seconds. Norsk Tipping's feed is the website's own and not a published API; it can change or be blocked, and the plugin then asks you to paste the coupon instead. The plugin has no telemetry and keeps nothing outside the working folder.

## Privacy

The plugin does not collect, store or transmit personal data. The amounts you give (budget, bankroll) are used locally and appear only in the report Claude writes for you.

## Responsible use

A pool game pays out less than it takes in; an average ticket returns about 0.47 kr per kr staked, and the report says so. The skills cap a coupon at 2 % of the bankroll by default, refuse to build a bigger one after a loss, never call a match a sure thing, and point to Hjelpelinjen (800 800 40, hjelpelinjen.no). Not affiliated with Norsk Tipping. Not financial advice. You must be 18 to play.

More in the [repository README](https://github.com/arienshibani/tippekupong).
