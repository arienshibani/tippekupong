#!/usr/bin/env python3
"""Read the open Tipping coupons from Norsk Tipping's public site API (no login, no key).

Usage:
    python3 fetch_coupon.py                       # the coupon with the nearest deadline, JSON
    python3 fetch_coupon.py --day sunday          # sunday | midweek | saturday | next | all
    python3 fetch_coupon.py --text                # short human-readable summary
    python3 fetch_coupon.py --file snapshot.json  # parse a saved response instead of fetching
    python3 fetch_coupon.py --out coupon.json     # also write the JSON to a file

What it does: one GET of the same anonymous endpoint the public Tipping page itself calls
(PoolGamesSportInfo tipping/live-info), cached on disk for 60 seconds as the server asks, and
at most one more GET for last week's comparable round (to estimate the final turnover). It
sends an honest User-Agent, never logs in, never posts anything. If the endpoint is unreachable
or changes shape, it exits with an error so the caller can fall back to a pasted coupon.

Output (JSON):
    {"source": {name, url, fetched_at, method}, "warnings": [...],
     "coupons": [{"day", "game_id", "status", "deadline", "row_price_nok", "turnover_nok",
                  "turnover_estimate_nok", "matches": [{"slot", "label", "home", "away", "league",
                  "kickoff", "public": {"H","U","B"}, "expert": {"H","U","B"}}]}]}
public/expert are fractions summing to 1 ("peoples" and "expert" tips for the full-time game).
Standard library only.
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping"
LIVE_URL = f"{BASE}/live-info"
RESULTED_URL = f"{BASE}/game/resulted-and-closest-before-date"
USER_AGENT = "oddsen-skills/0.7 (personal-use research tool; reads public pages once per run)"
CACHE_SECONDS = 60
TIMEOUT_SECONDS = 20
DAY_KEYS = {"sunday": "SUNDAY", "søndag": "SUNDAY", "midweek": "MIDWEEK", "midtuke": "MIDWEEK",
            "saturday": "SATURDAY", "lørdag": "SATURDAY"}


class FetchError(RuntimeError):
    pass


def _get_json(url, cache_name=None):
    """GET a JSON document, with a tiny on-disk cache so repeated runs stay polite."""
    path = os.path.join(tempfile.gettempdir(), f"oddsen-skills-{cache_name}.json") if cache_name else None
    if path and os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_SECONDS:
        with open(path, encoding="utf-8") as f:
            return json.load(f), True
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise FetchError(f"Norsk Tipping's API answered HTTP {e.code} for {url.split('?')[0]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise FetchError(f"could not reach Norsk Tipping's API ({e})")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise FetchError("Norsk Tipping's API did not return JSON (the site may have changed)")
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    return data, False


def _fractions(tip, where):
    try:
        h, d, a = float(tip["home"]), float(tip["draw"]), float(tip["away"])
    except (KeyError, TypeError, ValueError):
        raise FetchError(f"unexpected shape in {where}")
    total = h + d + a
    if total <= 0:
        raise FetchError(f"empty split in {where}")
    return {"H": h / total, "U": d / total, "B": a / total}


def _amount(node):
    try:
        return float(node["amount"])
    except (KeyError, TypeError, ValueError):
        return None


def parse_coupon(day_type, game):
    """Turn one gameDays[].game object into a coupon dict."""
    try:
        sales = game["sales"]["fullTime"]
        matches = game["matches"]
        tips = game["tips"]["fullTime"]
        row_price = _amount(game["product"]["rowPrice"])
        deadline = sales["saleStopDate"]
        turnover = _amount(sales["saleAmount"])
    except (KeyError, TypeError):
        raise FetchError(f"unexpected shape in the {day_type} game (the site may have changed)")
    if row_price is None or turnover is None:
        raise FetchError(f"missing row price or turnover in the {day_type} game")
    peoples, expert = tips.get("peoples") or [], tips.get("expert") or []
    out = []
    for i, m in enumerate(matches):
        teams = m.get("teams") or {}
        entry = {
            "slot": m.get("gameEngineSortingNumber", i + 1),
            "id": m.get("gameEngineEventId"),
            "betradar_id": m.get("gameEngineBetRadarId"),
            "label": m.get("name"),
            "home": (teams.get("home") or {}).get("webName"),
            "away": (teams.get("away") or {}).get("webName"),
            "league": (m.get("arrangement") or {}).get("name"),
            "kickoff": m.get("date"),
            "status": ((m.get("status") or {}).get("value")),
            "public": _fractions(peoples[i], f"{day_type} public split, match {i + 1}") if i < len(peoples) else None,
            "expert": _fractions(expert[i], f"{day_type} expert tips, match {i + 1}") if i < len(expert) else None,
        }
        out.append(entry)
    return {
        "day": day_type,
        "game_id": game.get("gameEngineBetObjectId"),
        "status": game.get("status"),
        "deadline": deadline,
        "row_price_nok": row_price,
        "turnover_nok": turnover,
        "turnover_estimate_nok": turnover,
        "turnover_estimate_basis": "turnover so far (still growing until the deadline)",
        "allowed_week_counts": (game.get("product") or {}).get("validDrawCounts"),
        "matches": out,
    }


def parse_live_info(data):
    games = data.get("gameDays")
    if not isinstance(games, list) or not games:
        raise FetchError("no gameDays in the response (the site may have changed)")
    return [parse_coupon(g.get("dayType"), g["game"]) for g in games if isinstance(g, dict) and g.get("game")]


def previous_round_turnover(coupon, fetch=_get_json):
    """Turnover of last week's comparable round, or None. One extra GET."""
    try:
        deadline = datetime.fromisoformat(coupon["deadline"])
        ask = (deadline - timedelta(days=7) + timedelta(hours=4)).isoformat(timespec="seconds")
        data, _ = fetch(f"{RESULTED_URL}?date={urllib.parse.quote(ask)}", None)
        stop = datetime.fromisoformat(data["sales"]["fullTime"]["saleStopDate"])
        # only trust it if it is the same weekday and roughly the same time of day
        if stop.weekday() != deadline.weekday() or abs((stop - deadline.replace(year=stop.year, month=stop.month, day=stop.day)).total_seconds()) > 4 * 3600:
            return None
        return _amount(data["sales"]["fullTime"]["saleAmount"])
    except (FetchError, KeyError, TypeError, ValueError):
        return None


def select(coupons, day, now):
    if day == "all":
        return coupons
    if day == "next":
        open_ = [c for c in coupons if c["status"] == "OPENED"]
        pool = open_ or coupons
        return [min(pool, key=lambda c: c["deadline"])] if pool else []
    key = DAY_KEYS.get(day.lower())
    if not key:
        raise FetchError(f"unknown day '{day}'; use sunday, midweek, saturday, next or all")
    return [c for c in coupons if c["day"] == key]


def build(raw, fetched_at, day="next", estimate_turnover=True, fetch=_get_json, now=None):
    now = now or datetime.now(timezone.utc)
    coupons = parse_live_info(raw)
    warnings = []
    chosen = select(coupons, day, now)
    if not chosen:
        raise FetchError(f"no '{day}' coupon in the response")
    for c in chosen:
        deadline = datetime.fromisoformat(c["deadline"])
        if c["status"] != "OPENED":
            warnings.append(f"{c['day']}: coupon status is {c['status']}, not OPENED")
        if deadline <= now:
            warnings.append(f"{c['day']}: the sale deadline {c['deadline']} has passed")
        if len(c["matches"]) != 12:
            warnings.append(f"{c['day']}: {len(c['matches'])} matches, expected 12 (check the rules)")
        started = [m["slot"] for m in c["matches"] if m["status"] not in (None, "NOT_STARTED")]
        if started:
            warnings.append(f"{c['day']}: match(es) {started} have started")
        for m in c["matches"]:
            if not m["public"]:
                warnings.append(f"{c['day']}: no public split for match {m['slot']}")
            if not m["expert"]:
                warnings.append(f"{c['day']}: no expert tips for match {m['slot']}")
        if estimate_turnover and c["status"] == "OPENED":
            previous = previous_round_turnover(c, fetch)
            if previous and previous > c["turnover_nok"]:
                c["turnover_estimate_nok"] = previous
                c["turnover_estimate_basis"] = "last week's comparable round (turnover so far is lower)"
    return {
        "source": {"name": "Norsk Tipping, Tipping (public site API, full-time game)", "url": LIVE_URL,
                   "fetched_at": fetched_at, "method": "public-api"},
        "warnings": warnings,
        "coupons": chosen,
    }


def to_text(result):
    lines = [f"Source: {result['source']['name']}, read {result['source']['fetched_at']}"]
    for c in result["coupons"]:
        lines.append("")
        lines.append(f"{c['day']} coupon #{c['game_id']}: deadline {c['deadline']}, row price {c['row_price_nok']:g} NOK, "
                     f"turnover so far {c['turnover_nok']:,.0f} NOK (estimate for final: {c['turnover_estimate_nok']:,.0f} NOK, "
                     f"{c['turnover_estimate_basis']})".replace(",", " "))
        for m in c["matches"]:
            p, e = m["public"], m["expert"]
            fmt = lambda d: "n/a" if not d else "/".join(f"{d[k]:.0%}" for k in ("H", "U", "B"))
            lines.append(f"  {m['slot']:>2} {m['label']:<34} {(m['league'] or ''):<22} {(m['kickoff'] or '')[5:16]}  "
                         f"public {fmt(p)}  expert {fmt(e)}")
    for w in result["warnings"]:
        lines.append(f"warning: {w}")
    return "\n".join(lines)


def main(argv):
    args = argv[1:]
    day, path, out, as_text = "next", None, None, "--text" in args
    i = 0
    while i < len(args):
        if args[i] == "--day" and i + 1 < len(args):
            day = args[i + 1]; i += 1
        elif args[i] == "--file" and i + 1 < len(args):
            path = args[i + 1]; i += 1
        elif args[i] == "--out" and i + 1 < len(args):
            out = args[i + 1]; i += 1
        elif args[i] not in ("--text", "--no-estimate"):
            print(__doc__, file=sys.stderr)
            return 2
        i += 1
    try:
        if path:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            fetched_at = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat(timespec="seconds")
            result = build(raw, fetched_at, day, estimate_turnover=False)
        else:
            raw, _ = _get_json(LIVE_URL, "live-info")
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            result = build(raw, fetched_at, day, estimate_turnover="--no-estimate" not in args)
    except (FetchError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}. Ask the user to paste the coupon (matches, deadline, public split) instead.", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    print(to_text(result) if as_text else text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
