#!/usr/bin/env python3
"""Apply bounded, justified adjustments to fair probabilities and compare with the public split.

Usage:
    python3 adjust.py input.json            # JSON result on stdout
    python3 adjust.py input.json --text     # human-readable summary
    python3 adjust.py blend.json --news news.json   # add team news: {"<slot>": [adjustment, ...]}
    cat input.json | python3 adjust.py -    # read stdin

Input JSON (matches can be taken from the probability engine's "matches", plus q and adjustments):
    {
      "matches": [
        {"slot": 1, "label": "Home - Away",
         "p_fair": {"H": 0.51, "U": 0.27, "B": 0.22},
         "confidence": "ok",                       # from the engine: ok | low (optional)
         "spread_top_outcome": 0.01,               # from the engine (optional)
         "q": {"H": 0.62, "U": 0.20, "B": 0.18},   # public split (optional)
         "q_estimated": false,
         "user_approved": false,                   # true lifts the caps for this match
         "adjustments": [
           {"outcome": "H", "delta_pp": -3, "reason": "Top scorer out, announced 10:15",
            "source": "club site", "source_time": "2026-10-10T10:20:00Z",
            "status": "confirmed",                 # confirmed | unconfirmed
            "market_likely_priced_in": false}
         ]}
      ]
    }

Rules (docs/COUPON-ARCHITECTURE.md, stage 6):
  - every adjustment needs outcome, reason and source (and delta_pp, unless it is unconfirmed or
    priced in, which are never applied), or it is rejected;
  - "unconfirmed" and "market_likely_priced_in" adjustments are NOT applied; they become flags;
  - timing: if the match carries the engine's "books" (with fetched_at) and the adjustment has a
    source_time (ISO time WITH a zone) and no explicit market_likely_priced_in, the script decides:
    news at least 15 min before the earliest odds is priced in (not applied); news after the latest
    odds is new (applied); anything in between is too close to tell (not applied, flagged);
  - caps: |net delta| <= 5 pp per outcome and sum of |delta| <= 8 pp per match, unless the
    match has user_approved: true; over-cap requests are clamped and reported;
  - p_est = normalise(p_fair + deltas), each outcome floored at 1 %.
value_ratio = p_est / q, with q floored at 2 % and renormalised. Standard library only.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

OUTCOMES = ("H", "U", "B")
PER_OUTCOME_CAP_PP = 5.0
PER_MATCH_CAP_PP = 8.0
P_FLOOR = 0.01
Q_FLOOR = 0.02
RESCALE_TOL = 0.02
MANY_NEWS_ITEMS = 3
PRICED_IN_GAP = timedelta(minutes=15)
FRESH_NEWS = timedelta(minutes=30)


class InputError(ValueError):
    pass


def _probs(raw, where, floor=0.0):
    """Validate a H/U/B triple. Returns (fractions summing to 1, note or None).

    Accepts fractions, or percentages adding to about 100; anything within 2 % of the right
    total is divided by its total, and a note says so.
    """
    if not isinstance(raw, dict) or any(k not in raw for k in OUTCOMES):
        raise InputError(f"{where}: need H, U and B")
    vals = {k: float(raw[k]) for k in OUTCOMES}
    if any(v < 0 for v in vals.values()):
        raise InputError(f"{where}: negative probability")
    total = sum(vals.values())
    note = None
    if 98 <= total <= 102:
        note = f"given as percentages adding to {total:g} %"
        vals = {k: v / 100 for k, v in vals.items()}
        total /= 100
    if abs(total - 1.0) > RESCALE_TOL + 1e-9:
        raise InputError(f"{where}: H+U+B adds to {total:g}; give fractions such as 0.51 or "
                         "percentages that add to about 100")
    if abs(total - 1.0) > 1e-4:  # smaller gaps are just decimals rounded upstream
        note = (note + "; " if note else f"added to {total:.1%}; ") + "divided by the total"
    else:
        note = None  # clean percentages (or fractions) need no comment
    if floor:
        vals = {k: max(v, floor) for k, v in vals.items()}
        total = sum(vals.values())
    return {k: v / total for k, v in vals.items()}, note


def _time(text):
    """Aware UTC datetime from an ISO string with a zone, or None if missing/unreadable/zoneless."""
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def _timing(adj, books):
    """Classify news against the odds times: ('priced_in'|'ambiguous'|'new', minutes) or (None, None)."""
    st = _time(adj.get("source_time"))
    quotes = [q for q in (_time(b.get("fetched_at")) for b in books or []) if q]
    if not st or not quotes:
        return None, None
    earliest, latest = min(quotes), max(quotes)
    if st <= earliest - PRICED_IN_GAP:
        return "priced_in", round((earliest - st).total_seconds() / 60)
    if st > latest:
        return "new", round((latest - st).total_seconds() / 60)
    return "ambiguous", None


def _check_adjustment(adj):
    """Return (delta_pp or None, problem or None). delta_pp is optional for unconfirmed or priced-in news."""
    if adj.get("outcome") not in OUTCOMES:
        return None, "outcome must be H, U or B"
    if not str(adj.get("reason", "")).strip():
        return None, "no reason given"
    if not str(adj.get("source", "")).strip():
        return None, "no source given"
    never_applied = adj.get("market_likely_priced_in") or adj.get("status", "confirmed") != "confirmed"
    try:
        return float(adj["delta_pp"]), None
    except (KeyError, TypeError, ValueError):
        return (None, None) if never_applied else (None, "delta_pp missing or not a number")


def _clamp_to_caps(net):
    """Scale net per-outcome deltas into the caps. Returns (clamped, was_clamped)."""
    clamped = {k: max(-PER_OUTCOME_CAP_PP, min(PER_OUTCOME_CAP_PP, v)) for k, v in net.items()}
    total = sum(abs(v) for v in clamped.values())
    if total > PER_MATCH_CAP_PP:
        scale = PER_MATCH_CAP_PP / total
        clamped = {k: v * scale for k, v in clamped.items()}
    return clamped, any(abs(clamped[k] - net[k]) > 1e-12 for k in net)


def process_match(m, now):
    slot, label = m.get("slot"), m.get("label")
    if m.get("p_fair") is None:
        return {"slot": slot, "label": label, "status": "no_market", "p_est": None,
                "dropped": m.get("dropped") or []}
    p_fair, p_note = _probs(m["p_fair"], f"match {slot} p_fair")
    q, q_note = (None, None)
    if m.get("q") is not None:
        q, q_note = _probs(m["q"], f"match {slot} q", floor=Q_FLOOR)

    notes = []
    if p_note:
        notes.append(f"p_fair {p_note}")
    if q_note:
        notes.append(f"public split {q_note}")
    applied, rejected, flags, unconfirmed, fresh_seen = [], [], [], [], set()
    for adj in m.get("adjustments") or []:
        delta, problem = _check_adjustment(adj)
        entry = {k: adj.get(k) for k in ("outcome", "delta_pp", "reason", "source", "source_time")}
        timing, minutes = (None, None)
        if not problem and adj.get("market_likely_priced_in") is None and adj.get("status", "confirmed") == "confirmed":
            timing, minutes = _timing(adj, m.get("books"))
        if problem:
            rejected.append(dict(entry, why=problem))
        elif adj.get("market_likely_priced_in") or timing == "priced_in":
            why = "market likely priced this in"
            if timing == "priced_in":
                why = f"announced {minutes} min before the earliest odds were taken, so the market likely priced this in"
            rejected.append(dict(entry, why=why))
        elif timing == "ambiguous":
            rejected.append(dict(entry, why="announced too close to the odds times to tell whether the market had "
                                            "priced it in; not applied"))
            flags.append(f"{adj['outcome']}: news '{adj['reason']}' came within {PRICED_IN_GAP.seconds // 60} min of the "
                         "odds times; could not tell if it was priced in, so it is not applied")
        elif adj.get("status", "confirmed") != "confirmed":
            unconfirmed.append((adj["outcome"], delta, adj["reason"]))
            rejected.append(dict(entry, why="unconfirmed; recorded as a risk flag, not a number"))
        else:
            applied.append(dict(entry, delta_pp=delta))
            st = _time(adj.get("source_time"))
            read_at = _time(m.get("public_read_at"))
            if st and read_at and not m.get("books") and st <= read_at and ("split", adj.get("source"), st) not in fresh_seen:
                fresh_seen.add(("split", adj.get("source"), st))
                flags.append(f"news '{adj['reason']}' was announced {round((read_at - st).total_seconds() / 60)} min before the "
                             "public split was read, and this match has no bookmaker odds to compare with: the split may already "
                             "reflect the news, so the adjustment may double count")
            if st and timedelta(0) <= now - st < FRESH_NEWS and (adj.get("source"), st) not in fresh_seen:
                fresh_seen.add((adj.get("source"), st))
                notes.append(f"news '{adj['reason']}' is only {round((now - st).total_seconds() / 60)} min old; "
                             "the market may not have fully moved yet")
            if 0 < abs(delta) < 0.5:
                flags.append(f"{adj['outcome']} {delta:+g} pp is tiny: delta_pp is in percentage points "
                             "(3 means 3 pp, not 0.03); check the unit")

    if unconfirmed:
        what = ", ".join(f"{o} {d:+g} pp" if d is not None else o for o, d, _ in unconfirmed)
        why = "; ".join(dict.fromkeys(str(r) for _, _, r in unconfirmed))
        flags.append(f"unconfirmed team news, not applied: {what} ({why})")

    net = {k: sum(a["delta_pp"] for a in applied if a["outcome"] == k) for k in OUTCOMES}
    capped = False
    if not m.get("user_approved"):
        net, capped = _clamp_to_caps(net)
        if capped:
            flags.append(f"adjustments exceeded the caps ({PER_OUTCOME_CAP_PP:g} pp per outcome, "
                         f"{PER_MATCH_CAP_PP:g} pp per match) and were scaled down; "
                         "ask the user before using larger ones")

    raw = {k: max(p_fair[k] + net[k] / 100.0, P_FLOOR) for k in OUTCOMES}
    total = sum(raw.values())
    p_est = {k: raw[k] / total for k in OUTCOMES}

    reasons = []
    if m.get("confidence") == "low":
        reasons.extend(m.get("confidence_reasons") or
                       ["probability engine confidence was low (single book, disagreement or undated)"])
    notes.extend(m.get("notes") or [])
    if q is None:
        reasons.append("no public split")
    elif m.get("q_estimated"):
        reasons.append("public split is an estimate")
    items = {(a.get("source"), a.get("source_time")) for a in applied}
    if len(items) >= MANY_NEWS_ITEMS:
        reasons.append(f"{len(items)} news items applied")
    if applied:
        notes.append("news applied: " + ", ".join(f"{a['outcome']} {a['delta_pp']:+g} pp" for a in applied))
    if any(f.startswith("unconfirmed") for f in flags):
        reasons.append("unconfirmed team news")
    if capped:
        reasons.append("adjustments were capped")
    confidence = "high" if not reasons else "medium" if len(reasons) == 1 else "low"

    return {
        "slot": slot, "label": label, "status": "ok",
        "p_fair": {k: round(p_fair[k], 6) for k in OUTCOMES},
        "p_est": {k: round(p_est[k], 6) for k in OUTCOMES},
        "change_pp": {k: round((p_est[k] - p_fair[k]) * 100, 2) for k in OUTCOMES},
        "q": None if q is None else {k: round(q[k], 6) for k in OUTCOMES},
        "q_estimated": bool(m.get("q_estimated")),
        "value_ratio": None if q is None else {k: round(p_est[k] / q[k], 3) for k in OUTCOMES},
        "kickoff": m.get("kickoff"),
        "applied": applied, "rejected": rejected, "notes": notes,
        "split_note": q_note,
        "risk_flags": flags, "confidence": confidence, "confidence_reasons": reasons,
    }


def run(data):
    matches = data.get("matches") or []
    if not matches:
        raise InputError("matches is empty")
    now = _time(data["now"]) if data.get("now") else datetime.now(timezone.utc)
    if now is None:
        raise InputError("now needs a time zone (Z or an offset such as +02:00)")
    results, errors = [], []
    for m in matches:
        try:
            results.append(process_match(m, now))
        except InputError as e:
            errors.append(str(e))
    if errors:
        raise InputError("; ".join(errors))
    ok = [r for r in results if r["status"] == "ok"]
    return {
        "matches": results,
        "optimizer_matches": [
            dict({"slot": r["slot"], "label": r["label"], "p": r["p_est"]},
                 **({"q": r["q"], "q_estimated": r["q_estimated"]} if r["q"] else {}))
            for r in ok],
        "excluded": [{"slot": r["slot"], "label": r["label"], "reason": "no usable market",
                      "dropped": r.get("dropped") or []}
                     for r in results if r["status"] != "ok"],
    }


def to_text(result):
    lines = []
    for r in result["matches"]:
        head = f"{r['slot']:>2}  {r['label']}"
        if r["status"] != "ok":
            lines.append(f"{head}: NO USABLE MARKET")
            continue
        p = r["p_est"]
        lines.append(f"{head}: p_est H {p['H']:.1%} U {p['U']:.1%} B {p['B']:.1%}  "
                     f"confidence {r['confidence']}")
        if r["value_ratio"]:
            v = r["value_ratio"]
            tag = "estimated" if r["q_estimated"] else "observed"
            lines.append(f"      value ratio (p/q, q {tag}): H {v['H']}  U {v['U']}  B {v['B']}")
        for a in r["applied"]:
            lines.append(f"      applied {a['outcome']} {a['delta_pp']:+g} pp: {a['reason']} [{a['source']}]")
        for a in r["rejected"]:
            lines.append(f"      not applied {a['outcome']} {a['delta_pp']}: {a['why']}")
        for f in r["risk_flags"]:
            lines.append(f"      ! {f}")
        for why in r["confidence_reasons"]:
            lines.append(f"      confidence: {why}")
    return "\n".join(lines)


def merge_news(data, news):
    """Add adjustments from {"<slot>": [adjustment, ...]} to the matches with that slot."""
    if not isinstance(news, dict):
        raise InputError("the news file must be an object mapping slot numbers to lists of adjustments")
    by_slot = {str(k): v for k, v in news.items()}
    for m in data.get("matches") or []:
        extra = by_slot.pop(str(m.get("slot")), None)
        if extra:
            m["adjustments"] = list(m.get("adjustments") or []) + list(extra)
    if by_slot:
        raise InputError(f"news given for slot(s) {sorted(by_slot)} that are not on the coupon")
    return data


def main(argv):
    args, news_path, i, positional = argv[1:], None, 0, []
    while i < len(args):
        if args[i] == "--news" and i + 1 < len(args):
            news_path = args[i + 1]; i += 2
        elif args[i] == "--text":
            i += 1
        elif args[i].startswith("--"):
            print(__doc__, file=sys.stderr); return 2
        else:
            positional.append(args[i]); i += 1
    if len(positional) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if positional[0] == "-" else open(positional[0], encoding="utf-8").read()
        data = json.loads(raw)
        if news_path:
            with open(news_path, encoding="utf-8") as f:
                data = merge_news(data, json.load(f))
        result = run(data)
    except (InputError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(to_text(result) if "--text" in argv else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
