#!/usr/bin/env python3
"""De-vig 1X2 odds from several bookmakers and build a consensus probability per match.

Usage:
    python3 engine.py input.json            # JSON result on stdout
    python3 engine.py input.json --text     # human-readable summary
    cat input.json | python3 engine.py -    # read stdin

Input JSON:
    {
      "method": "multiplicative",     # multiplicative | additive | power | shin
      "max_age_hours": 6,             # quotes older than this at run time are dropped
      "now": "2026-10-10T12:00:00Z",  # optional; defaults to the current UTC time (for tests)
      "matches": [
        {"slot": 1, "label": "Home - Away",
         "quotes": [
           {"book": "Pinnacle", "odds": {"H": 2.10, "U": 3.40, "B": 3.60},
            "fetched_at": "2026-10-10T11:30:00Z", "weight": 1.0}   # weight optional
         ]}
      ]
    }

Consensus weight of a quote is weight / max(margin, 0.01)^2, so low-margin (sharper) books
count more. The result's "optimizer_matches" can be merged with a public split and passed to
oddsen-tipping-coupon-optimizer. Standard library only. See shared/odds-math.md.
"""
import json
import math
import sys
from datetime import datetime, timezone

OUTCOMES = ("H", "U", "B")
METHODS = ("multiplicative", "additive", "power", "shin")
MARGIN_FLOOR = 0.01
SPREAD_LOW_CONFIDENCE = 0.05


class InputError(ValueError):
    pass


def implied(odds):
    return {k: 1.0 / odds[k] for k in OUTCOMES}


def booksum(odds):
    return sum(implied(odds).values())


def _multiplicative(pi, total):
    return {k: pi[k] / total for k in OUTCOMES}


def _additive(pi, total):
    shift = (total - 1.0) / len(OUTCOMES)
    p = {k: pi[k] - shift for k in OUTCOMES}
    if any(v <= 0 for v in p.values()):
        raise ValueError("additive de-vig gives a non-positive probability")
    return p


def _power(pi, total):
    lo, hi = 1.0, 30.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sum(v ** mid for v in pi.values()) > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    return {key: v ** k for key, v in pi.items()}


def _shin(pi, total):
    def probs(z):
        return {k: (math.sqrt(z * z + 4 * (1 - z) * pi[k] ** 2 / total) - z) / (2 * (1 - z))
                for k in OUTCOMES}
    lo, hi = 0.0, 0.99
    for _ in range(200):
        mid = (lo + hi) / 2
        if sum(probs(mid).values()) > 1.0:
            lo = mid
        else:
            hi = mid
    return probs((lo + hi) / 2)


_DEVIG = {"multiplicative": _multiplicative, "additive": _additive, "power": _power, "shin": _shin}


def devig(odds, method):
    """Return (fair probabilities summing to 1, method actually used, note or None)."""
    pi = implied(odds)
    total = sum(pi.values())
    if total <= 1.0 + 1e-9:
        return _multiplicative(pi, total), "multiplicative", \
            "no positive margin; normalised proportionally"
    try:
        p = _DEVIG[method](pi, total)
        used, note = method, None
    except ValueError as e:
        p, used, note = _multiplicative(pi, total), "multiplicative", f"{e}; used multiplicative"
    s = sum(p.values())
    return {k: v / s for k, v in p.items()}, used, note


def _parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _valid_odds(odds):
    try:
        return all(float(odds[k]) > 1.0 for k in OUTCOMES)
    except (KeyError, TypeError, ValueError):
        return False


def consensus_for_match(match, method, now, max_age_hours):
    notes, used_quotes, dropped = [], [], []
    for quote in match.get("quotes") or []:
        book = quote.get("book", "unknown")
        odds = quote.get("odds")
        if not _valid_odds(odds):
            dropped.append({"book": book, "reason": "incomplete or invalid H/U/B odds"})
            continue
        odds = {k: float(odds[k]) for k in OUTCOMES}
        fetched = quote.get("fetched_at")
        undated = fetched is None
        if not undated:
            try:
                age_h = (now - _parse_time(fetched)).total_seconds() / 3600
            except ValueError:
                dropped.append({"book": book, "reason": f"unreadable timestamp {fetched!r}"})
                continue
            if age_h > max_age_hours:
                dropped.append({"book": book, "reason": f"stale ({age_h:.1f} h old)"})
                continue
        margin = booksum(odds) - 1.0
        p, used, note = devig(odds, method)
        if note:
            notes.append(f"{book}: {note}")
        weight = float(quote.get("weight", 1.0)) / max(margin, MARGIN_FLOOR) ** 2
        used_quotes.append({"book": book, "p": p, "margin": margin, "weight": weight,
                            "fetched_at": fetched, "undated": undated, "method": used})
    if not used_quotes:
        return {"slot": match.get("slot"), "label": match.get("label"), "p_fair": None,
                "status": "no_market", "n_books": 0, "dropped": dropped, "notes": notes}

    total_w = sum(q["weight"] for q in used_quotes)
    p_fair = {k: sum(q["weight"] * q["p"][k] for q in used_quotes) / total_w for k in OUTCOMES}
    top = max(OUTCOMES, key=lambda k: p_fair[k])
    if len(used_quotes) > 1:
        vals = [q["p"][top] for q in used_quotes]
        spread = max(vals) - min(vals)
    else:
        spread = None
    reasons = []
    if len(used_quotes) == 1:
        reasons.append("single book")
    if spread is not None and spread > SPREAD_LOW_CONFIDENCE:
        reasons.append(f"books disagree by {spread:.1%} on {top}")
    if any(q["undated"] for q in used_quotes):
        reasons.append("undated quote")
    return {
        "slot": match.get("slot"), "label": match.get("label"),
        "status": "ok",
        "p_fair": {k: round(p_fair[k], 6) for k in OUTCOMES},
        "top_outcome": top,
        "n_books": len(used_quotes),
        "spread_top_outcome": None if spread is None else round(spread, 4),
        "confidence": "low" if reasons else "ok",
        "confidence_reasons": reasons,
        "books": [{"book": q["book"], "margin": round(q["margin"], 4),
                   "weight_share": round(q["weight"] / total_w, 3),
                   "fetched_at": q["fetched_at"], "method": q["method"]} for q in used_quotes],
        "dropped": dropped, "notes": notes,
    }


def run(data):
    method = data.get("method", "multiplicative")
    if method not in METHODS:
        raise InputError(f"method must be one of {METHODS}")
    max_age = float(data.get("max_age_hours", 6))
    now = _parse_time(data["now"]) if data.get("now") else datetime.now(timezone.utc)
    matches = data.get("matches") or []
    if not matches:
        raise InputError("matches is empty")
    results = [consensus_for_match(m, method, now, max_age) for m in matches]
    return {
        "method": method, "max_age_hours": max_age, "run_at": now.isoformat(),
        "matches": results,
        "optimizer_matches": [
            {"slot": r["slot"], "label": r["label"], "p": r["p_fair"]}
            for r in results if r["p_fair"] is not None],
        "excluded": [{"slot": r["slot"], "label": r["label"], "reason": "no usable market"}
                     for r in results if r["p_fair"] is None],
    }


def to_text(result):
    lines = [f"de-vig method: {result['method']}  run at {result['run_at']}  "
             f"(quotes older than {result['max_age_hours']:g} h dropped)"]
    for m in result["matches"]:
        head = f"{m['slot']:>2}  {m['label']}"
        if m["status"] == "no_market":
            lines.append(f"{head}: NO USABLE MARKET")
        else:
            p = m["p_fair"]
            sp = "n/a" if m["spread_top_outcome"] is None else f"{m['spread_top_outcome']:.1%}"
            lines.append(f"{head}: H {p['H']:.1%}  U {p['U']:.1%}  B {p['B']:.1%}  "
                         f"({m['n_books']} book(s), spread {sp}, confidence {m['confidence']})")
            for r in m["confidence_reasons"]:
                lines.append(f"      ! {r}")
        for d in m["dropped"]:
            lines.append(f"      dropped {d['book']}: {d['reason']}")
        for n in m["notes"]:
            lines.append(f"      note {n}")
    return "\n".join(lines)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
        result = run(json.loads(raw))
    except (InputError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(to_text(result) if "--text" in argv else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
