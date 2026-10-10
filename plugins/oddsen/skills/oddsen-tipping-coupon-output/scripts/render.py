#!/usr/bin/env python3
"""Render the final Tipping coupon recommendation as markdown.

Usage:
    python3 render.py input.json            # markdown on stdout
    python3 render.py input.json --json     # {"markdown", "warnings", "recommended_tier"}
    cat input.json | python3 render.py -    # read stdin

Input JSON:
    {
      "bankroll_nok": 5000,                       # required
      "cap_pct": 2,                               # optional; max coupon cost as % of bankroll
      "now": "2026-10-10T12:00:00Z",              # optional (defaults to current UTC time)
      "max_source_age_hours": 6,                  # optional
      "coupon": {"name": "...", "deadline_utc": "...", "url": "https://..."},   # url optional
      "optimizer_result": { ... output of oddsen-tipping-coupon-optimizer ... },
      "matches": [ ... "matches" from oddsen-tipping-value-model (status ok) ... ],
      "excluded": [ ... "excluded" from the value model / engine ... ],
      "sources": [{"name": "...", "url": "...", "fetched_at": "..."}],
      "why": {"1": "One-line reason for match 1"},     # optional, overrides the auto text
      "notes": ["free-text caveats from the analyst"]  # optional
    }

The recommended tier is the most expensive one that fits the cap (else the cheapest, with a
warning). Free text that calls a bet safe, certain or a lock is rejected. Standard library only.
"""
import json
import re
import sys
from datetime import datetime, timezone

OUTCOMES = ("H", "U", "B")
MARK = {"H": "1", "U": "X", "B": "2"}
RISK_LABEL = {"safe": "cautious (maximise the hit chance)",
              "balanced": "balanced", "contrarian": "contrarian (favour under-backed outcomes)"}
FORBIDDEN = re.compile(
    r"\b(safe|sure thing|certain|certainly|guarantee|guaranteed|lock|risk-free|banker|sikker|garantert)\b",
    re.IGNORECASE)
CLOSING = ("Estimated, not certain. A pool coupon has a takeout, so on average it loses money, and "
           "even a well-built coupon is unlikely to hit. Only play what you can afford to lose; "
           "never raise the budget to win back a loss. Help: Hjelpelinjen 800 800 40, hjelpelinjen.no.")


class InputError(ValueError):
    pass


def _time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _cell(text):
    return str(text).replace("|", "/").replace("\n", " ")


def _pct(x):
    return f"{x:.0%}"


def _triple(d):
    return "/".join(_pct(d[k]) for k in OUTCOMES) if d else "n/a"


def _one_in(n):
    return f"{n:,}".replace(",", " ")


def _check_text(label, text):
    hit = FORBIDDEN.search(text)
    if hit:
        raise InputError(f"{label} contains '{hit.group(0)}'; never present a bet as safe or certain. "
                         "Rephrase as an estimate.")


def _auto_why(plan_mark, match):
    parts = []
    for k in plan_mark["outcomes"]:
        bit = f"{MARK[k]} {_pct(match['p_est'][k])}" if match else MARK[k]
        if match and match.get("q"):
            ratio = match["value_ratio"][k]
            tag = "under-backed" if ratio >= 1.15 else "over-backed" if ratio <= 0.85 else "in line"
            bit += f" (public {_pct(match['q'][k])}, {tag})"
        parts.append(bit)
    return "; ".join(parts)


def _risk_text(match):
    if not match:
        return "no model data"
    bits = list(match.get("confidence_reasons") or [])
    return f"confidence {match['confidence']}" + (": " + ", ".join(bits) if bits else "")


def build(data):
    try:
        bankroll = float(data["bankroll_nok"])
    except (KeyError, TypeError, ValueError):
        raise InputError("bankroll_nok is required")
    if bankroll <= 0:
        raise InputError("bankroll_nok must be positive")
    cap_pct = float(data.get("cap_pct", 2))
    result = data.get("optimizer_result") or {}
    plans = result.get("plans") or []
    if not plans:
        raise InputError("optimizer_result has no plans")
    matches = {m["slot"]: m for m in data.get("matches") or [] if m.get("status", "ok") == "ok"}
    why = {str(k): v for k, v in (data.get("why") or {}).items()}
    notes = list(data.get("notes") or [])
    for slot, text in why.items():
        _check_text(f"why[{slot}]", str(text))
    for i, note in enumerate(notes):
        _check_text(f"notes[{i}]", str(note))

    now = _time(data["now"]) if data.get("now") else datetime.now(timezone.utc)
    coupon = data.get("coupon") or {}
    warnings = list(result.get("warnings") or [])

    for plan in plans:
        plan["pct_bankroll"] = plan["cost_nok"] / bankroll * 100
        plan["within_cap"] = plan["pct_bankroll"] <= cap_pct + 1e-9
    fitting = [p for p in plans if p["within_cap"]]
    rec = max(fitting, key=lambda p: p["cost_nok"]) if fitting else min(plans, key=lambda p: p["cost_nok"])
    if not fitting:
        warnings.append(
            f"Even the cheapest plan costs {rec['pct_bankroll']:.1f} % of the bankroll, above the "
            f"{cap_pct:g} % cap. Consider a smaller budget or skipping this coupon.")
    elif rec["tier"] != plans[-1]["tier"] and not plans[-1]["within_cap"]:
        warnings.append(f"The '{plans[-1]['tier']}' tier is above the {cap_pct:g} % cap and is not recommended.")

    if rec["rows"] == 3 ** len(rec["marks"]):
        warnings.append("This plan buys every possible row. It guarantees a winning row, not a profit: "
                        "the payout can be smaller than the cost.")

    deadline = None
    if coupon.get("deadline_utc"):
        deadline = _time(coupon["deadline_utc"])
        left = (deadline - now).total_seconds() / 3600
        if left <= 0:
            warnings.append("The coupon deadline has passed.")
        elif left < 1:
            warnings.append(f"Less than an hour to the deadline ({left * 60:.0f} min).")

    max_age = float(data.get("max_source_age_hours", 6))
    for s in data.get("sources") or []:
        if s.get("fetched_at"):
            age = (now - _time(s["fetched_at"])).total_seconds() / 3600
            if age > max_age:
                warnings.append(f"Source '{s.get('name')}' is {age:.1f} h old; odds and news may have moved.")
        else:
            warnings.append(f"Source '{s.get('name')}' has no timestamp.")

    lines = [f"# Tipping coupon recommendation{': ' + coupon['name'] if coupon.get('name') else ''}", ""]
    meta = [f"Row price {result.get('row_price_nok', '?')} NOK",
            f"Preference: {RISK_LABEL.get(result.get('risk'), result.get('risk'))}",
            f"Bankroll {bankroll:,.0f} NOK".replace(",", " ")]
    if deadline:
        meta.insert(0, f"Deadline {deadline:%Y-%m-%d %H:%M} UTC")
    lines += [" · ".join(meta), ""]
    if warnings:
        lines += ["\n>\n".join(f"> **Warning:** {w}" for w in warnings), ""]

    lines += [f"## Recommended: {rec['tier']} tier", "",
              f"- **{rec['rows']} rows, {rec['cost_nok']:g} NOK = {rec['pct_bankroll']:.2f} % of bankroll** "
              f"(cap {cap_pct:g} %)",
              f"- Estimated chance that the coupon contains a fully correct row: "
              f"**{rec['p_all_correct']:.2%}** (about 1 in {_one_in(rec['one_in'])})"]
    if rec.get("mean_row_value_index") is not None:
        lines.append(f"- Crowding: mean row value index {rec['mean_row_value_index']}, "
                     f"{rec['win_value_index']} for the rows most likely to hit "
                     "(above 1 means less crowded than their probability suggests)")
    lines += ["", "| # | Match | Mark | Cover | p (est) 1/X/2 | Public 1/X/2 | Why | Risk |",
              "|---|---|---|---|---|---|---|---|"]
    for pm in rec["marks"]:
        m = matches.get(pm["slot"])
        lines.append("| " + " | ".join(_cell(x) for x in [
            pm["slot"], pm["label"], f"**{pm['mark']}**", pm["cover"],
            _triple(m["p_est"]) if m else "n/a", _triple(m.get("q")) if m else "n/a",
            why.get(str(pm["slot"])) or _auto_why(pm, m), _risk_text(m)]) + " |")

    lines += ["", "Copy into your own coupon:", "", "```"]
    lines += [f"{pm['slot']:>2}  {pm['mark']:<4} {pm['label']}" for pm in rec["marks"]]
    lines += ["```"]
    excluded = data.get("excluded") or []
    if excluded:
        names = ", ".join(f"#{e['slot']} {e.get('label') or ''}".strip() for e in excluded)
        lines += ["", f"**Not covered by this plan (no usable market): {names}.** The coupon still "
                  "needs a mark for each. A single mark leaves the cost unchanged; a cover multiplies it."]
    if coupon.get("url"):
        lines += ["", f"Public coupon page: {coupon['url']} (fill it in yourself; nothing is placed for you)."]
    else:
        lines += ["", "Fill the coupon in yourself; nothing is placed for you."]

    if len(plans) > 1:
        lines += ["", "## Budget tiers", "", "| Tier | Rows | Cost (NOK) | % of bankroll | P(fully correct row) | 1 in | Within cap |",
                  "|---|---|---|---|---|---|---|"]
        for p in plans:
            lines.append(f"| {p['tier']} | {p['rows']} | {p['cost_nok']:g} | {p['pct_bankroll']:.2f} % | "
                         f"{p['p_all_correct']:.2%} | {_one_in(p['one_in'])} | {'yes' if p['within_cap'] else 'no'} |")
        lines.append("")
        lines.append("More rows raise the chance but with diminishing returns, and each extra row costs the same.")

    caveats = ["Crowding numbers assume tippers pick matches independently; real tippers pile onto the same favourites, "
               "so popular rows are probably more crowded than shown.",
               "Row price and payout rules are as given by you or the source; check them against Norsk Tipping's current rules."]
    est = [m for m in matches.values() if m.get("q_estimated")]
    if est:
        caveats.append("Public split is an estimate for match(es) " + ", ".join(f"#{m['slot']}" for m in est) + ".")
    nosplit = [m for m in matches.values() if not m.get("q")]
    if nosplit:
        caveats.append("No public split for match(es) " + ", ".join(f"#{m['slot']}" for m in nosplit)
                       + "; those marks optimise the hit chance only.")
    low = [m for m in matches.values() if m.get("confidence") == "low"]
    if low:
        caveats.append("Low-confidence match(es): " + ", ".join(f"#{m['slot']}" for m in low) + ".")
    for m in matches.values():
        for f in m.get("risk_flags") or []:
            caveats.append(f"#{m['slot']}: {f}")
    caveats += notes
    lines += ["", "## What could be wrong", ""] + [f"- {c}" for c in caveats]

    lines += ["", "## Sources", ""]
    srcs = data.get("sources") or []
    lines += [f"- {s.get('name', 'unnamed')}" + (f" ({s['url']})" if s.get("url") else "")
              + f", fetched {s.get('fetched_at', 'time unknown')}" for s in srcs] or ["- none given"]
    lines += ["", CLOSING, ""]
    return {"markdown": "\n".join(lines), "warnings": warnings, "recommended_tier": rec["tier"]}


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
        out = build(json.loads(raw))
    except (InputError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2) if "--json" in argv else out["markdown"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
