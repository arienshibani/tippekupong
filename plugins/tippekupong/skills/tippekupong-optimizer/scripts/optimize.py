#!/usr/bin/env python3
"""Choose single marks and half/full covers for a Tipping pool coupon within a budget.

Usage:
    python3 optimize.py input.json            # JSON result on stdout
    python3 optimize.py input.json --text     # human-readable summary
    cat input.json | python3 optimize.py -    # read stdin

Input JSON:
    {
      "row_price_nok": 1.0,            # required (TO VERIFY against Norsk Tipping)
      "budget_nok": 100,               # required; base tier
      "max_budget_nok": 200,           # optional; adds a "max" tier
      "bankroll_nok": 2500,            # optional but recommended; with it, no tier is built above
      "cap_pct": 2,                    #   cap_pct % of the bankroll (default 2) and over-cap budgets are cut
      "risk": "balanced",              # safe | balanced | contrarian
      "matches": [
        {"slot": 1, "label": "Home - Away",
         "p": {"H": 0.55, "U": 0.25, "B": 0.20},       # estimated true probability
         "q": {"H": 0.70, "U": 0.18, "B": 0.12},       # public share; optional
         "q_estimated": false}                          # optional; true if q is a model
      ]
    }

Method (see shared/tipping-pool-math.md): for each match, the outcomes are ranked by
score = (1 - lam) * p + lam * p * (p / q). A cover of size n marks the top n outcomes.
P(coupon contains a fully correct row) = prod_i sum(p over marked outcomes in i), and
rows = prod_i n_i. Maximising P subject to rows <= budget / row_price is solved
exactly by dynamic programming over the row count. Probabilities may be fractions (0.51) or
percentages adding to about 100 (51/27/22); small rounding errors (98-102 %) are rescaled with a
note. Standard library only.
"""
import json
import math
import sys

OUTCOMES = ("H", "U", "B")
MARK = {"H": "H", "U": "U", "B": "B"}  # the letters on the coupon page
RISK_LAMBDA = {"safe": 0.0, "balanced": 0.5, "contrarian": 1.0}
Q_FLOOR = 0.02
RESCALE_TOL = 0.02


class InputError(ValueError):
    pass


def _probs(raw, where, floor=0.0):
    """Validate a H/U/B triple. Returns (fractions summing to 1, note or None).

    Accepts fractions, or percentages adding to about 100; anything that adds to within
    2 % of the right total is divided by its total, and a note says so.
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


def parse_input(data):
    """Validate and normalise the input. Returns (config, warnings)."""
    warnings = []
    try:
        price = float(data["row_price_nok"])
        budget = float(data["budget_nok"])
    except (KeyError, TypeError, ValueError):
        raise InputError("row_price_nok and budget_nok are required numbers")
    if price <= 0 or budget <= 0:
        raise InputError("row_price_nok and budget_nok must be positive")
    max_budget = data.get("max_budget_nok")
    if max_budget is not None:
        max_budget = float(max_budget)
        if max_budget < budget:
            raise InputError("max_budget_nok must be >= budget_nok")
    requested, cap_pct, bankroll, capped = budget, None, None, False
    if data.get("bankroll_nok") is not None:
        try:
            bankroll = float(data["bankroll_nok"])
            cap_pct = float(data.get("cap_pct", 2))
        except (TypeError, ValueError):
            raise InputError("bankroll_nok and cap_pct must be numbers")
        if bankroll <= 0 or cap_pct <= 0:
            raise InputError("bankroll_nok and cap_pct must be positive")
        cap_budget = bankroll * cap_pct / 100
        if cap_budget < price - 1e-9:
            raise InputError(f"a {cap_pct:g} % cap of {bankroll:g} NOK is {cap_budget:g} NOK, "
                             f"less than one row ({price:g} NOK)")
        if budget > cap_budget + 1e-9:
            warnings.append(f"requested budget {budget:g} NOK is {budget / bankroll:.1%} of the bankroll, above the "
                            f"{cap_pct:g} % cap; plans are built at the cap ({cap_budget:g} NOK)")
            budget, capped = cap_budget, True
        if max_budget is not None and max_budget > cap_budget + 1e-9:
            warnings.append(f"max budget {max_budget:g} NOK is above the cap; the max tier is built at the cap")
            max_budget = cap_budget
    risk = data.get("risk", "balanced")
    if risk not in RISK_LAMBDA:
        raise InputError(f"risk must be one of {sorted(RISK_LAMBDA)}")
    raw_matches = data.get("matches") or []
    if not raw_matches:
        raise InputError("matches is empty")

    matches, errors = [], []
    for idx, m in enumerate(raw_matches):
        slot = m.get("slot", idx + 1)
        label = m.get("label", f"Match {slot}")
        where = f"match {slot}"
        try:
            p, p_note = _probs(m.get("p"), f"{where} p")
            q, q_note = None, None
            if m.get("q") is not None:
                q, q_note = _probs(m["q"], f"{where} q", floor=Q_FLOOR)
        except InputError as e:
            errors.append(str(e))
            continue
        for note, what in ((p_note, "p"), (q_note, "public split")):
            if note:
                warnings.append(f"{where} ({label}): {what} {note}")
        if q is None:
            warnings.append(f"{where} ({label}): no public split; crowding unknown, so this match is chosen on hit chance only")
        if m.get("q_estimated"):
            warnings.append(f"{where} ({label}): public split is an estimate, not observed")
        matches.append({"slot": slot, "label": label, "p": p, "q": q})
    if errors:
        raise InputError("; ".join(errors))
    return {
        "row_price": price, "budget": budget, "max_budget": max_budget,
        "requested_budget": requested, "budget_capped": capped,
        "bankroll": bankroll, "cap_pct": cap_pct,
        "risk": risk, "lam": RISK_LAMBDA[risk], "matches": matches,
    }, warnings


def value_ratios(match):
    if match["q"] is None:
        return {k: 1.0 for k in OUTCOMES}
    return {k: match["p"][k] / match["q"][k] for k in OUTCOMES}


def ranked_outcomes(match, lam):
    """Outcomes best-first by score; ties broken by plain probability."""
    ratio = value_ratios(match)
    def score(k):
        p = match["p"][k]
        return ((1 - lam) * p + lam * p * ratio[k], p)
    return sorted(OUTCOMES, key=score, reverse=True)


def solve(matches, lam, max_rows):
    """Exact best covers: maximise prod(sum p) subject to prod(n_i) <= max_rows."""
    options = []  # per match: list of (n, outcomes, mass)
    for m in matches:
        order = ranked_outcomes(m, lam)
        options.append([
            (n, tuple(order[:n]), sum(m["p"][k] for k in order[:n])) for n in (1, 2, 3)
        ])
    # dp: rows -> (probability, choice tuple)
    dp = {1: (1.0, ())}
    for opts in options:
        nxt = {}
        for rows, (prob, choice) in dp.items():
            for n, outs, mass in opts:
                r2 = rows * n
                if r2 > max_rows:
                    continue
                cand = (prob * mass, choice + (outs,))
                if r2 not in nxt or cand[0] > nxt[r2][0] + 1e-15:
                    nxt[r2] = cand
        dp = nxt
    if not dp:
        raise InputError("budget does not cover a single row")
    best_rows = max(dp, key=lambda r: (dp[r][0], -r))
    prob, choice = dp[best_rows]
    return best_rows, prob, choice


def describe(matches, choice, rows, prob, price, tier, tier_budget):
    marks = []
    mean_vi = 1.0
    win_vi = 1.0
    for m, outs in zip(matches, choice):
        ratio = value_ratios(m)
        mass = sum(m["p"][k] for k in outs)
        mean_vi *= sum(ratio[k] for k in outs) / len(outs)
        win_vi *= sum(m["p"][k] * ratio[k] for k in outs) / mass
        marks.append({
            "slot": m["slot"], "label": m["label"],
            "outcomes": list(outs),
            "mark": "".join(MARK[k] for k in sorted(outs, key=OUTCOMES.index)),
            "cover": {1: "single", 2: "half", 3: "full"}[len(outs)],
            "p_covered": round(mass, 4),
            "value_ratio": {k: round(ratio[k], 3) for k in OUTCOMES},
        })
    has_q = any(m["q"] is not None for m in matches)
    return {
        "tier": tier,
        "tier_budget_nok": round(tier_budget, 2),
        "rows": rows,
        "cost_nok": round(rows * price, 2),
        "p_all_correct": prob,
        "one_in": round(1 / prob) if prob > 0 else None,
        "mean_row_value_index": round(mean_vi, 4) if has_q else None,
        "win_value_index": round(win_vi, 4) if has_q else None,
        "marks": marks,
    }


def optimize(data):
    cfg, warnings = parse_input(data)
    price = cfg["row_price"]
    caps = [("cheap", math.floor(round(cfg["budget"] * 0.5 / price, 9))),
            ("base", math.floor(round(cfg["budget"] / price, 9)))]
    if cfg["max_budget"] is not None and cfg["max_budget"] > cfg["budget"]:
        caps.append(("max", math.floor(round(cfg["max_budget"] / price, 9))))
    if caps[1][1] < 1:
        raise InputError("budget does not cover a single row")

    plans, seen = [], set()
    for tier, cap in caps:
        rows, prob, choice = solve(cfg["matches"], cfg["lam"], max(cap, 1))
        key = tuple(choice)
        if key in seen:  # tiers collapse when extra budget buys nothing
            warnings.append(f"tier '{tier}' identical to a cheaper tier; omitted")
            continue
        seen.add(key)
        plans.append(describe(cfg["matches"], choice, rows, prob, price, tier, cap * price))
    return {"risk": cfg["risk"], "row_price_nok": price, "budget_nok": cfg["budget"],
            "requested_budget_nok": cfg["requested_budget"], "budget_capped": cfg["budget_capped"],
            "bankroll_nok": cfg["bankroll"], "cap_pct": cfg["cap_pct"],
            "plans": plans, "warnings": warnings}


def to_text(result):
    lines = [f"risk={result['risk']}  row price={result['row_price_nok']} NOK"]
    for plan in result["plans"]:
        lines.append("")
        lines.append(
            f"[{plan['tier']}] {plan['rows']} rows, {plan['cost_nok']} NOK, "
            f"P(a fully correct row) = {plan['p_all_correct']:.2%} (about 1 in {plan['one_in']})"
        )
        if plan["mean_row_value_index"] is not None:
            lines.append(
                f"    mean row value index {plan['mean_row_value_index']}, "
                f"value index if it hits {plan['win_value_index']} (above 1 = less crowded)"
            )
        for m in plan["marks"]:
            lines.append(f"    {m['slot']:>2}  {m['mark']:<4} {m['cover']:<6} {m['label']}")
    for w in result["warnings"]:
        lines.append(f"warning: {w}")
    return "\n".join(lines)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
        result = optimize(json.loads(raw))
    except (InputError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(to_text(result) if "--text" in argv else json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
