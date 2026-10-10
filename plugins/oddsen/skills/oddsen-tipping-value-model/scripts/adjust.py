#!/usr/bin/env python3
"""Apply bounded, justified adjustments to fair probabilities and compare with the public split.

Usage:
    python3 adjust.py input.json            # JSON result on stdout
    python3 adjust.py input.json --text     # human-readable summary
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
  - every adjustment needs outcome, delta_pp, reason and source, or it is rejected;
  - "unconfirmed" and "market_likely_priced_in" adjustments are NOT applied; they become flags;
  - caps: |net delta| <= 5 pp per outcome and sum of |delta| <= 8 pp per match, unless the
    match has user_approved: true; over-cap requests are clamped and reported;
  - p_est = normalise(p_fair + deltas), each outcome floored at 1 %.
value_ratio = p_est / q, with q floored at 2 % and renormalised. Standard library only.
"""
import json
import sys

OUTCOMES = ("H", "U", "B")
PER_OUTCOME_CAP_PP = 5.0
PER_MATCH_CAP_PP = 8.0
P_FLOOR = 0.01
Q_FLOOR = 0.02
SUM_TOL = 0.01
MANY_ADJUSTMENTS = 3


class InputError(ValueError):
    pass


def _probs(raw, where, floor=0.0):
    if not isinstance(raw, dict) or any(k not in raw for k in OUTCOMES):
        raise InputError(f"{where}: need H, U and B")
    vals = {k: float(raw[k]) for k in OUTCOMES}
    if any(v < 0 for v in vals.values()):
        raise InputError(f"{where}: negative probability")
    total = sum(vals.values())
    if abs(total - 1.0) > SUM_TOL:
        raise InputError(f"{where}: H+U+B sums to {total:.3f}, expected 1")
    if floor:
        vals = {k: max(v, floor) for k, v in vals.items()}
        total = sum(vals.values())
    return {k: v / total for k, v in vals.items()}


def _check_adjustment(adj):
    """Return (delta_pp, None) if usable, or (None, reason)."""
    if adj.get("outcome") not in OUTCOMES:
        return None, "outcome must be H, U or B"
    try:
        delta = float(adj["delta_pp"])
    except (KeyError, TypeError, ValueError):
        return None, "delta_pp missing or not a number"
    if not str(adj.get("reason", "")).strip():
        return None, "no reason given"
    if not str(adj.get("source", "")).strip():
        return None, "no source given"
    return delta, None


def _clamp_to_caps(net):
    """Scale net per-outcome deltas into the caps. Returns (clamped, was_clamped)."""
    clamped = {k: max(-PER_OUTCOME_CAP_PP, min(PER_OUTCOME_CAP_PP, v)) for k, v in net.items()}
    total = sum(abs(v) for v in clamped.values())
    if total > PER_MATCH_CAP_PP:
        scale = PER_MATCH_CAP_PP / total
        clamped = {k: v * scale for k, v in clamped.items()}
    return clamped, any(abs(clamped[k] - net[k]) > 1e-12 for k in net)


def process_match(m):
    slot, label = m.get("slot"), m.get("label")
    if m.get("p_fair") is None:
        return {"slot": slot, "label": label, "status": "no_market", "p_est": None}
    p_fair = _probs(m["p_fair"], f"match {slot} p_fair")
    q = _probs(m["q"], f"match {slot} q", floor=Q_FLOOR) if m.get("q") is not None else None

    applied, rejected, flags = [], [], []
    for adj in m.get("adjustments") or []:
        delta, problem = _check_adjustment(adj)
        entry = {k: adj.get(k) for k in ("outcome", "delta_pp", "reason", "source", "source_time")}
        if problem:
            rejected.append(dict(entry, why=problem))
        elif adj.get("market_likely_priced_in"):
            rejected.append(dict(entry, why="market likely priced this in; not applied"))
        elif adj.get("status", "confirmed") != "confirmed":
            flags.append(f"unconfirmed: {adj['outcome']} {delta:+g} pp ({adj['reason']}); not applied")
            rejected.append(dict(entry, why="unconfirmed; recorded as a risk flag, not a number"))
        else:
            applied.append(dict(entry, delta_pp=delta))

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
        reasons.append("probability engine confidence was low (single book, disagreement or undated)")
    if q is None:
        reasons.append("no public split")
    elif m.get("q_estimated"):
        reasons.append("public split is an estimate")
    if len(applied) >= MANY_ADJUSTMENTS:
        reasons.append(f"{len(applied)} adjustments applied")
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
        "applied": applied, "rejected": rejected,
        "risk_flags": flags, "confidence": confidence, "confidence_reasons": reasons,
    }


def run(data):
    matches = data.get("matches") or []
    if not matches:
        raise InputError("matches is empty")
    results = [process_match(m) for m in matches]
    ok = [r for r in results if r["status"] == "ok"]
    return {
        "matches": results,
        "optimizer_matches": [
            dict({"slot": r["slot"], "label": r["label"], "p": r["p_est"]},
                 **({"q": r["q"], "q_estimated": r["q_estimated"]} if r["q"] else {}))
            for r in ok],
        "excluded": [{"slot": r["slot"], "label": r["label"], "reason": "no usable market"}
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
