#!/usr/bin/env python3
"""Blend market odds, Norsk Tipping's expert tips and the public split into one probability per match.

Usage:
    python3 blend.py --coupon coupon.json --engine engine_out.json [--day sunday] [--out p.json] [--text]

Inputs:
    --coupon   JSON from tippekupong-fixtures (each match has "public" and "expert" fractions)
    --engine   JSON from engine.py run on the odds from tippekupong-odds (or the user's
               pasted odds); matches without a usable market are simply absent or have p_fair null
Output: {"matches": [...]} in the shape tippekupong-news takes: slot, label, p_fair,
q (the public split), confidence, confidence_reasons, books, components and weights.

Why these ingredients. Tested on 720 finished Tipping matches (60 rounds, 2026): the expert tips
and the public split are both well calibrated (log-loss 0.9375 and 0.9424 against 1.0986 for
coin-flip), and a 50/50 blend scores best of the pair (0.9353). Bookmaker consensus is the
only fully independent signal, so it gets the biggest weight when there is one.

Weights (judgement, not fitted; they are printed in the output):
    market with >= 2 books  market .55  expert .25  public .20
    market with one book    market .40  expert .30  public .30
    no market               expert .50  public .50
When the market odds are more than 24 h old their weight is cut by a quarter first. Linear
pooling, renormalised. Standard library only.
"""
import json
import sys

OUTCOMES = ("H", "U", "B")
WEIGHTS = {
    "market_multi": {"market": 0.55, "expert": 0.25, "public": 0.20},
    "market_single": {"market": 0.40, "expert": 0.30, "public": 0.30},
    "crowd_only": {"expert": 0.50, "public": 0.50},
}
OLD_ODDS_HOURS = 24
OLD_ODDS_FACTOR = 0.75


def _pick_coupon(coupon, day):
    coupons = coupon.get("coupons") or []
    if not coupons:
        raise ValueError("the coupon file has no coupons")
    if day not in (None, "next", "all"):
        picked = [c for c in coupons if c["day"].lower() == day.lower()]
        if picked:
            return picked[0]
    return coupons[0]


def blend_match(match, engine_match, odds_age_hours):
    comps, reasons, notes = {}, [], []
    if match.get("expert"):
        comps["expert"] = match["expert"]
    if match.get("public"):
        comps["public"] = match["public"]
    n_books = 0
    if engine_match and engine_match.get("p_fair"):
        comps["market"] = engine_match["p_fair"]
        n_books = engine_match.get("n_books", 1)
    if not comps:
        return None
    if "market" in comps:
        table = dict(WEIGHTS["market_multi" if n_books >= 2 else "market_single"])
        kind = "market_multi" if n_books >= 2 else "market_single"
        if n_books < 2:
            reasons.append("only one bookmaker priced this match")
        if odds_age_hours is not None and odds_age_hours > OLD_ODDS_HOURS:
            table["market"] *= OLD_ODDS_FACTOR
            notes.append(f"market odds are {odds_age_hours:g} h old (their weight is cut by a quarter)")
        if engine_match.get("confidence") == "low" and n_books >= 2:
            reasons.append("bookmakers disagree or a quote is undated")
    else:
        table, kind = dict(WEIGHTS["crowd_only"]), "crowd_only"
        reasons.append("no bookmaker odds (expert tips and public split only)")
    table = {k: v for k, v in table.items() if k in comps}
    total = sum(table.values())
    weights = {k: v / total for k, v in table.items()}
    p = {o: sum(weights[k] * comps[k][o] for k in weights) for o in OUTCOMES}
    s = sum(p.values())
    p = {o: round(v / s, 6) for o, v in p.items()}
    confidence = "ok" if kind == "market_multi" and not reasons else "low"
    out = {
        "slot": match["slot"], "label": match["label"], "league": match.get("league"),
        "p_fair": p,
        "q": match.get("public"),
        "confidence": confidence, "confidence_reasons": reasons, "notes": notes,
        "weights": {k: round(v, 3) for k, v in weights.items()},
        "components": {k: {o: round(v[o], 4) for o in OUTCOMES} for k, v in comps.items()},
        "n_books": n_books,
    }
    if engine_match:
        for key in ("books", "spread_top_outcome"):
            if engine_match.get(key) is not None:
                out[key] = engine_match[key]
    if not match.get("public"):
        out["q"] = None
    return out


def build(coupon, engine, day=None):
    chosen = _pick_coupon(coupon, day)
    read_at = (coupon.get("source") or {}).get("fetched_at")
    by_slot = {m["slot"]: m for m in (engine.get("matches") or [])}
    age = (engine.get("source") or {}).get("odds_age_hours")
    out, skipped = [], []
    for m in chosen["matches"]:
        blended = blend_match(m, by_slot.get(m["slot"]), age)
        if blended is None:
            skipped.append({"slot": m["slot"], "label": m["label"], "reason": "no expert tips, public split or odds"})
        else:
            blended["public_read_at"] = read_at if m.get("public") else None
            blended["kickoff"] = m.get("kickoff")
            out.append(blended)
    return {"day": chosen["day"], "matches": out, "skipped": skipped}


def to_text(result):
    lines = [f"{result['day']} coupon: blended probabilities"]
    for m in result["matches"]:
        p = m["p_fair"]
        w = "/".join(f"{k} {v:.0%}" for k, v in m["weights"].items())
        lines.append(f"  {m['slot']:>2} {m['label']:<34} H {p['H']:.0%} U {p['U']:.0%} B {p['B']:.0%}   weights {w}   {m['confidence']}")
    for s in result["skipped"]:
        lines.append(f"  {s['slot']:>2} {s['label']}: skipped ({s['reason']})")
    return "\n".join(lines)


def main(argv):
    args, opts, i = argv[1:], {}, 0
    while i < len(args):
        if args[i] in ("--coupon", "--engine", "--day", "--out") and i + 1 < len(args):
            opts[args[i]] = args[i + 1]; i += 2
        elif args[i] == "--text":
            opts["--text"] = True; i += 1
        else:
            print(__doc__, file=sys.stderr); return 2
    if "--coupon" not in opts:
        print(__doc__, file=sys.stderr); return 2
    try:
        with open(opts["--coupon"], encoding="utf-8") as f:
            coupon = json.load(f)
        engine = {}
        if "--engine" in opts:
            with open(opts["--engine"], encoding="utf-8") as f:
                engine = json.load(f)
        result = build(coupon, engine, opts.get("--day"))
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if "--out" in opts:
        with open(opts["--out"], "w", encoding="utf-8") as f:
            f.write(text)
    print(to_text(result) if "--text" in opts else text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
