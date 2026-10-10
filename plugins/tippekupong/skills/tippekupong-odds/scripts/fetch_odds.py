#!/usr/bin/env python3
"""Find bookmaker 1X2 odds for the matches on a Tipping coupon, from football-data.co.uk (free, no key).

Usage:
    python3 fetch_odds.py --coupon coupon.json [--day sunday] [--out odds.json] [--text]
    python3 fetch_odds.py --coupon coupon.json --fixtures-file fixtures.csv   # offline

Input: the JSON written by tippekupong-fixtures (fetch_coupon.py).
Output: probability-engine input, {"source", "max_age_hours", "matches": [{"slot", "label",
"quotes": [{"book", "odds": {"H","U","B"}, "fetched_at"}]}], "unmatched": [...], "notes": [...]}.

football-data.co.uk publishes upcoming fixtures with odds from several bookmakers (Bet365,
Betfred, BetVictor, Bwin, Paddy Power, SkyBet, Betfair Exchange) for the major leagues only. Matches
from other leagues (Norwegian lower leagues, European qualifiers, ...) are returned as
"unmatched": nothing is guessed. The file carries no per-odds timestamp, so each quote's
fetched_at is the file's Last-Modified time (often a day old); the output sets max_age_hours so
the engine keeps them and the age is reported honestly. One GET per run. Standard library only.
"""
import csv
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"
USER_AGENT = "tippekupong/0.7 (personal-use research tool; reads a public CSV once per run)"
TIMEOUT_SECONDS = 25
MAX_AGE_HOURS = 72  # kept this long, but the age is reported and the blend trusts old odds less
BOOKS = {"B365": "Bet365", "BFD": "Betfred", "BV": "BetVictor", "BW": "Bwin", "PP": "Paddy Power",
         "SKB": "SkyBet", "BFE": "Betfair Exchange"}
# (football-data notes: PP = Paddy Power, PS = Pinnacle, which the free fixtures file no longer carries)

# Norsk Tipping spelling -> football-data spelling (both normalised, see norm()).
ALIASES = {
    "manchester city": "man city", "manchester utd": "man united", "manchester united": "man united",
    "nottingham f": "nottm forest", "nottingham forest": "nottm forest", "nottingham": "nottm forest",
    "wolverhampton": "wolves", "wolverhampton wanderers": "wolves", "newcastle united": "newcastle",
    "tottenham hotspur": "tottenham", "spurs": "tottenham", "brighton hove albion": "brighton",
    "west ham united": "west ham", "leeds united": "leeds", "sheffield utd": "sheffield united",
    "sheffield wed": "sheffield weds", "west bromwich albion": "west brom", "hull city": "hull",
    "ipswich town": "ipswich", "norwich city": "norwich", "cardiff city": "cardiff",
    "brentford fc": "brentford", "wrexham afc": "wrexham", "swansea city": "swansea",
    "stoke city": "stoke", "coventry city": "coventry", "derby county": "derby",
    "preston north end": "preston", "blackburn rovers": "blackburn", "bolton wanderers": "bolton",
    "charlton athletic": "charlton", "birmingham city": "birmingham", "leicester city": "leicester",
    "queens park rangers": "qpr", "oxford united": "oxford", "bristol city": "bristol city",
    "luton town": "luton", "huddersfield town": "huddersfield", "plymouth argyle": "plymouth",
    "afc bournemouth": "bournemouth", "crystal palace": "crystal palace", "borussia dortmund": "dortmund",
    "bayern munchen": "bayern munich", "paris saint germain": "paris sg", "internazionale": "inter",
    "atletico madrid": "ath madrid", "athletic bilbao": "ath bilbao", "real sociedad": "sociedad",
}


# letters Unicode does not decompose into base letter + accent
TRANSLITERATE = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L"})


def norm(name):
    """Lower-case, strip accents and punctuation, apply the alias table."""
    text = unicodedata.normalize("NFKD", (name or "").translate(TRANSLITERATE))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text.replace("'", ""))
    text = re.sub(r"\s+", " ", text).strip()
    return ALIASES.get(text, text)


def _dt(date_text, time_text):
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            return datetime.strptime(f"{date_text} {time_text or '12:00'}", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _odds(row, prefix):
    try:
        h, d, a = (float(row[prefix + s]) for s in ("H", "D", "A"))
    except (KeyError, ValueError, TypeError):
        return None
    return {"H": h, "U": d, "B": a} if min(h, d, a) > 1.0 else None


def download(fetch=None):
    """Return (csv text, last_modified datetime or None). One GET, redirects followed."""
    request = urllib.request.Request(FIXTURES_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8-sig", errors="replace")
            modified = response.headers.get("Last-Modified")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f"could not download football-data.co.uk fixtures ({e})")
    return body, (parsedate_to_datetime(modified).astimezone(timezone.utc) if modified else None)


def find_matches(coupon_matches, csv_text, file_time):
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    index = {}
    for r in rows:
        when = _dt(r.get("Date"), r.get("Time"))
        if when:
            index.setdefault((norm(r.get("HomeTeam")), norm(r.get("AwayTeam"))), []).append((when, r))
    out, unmatched, notes = [], [], []
    for m in coupon_matches:
        key = (norm(m.get("home")), norm(m.get("away")))
        kickoff = datetime.fromisoformat(m["kickoff"]).astimezone(timezone.utc) if m.get("kickoff") else None
        candidates = [(w, r) for w, r in index.get(key, []) if kickoff is None or abs(w - kickoff) <= timedelta(hours=36)]
        if not candidates:
            unmatched.append({"slot": m["slot"], "label": m["label"], "league": m.get("league"),
                              "reason": "not in football-data.co.uk's upcoming fixtures"})
            continue
        _, row = min(candidates, key=lambda c: abs(c[0] - kickoff) if kickoff else timedelta(0))
        quotes = []
        for prefix, name in BOOKS.items():
            odds = _odds(row, prefix)
            if odds:
                quotes.append({"book": name, "odds": odds,
                               "fetched_at": file_time.isoformat(timespec="seconds") if file_time else None})
        if not quotes:
            unmatched.append({"slot": m["slot"], "label": m["label"], "league": m.get("league"),
                              "reason": "fixture found but no complete 1X2 odds"})
            continue
        out.append({"slot": m["slot"], "label": m["label"], "quotes": quotes})
    if file_time is None:
        notes.append("the file has no Last-Modified header, so the quotes are undated and will be flagged low confidence")
    return out, unmatched, notes


def build(coupon, csv_text, file_time, fetched_at, day="next"):
    coupons = coupon.get("coupons") or []
    if not coupons:
        raise ValueError("the coupon file has no coupons")
    if day not in ("next", "all"):
        picked = [c for c in coupons if c["day"].lower() == day.lower()]
        coupons = picked or coupons
    chosen = coupons[0]
    matches, unmatched, notes = find_matches(chosen["matches"], csv_text, file_time)
    age = None
    if file_time:
        age = round((datetime.fromisoformat(fetched_at) - file_time).total_seconds() / 3600, 1)
        if age > 24:
            notes.append(f"the odds file is {age:g} h old (last modified {file_time:%Y-%m-%d %H:%M} UTC); "
                         "league odds drift slowly but team news since then is not in them")
    return {
        "source": {"name": "football-data.co.uk fixtures.csv (free multi-bookmaker odds)", "url": FIXTURES_URL,
                   "fetched_at": fetched_at, "odds_file_last_modified": file_time.isoformat(timespec="seconds") if file_time else None,
                   "odds_age_hours": age, "method": "public-csv"},
        "max_age_hours": MAX_AGE_HOURS,
        "day": chosen["day"],
        "matches": matches,
        "unmatched": unmatched,
        "notes": notes,
    }


def to_text(result):
    lines = [f"{result['source']['name']}: odds file {result['source']['odds_age_hours']} h old"]
    for m in result["matches"]:
        books = ", ".join(f"{q['book']} {q['odds']['H']:g}/{q['odds']['U']:g}/{q['odds']['B']:g}" for q in m["quotes"][:3])
        lines.append(f"  {m['slot']:>2} {m['label']:<34} {len(m['quotes'])} books: {books} ...")
    for u in result["unmatched"]:
        lines.append(f"  {u['slot']:>2} {u['label']:<34} no odds ({u['reason']}; {u['league']})")
    lines += [f"note: {n}" for n in result["notes"]]
    return "\n".join(lines)


def main(argv):
    args, opts = argv[1:], {}
    flags = {"--text"}
    i = 0
    while i < len(args):
        if args[i] in ("--coupon", "--day", "--out", "--fixtures-file") and i + 1 < len(args):
            opts[args[i]] = args[i + 1]; i += 2
        elif args[i] in flags:
            opts[args[i]] = True; i += 1
        else:
            print(__doc__, file=sys.stderr); return 2
    if "--coupon" not in opts:
        print(__doc__, file=sys.stderr); return 2
    try:
        with open(opts["--coupon"], encoding="utf-8") as f:
            coupon = json.load(f)
        now = datetime.now(timezone.utc)
        if "--fixtures-file" in opts:
            with open(opts["--fixtures-file"], encoding="utf-8-sig") as f:
                text = f.read()
            import os
            file_time = datetime.fromtimestamp(os.path.getmtime(opts["--fixtures-file"]), timezone.utc)
        else:
            text, file_time = download()
        result = build(coupon, text, file_time, now.isoformat(timespec="seconds"), opts.get("--day", "next"))
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"error: {e}. Odds can be pasted instead (decimal H/U/B per match, with the time they were taken).",
              file=sys.stderr)
        return 1
    text_out = json.dumps(result, indent=2, ensure_ascii=False)
    if "--out" in opts:
        with open(opts["--out"], "w", encoding="utf-8") as f:
            f.write(text_out)
    print(to_text(result) if "--text" in opts else text_out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
