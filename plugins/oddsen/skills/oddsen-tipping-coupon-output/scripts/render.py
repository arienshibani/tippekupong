#!/usr/bin/env python3
"""Render the final Tipping coupon recommendation as markdown.

Usage:
    python3 render.py input.json            # markdown on stdout
    python3 render.py --build build.json --value value.json --coupon coupon.json --bankroll 3000 \\
                      [--odds odds.json] [--cap-pct N] [--day sunday] [--note "text"]... [--why "3=reason"]...
                      [--source "name|2026-10-10T12:00:00Z|url"]... [--out report.md]
        builds the input from the earlier stages' files (build.py, adjust.py, fetch_coupon.py, fetch_odds.py)
    python3 render.py input.json --json     # {"markdown", "warnings", "recommended_tier", "chance_range"}
    cat input.json | python3 render.py -    # read stdin

Input JSON:
    {
      "bankroll_nok": 5000,                       # required
      "cap_pct": 2,                               # only if the USER set their own cap; omit to use the
                                                  # default (2 %), which the report then calls "the default cap"
      "now": "2026-10-10T12:00:00Z",              # optional; ONLY to replay old data. Defaults to the
                                                  # machine clock, which is what you want in real use.
      "max_source_age_hours": 6,                  # optional
      "coupon": {"name": "...",                   # all optional
                 "deadline": "2026-10-10T17:00:00+02:00",   # any ISO time WITH a zone (Z or +02:00);
                 "url": "https://..."},                     # "deadline_utc" is accepted as an alias
      "optimizer_result": { ... output of oddsen-tipping-coupon-optimizer ... },
      "matches": [ ... "matches" from oddsen-tipping-value-model ... ],
      "excluded": [ ... "excluded" from the value model (carries dropped-quote reasons) ... ],
      "sources": [{"name": "...", "url": "...", "fetched_at": "2026-10-10T11:30:00Z",
                   "static": false}],             # static: true = time does not matter (e.g. the match list)
      "why": {"1": "One-line reason for match 1"},     # optional, overrides the auto text
      "notes": ["free-text caveats from the analyst"]  # optional
    }

Times must carry a time zone ("Z" or an offset such as "+02:00" for Oslo summer time); a time
without one is rejected rather than guessed. The recommended tier is the most expensive one that
fits the cap (else the cheapest, with a warning). Free text that calls a bet safe, certain or a lock
is rejected. Standard library only.
"""
import json
import re
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    OSLO = ZoneInfo("Europe/Oslo")
except Exception:  # no tz database on this system: fall back to UTC-only display
    OSLO = None

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
# Rough chance that a single mark on a 1X2 football match is right. Used only to illustrate how
# much an unanalysed match lowers the headline chance; not a model output.
SINGLE_MARK_LOW, SINGLE_MARK_HIGH = 0.30, 0.55
# Phrases the optimizer also reports; the report covers them in its own caveats, so skip the repeat.
COVERED_ELSEWHERE = ("no public split", "public split is an estimate", "requested budget")


class InputError(ValueError):
    pass


def _time(text):
    dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"time {text!r} has no time zone; add Z or an offset such as +02:00")
    return dt.astimezone(timezone.utc)


def _fmt(dt):
    """Oslo time first (when the tz database exists), UTC in brackets."""
    if OSLO:
        return f"{dt.astimezone(OSLO):%Y-%m-%d %H:%M} Oslo ({dt:%H:%M} UTC)"
    return f"{dt:%Y-%m-%d %H:%M} UTC"


def _time_or_none(text):
    try:
        return _time(text) if text else None
    except ValueError:
        return None


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
    """A short reason for the mark, only where there is something to say beyond the table."""
    if not match:
        return ""
    p, q, ratio = match["p_est"], match.get("q"), match.get("value_ratio")
    outs = sorted(plan_mark["outcomes"], key=OUTCOMES.index)
    order = sorted(OUTCOMES, key=lambda k: -p[k])
    top = order[0]
    bits = []
    if len(outs) == 3:
        bits.append(f"flat match, no outcome above {p[top]:.0%}, so fully covered")
    elif len(outs) == 2:
        if set(outs) == set(order[:2]):
            bits.append("the two likeliest outcomes")
        else:
            extra = [k for k in outs if k not in order[:2]][0]
            bits.append(f"includes {MARK[extra]} ({p[extra]:.0%}) because fewer tippers back it")
    else:
        k = outs[0]
        bits.append(f"likeliest outcome ({p[k]:.0%})" if k == top
                    else f"not the likeliest ({p[k]:.0%} against {p[top]:.0%} for {MARK[top]}), but fewer tippers back it")
    if q and ratio:
        for k in outs:
            if ratio[k] >= 1.25:
                bits.append(f"{MARK[k]} is under-backed (public {q[k]:.0%})")
            elif ratio[k] <= 0.75:
                bits.append(f"{MARK[k]} is over-backed (public {q[k]:.0%})")
    return "; ".join(bits)


SHORT_REASONS = {
    "no bookmaker odds (expert tips and public split only)": "no bookmaker odds",
    "only one bookmaker priced this match": "one bookmaker only",
}


def _risk_text(match):
    """Reasons for doubt and short notes about this match; a dash when there is nothing to flag."""
    if not match:
        return "no model data"
    parts = [SHORT_REASONS.get(r, r) for r in (match.get("confidence_reasons") or [])]
    parts += list(match.get("notes") or [])
    if not parts:
        return "–"
    return "; ".join(parts) + (" (low confidence)" if match.get("confidence") == "low" else "")


def _adjustment_label(a):
    delta = a.get("delta_pp")
    try:
        return f"{a.get('outcome')} {float(delta):+g} pp"
    except (TypeError, ValueError):
        return f"{a.get('outcome')} {delta}"


def _rejected_notes(match):
    """One bullet per reason for adjustments that were not applied (unconfirmed ones are already flags)."""
    groups = {}
    for a in match.get("rejected") or []:
        why = a.get("why", "")
        if why.startswith("unconfirmed"):
            continue
        groups.setdefault(why, []).append(a)
    notes = []
    for why, items in groups.items():
        what = ", ".join(_adjustment_label(a) for a in items)
        reasons = "; ".join(dict.fromkeys(str(a.get("reason")) for a in items if a.get("reason")))
        notes.append(f"#{match['slot']}: news adjustment not applied ({why}): {what}"
                     + (f" ({reasons})" if reasons else ""))
    return notes


def _dropped_text(entry):
    drops = entry.get("dropped") or []
    if not drops:
        return ""
    return "; ".join(f"{d.get('book', 'a quote')} - {d.get('reason')}" for d in drops)


def _crowding_line(rec, has_unsplit):
    idx = rec["mean_row_value_index"]
    tech = f"mean row value index {idx}, where 1.0 is a row picked the way the public picks"
    if idx < 0.9:
        plain = (f"Your rows are about {1 / idx:.1f}× as crowded as their probability suggests, so a winning row "
                 f"would typically pay about {idx:.0%} of what a public-style row pays. The plan leans toward hit "
                 "chance rather than payout.")
    elif idx > 1.1:
        plain = (f"Your rows are less crowded than their probability suggests; a winning row would typically pay "
                 f"about {idx:.1f}× what a public-style row pays.")
    else:
        plain = "Your rows are about as crowded as the public's."
    extra = " Matches without a public split count as neutral, which biases this figure." if has_unsplit else ""
    return f"- Crowding: {plain}{extra} Technical: {tech}; assumes tippers choose matches independently."


STRATEGY_TEXT = {
    "balanced": "balanced: maximises the expected payout while keeping at least 80 % of the best chance of a prize, "
                "so among nearly equally likely choices it prefers outcomes fewer other tippers pick",
    "prize-chance": "prize-chance: maximises the chance of winning something, ignoring what other tippers pick",
}
AVERAGE_TICKET_PER_NOK = 0.47  # 55 % of turnover is paid out; 85 % of that goes to the 12/11/10 tiers
EDGE_BAND = 0.03  # within this of the average ticket counts as "about the same" (the estimate is good to about 0.01)


def _payout_lines(rec, scope, cost):
    p = rec["p_any_prize"]
    pub_b, hit_b = rec["baselines"]["follow_the_public"], rec["baselines"]["maximise_chance_of_all_correct"]
    epn, se = rec["expected_payout_per_nok"], rec["expected_payout_se_nok"] / cost
    edge = epn - AVERAGE_TICKET_PER_NOK
    if edge >= EDGE_BAND:
        verdict = (f"That is about {edge:.2f} more per NOK than an average ticket: a small edge in a game that pays out less "
                   "than it takes in, not a way to make money.")
    elif edge <= -EDGE_BAND:
        verdict = "That is below an average ticket. This game pays out less than it takes in; it is not a way to make money."
    else:
        verdict = ("That is about the same as an average ticket, so no real edge. This game pays out less than it takes in; "
                   "it is not a way to make money.")
    return [
        f"- Chance of winning a prize (10, 11 or 12 correct){scope}: **{p:.0%}**, about 1 in {round(1 / p) if p else 0}. "
        f"All 12 correct: about 1 in {_one_in(rec['one_in'])}.",
        f"- Expected payout: about **{rec['expected_payout_nok']:.0f} NOK on {cost:g} NOK staked ({epn:.2f} per NOK**, ±{se:.3f}; "
        f"differences under about 0.02 per NOK are noise). For comparison: following the public with {pub_b['rows']} rows is worth "
        f"about {pub_b['expected_payout_per_nok']:.2f} per NOK, the coupon with the best chance of all 12 ({hit_b['rows']} rows) about "
        f"{hit_b['expected_payout_per_nok']:.2f}, and an average ticket about {AVERAGE_TICKET_PER_NOK:.2f} before the bonus pool. {verdict}",
        f"- Strategy: {STRATEGY_TEXT.get(rec.get('strategy'), rec.get('strategy'))}.",
    ]


def build(data):
    try:
        bankroll = float(data["bankroll_nok"])
    except (KeyError, TypeError, ValueError):
        raise InputError("bankroll_nok is required")
    if bankroll <= 0:
        raise InputError("bankroll_nok must be positive")
    cap_pct = float(data.get("cap_pct", 2))
    cap_label = f"your {cap_pct:g} % cap" if "cap_pct" in data else f"the default {cap_pct:g} % cap"
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

    try:
        now = _time(data["now"]) if data.get("now") else datetime.now(timezone.utc)
    except ValueError as e:
        raise InputError(f"now: {e}")
    coupon = data.get("coupon") or {}
    warnings = [w for w in (result.get("warnings") or []) if not any(p in w for p in COVERED_ELSEWHERE)]

    for plan in plans:
        plan["pct_bankroll"] = plan["cost_nok"] / bankroll * 100
        plan["within_cap"] = plan["pct_bankroll"] <= cap_pct + 1e-9
    fitting = [p for p in plans if p["within_cap"]]
    rec = max(fitting, key=lambda p: p["cost_nok"]) if fitting else min(plans, key=lambda p: p["cost_nok"])
    if result.get("budget_capped") and result.get("requested_budget_nok"):
        asked = result["requested_budget_nok"]
        warnings.append(f"You asked for {asked:g} NOK ({asked / bankroll:.1%} of your bankroll), which is above "
                        f"{cap_label}. The plans below are built at the cap ({result['budget_nok']:g} NOK).")
    if not fitting:
        warnings.append(
            f"Even the cheapest plan costs {rec['pct_bankroll']:.1f} % of the bankroll, above {cap_label}. "
            "It is shown for reference and is NOT recommended; consider a smaller budget or skipping this coupon.")
    elif rec["tier"] != plans[-1]["tier"] and not plans[-1]["within_cap"]:
        warnings.append(f"The '{plans[-1]['tier']}' tier is above {cap_label} and is not recommended.")

    if rec["rows"] == 3 ** len(rec["marks"]):
        warnings.append("This plan buys every possible row. It guarantees a winning row, not a profit: "
                        "the payout can be smaller than the cost.")

    deadline, left_text = None, ""
    deadline_raw = coupon.get("deadline") or coupon.get("deadline_utc")
    if deadline_raw:
        try:
            deadline = _time(deadline_raw)
        except ValueError as e:
            raise InputError(f"coupon deadline: {e}")
        left = (deadline - now).total_seconds() / 60
        if left <= 0:
            warnings.append("The coupon deadline has passed.")
        else:
            left_text = f"{int(left // 60)} h {int(left % 60)} min left"
            if left < 60:
                warnings.append(f"Less than an hour to the deadline ({left:.0f} min).")

    max_age = float(data.get("max_source_age_hours", 6))
    parsed_sources, source_notes = [], []
    for s in data.get("sources") or []:
        stamp = None
        if s.get("fetched_at"):
            try:
                stamp = _time(s["fetched_at"])
            except ValueError as e:
                warnings.append(f"Source '{s.get('name')}': {e}.")
            else:
                age = (now - stamp).total_seconds() / 3600
                if age > max_age:
                    warnings.append(f"Source '{s.get('name')}' is {age:.1f} h old; odds and news may have moved.")
        elif not s.get("static"):
            source_notes.append(f"Source '{s.get('name')}' has no timestamp, so its freshness is unknown.")
        parsed_sources.append((s, stamp))

    lines = [f"# Tipping coupon recommendation{': ' + coupon['name'] if coupon.get('name') else ''}", ""]
    meta = [f"Row price {result.get('row_price_nok', '?')} NOK",
            (f"Strategy: {rec['strategy']}" if rec.get("expected_payout_per_nok") is not None
             else f"Preference: {RISK_LABEL.get(result.get('risk'), result.get('risk'))}"),
            f"Bankroll {bankroll:,.0f} NOK".replace(",", " ")]
    if deadline:
        meta.insert(0, f"Deadline {_fmt(deadline)}" + (f", {left_text}" if left_text else ""))
    lines += [" · ".join(meta), ""]
    if warnings:
        lines += ["\n>\n".join(f"> **Warning:** {w}" for w in warnings), ""]

    excluded = data.get("excluded") or []
    scope = " (analysed matches only)" if excluded else ""
    n_exc = len(excluded)

    def whole_range(p):
        return p * SINGLE_MARK_HIGH ** n_exc, p * SINGLE_MARK_LOW ** n_exc

    chance_range = None
    heading = (f"## Recommended: {rec['tier']} tier" if rec["within_cap"]
               else f"## Cheapest plan: {rec['tier']} tier (above {cap_label}, not recommended)")
    lines += [heading, "",
              f"- **{rec['rows']} rows, {rec['cost_nok']:g} NOK = {rec['pct_bankroll']:.2f} % of bankroll** "
              f"({'cap ' + format(cap_pct, 'g') + ' %' if rec['within_cap'] else 'over the ' + format(cap_pct, 'g') + ' % cap'})"]
    new_style = rec.get("expected_payout_per_nok") is not None
    if new_style:
        lines += _payout_lines(rec, scope, rec["cost_nok"])
        if result.get("turnover_nok"):
            lines.append(f"- Pool: about {result['turnover_nok']:,.0f} NOK expected at the deadline (the payouts are shares of it).".replace(",", " "))
    elif excluded:
        hi, lo = whole_range(rec["p_all_correct"])
        chance_range = [hi, lo]
        lines.append(f"- **Chance that the whole coupon contains a fully correct row: roughly 1 in {_one_in(round(1 / hi))} "
                     f"to 1 in {_one_in(round(1 / lo))}.** The {len(rec['marks'])} analysed matches alone give "
                     f"{rec['p_all_correct']:.2%} (about 1 in {_one_in(rec['one_in'])}); the range assumes you single-mark "
                     f"the {n_exc} unanalysed match{'es' if n_exc > 1 else ''} at a typical {SINGLE_MARK_LOW:.0%} to "
                     f"{SINGLE_MARK_HIGH:.0%} chance of being right{' each' if n_exc > 1 else ''}.")
    else:
        lines.append(f"- Estimated chance that the coupon contains a fully correct row: "
                     f"**{rec['p_all_correct']:.2%}** (about 1 in {_one_in(rec['one_in'])})")
    unused = rec.get("tier_budget_nok")
    if unused is not None and rec["cost_nok"] < unused - 1e-9:
        lines.append(f"- Uses {rec['cost_nok']:g} of the {unused:g} NOK for this tier: the number of rows is a product "
                     "of 1, 2 and 3 (a half cover doubles it, a full cover triples it), so not every amount can be filled.")
    if excluded:
        if new_style:
            lines.append(f"- The {n_exc} unanalysed match{'es' if n_exc > 1 else ''} below are not in these numbers.")
        c2, c3 = rec["cost_nok"] * 2, rec["cost_nok"] * 3
        p2, p3 = c2 / bankroll * 100, c3 / bankroll * 100
        over = lambda p: f", above {cap_label}" if p > cap_pct + 1e-9 else ""
        lines.append(f"- Covering one of the unanalysed matches instead of single-marking it doubles the cost to {c2:g} NOK "
                     f"({p2:.2f} % of bankroll{over(p2)}); a full cover triples it to {c3:g} NOK "
                     f"({p3:.2f} %{over(p3)}).")
    if rec.get("mean_row_value_index") is not None and not new_style:
        lines.append(_crowding_line(rec, any(not m.get("q") for m in matches.values())))
    has_kickoff = any(m.get("kickoff") for m in matches.values())

    def kickoff_text(m):
        try:
            when = _time(m["kickoff"])
        except (KeyError, TypeError, ValueError):
            return "n/a"
        return f"{when.astimezone(OSLO) if OSLO else when:%a %H:%M}"

    lines += ["", "| # | Match |" + (" Kick-off (Oslo) |" if has_kickoff else "") + " Mark | Cover | p (est) 1/X/2 | Public 1/X/2 | Why | Risk |",
              "|---|---|" + ("---|" if has_kickoff else "") + "---|---|---|---|---|---|"]
    for pm in rec["marks"]:
        m = matches.get(pm["slot"])
        cells = [pm["slot"], pm["label"]] + ([kickoff_text(m) if m else "n/a"] if has_kickoff else []) + [
            f"**{pm['mark']}**", pm["cover"], _triple(m["p_est"]) if m else "n/a", _triple(m.get("q")) if m else "n/a",
            why.get(str(pm["slot"])) or _auto_why(pm, m), _risk_text(m)]
        lines.append("| " + " | ".join(_cell(x) for x in cells) + " |")

    lines += ["", "Copy into your own coupon:", "", "```"]
    grid = [(pm["slot"], f"{pm['slot']:>2}  {pm['mark']:<4} {pm['label']}") for pm in rec["marks"]]
    grid += [(e["slot"], f"{e['slot']:>2}  ?    {e.get('label') or ''} (not analysed: mark it yourself)")
             for e in excluded]
    lines += [line for _, line in sorted(grid, key=lambda g: g[0])]
    lines += ["```"]
    if excluded:
        lines += ["", "**Not covered by this plan:**"]
        for e in excluded:
            detail = _dropped_text(e)
            lines.append(f"- #{e['slot']} {e.get('label') or ''}".rstrip()
                         + f": {e.get('reason', 'no usable market')}" + (f" ({detail})" if detail else ""))
        lines += ["", "The coupon still needs a mark for each. A single mark leaves the cost unchanged; a cover "
                  "multiplies it."]
    if coupon.get("url"):
        lines += ["", f"Public coupon page: {coupon['url']} (fill it in yourself; nothing is placed for you)."]
    else:
        lines += ["", "Fill the coupon in yourself; nothing is placed for you."]

    if new_style and rec.get("alternatives"):
        lines += ["", "## Same budget, other strategies", "",
                  "| Strategy | Rows | Chance of a prize | Expected payout per NOK | Marks |", "|---|---|---|---|---|"]
        def row(name, r):
            return (f"| {name} | {r['rows']} | {r['p_any_prize']:.0%} | {r['expected_payout_per_nok']:.2f} | "
                    + " ".join(m["mark"] for m in r["marks"]) + " |")
        lines.append(row(f"**{rec['strategy']}** (above)", rec))
        for name, alt in rec["alternatives"].items():
            lines.append(row(name, alt))
        for name, b_ in (rec.get("baselines") or {}).items():
            lines.append(f"| {name.replace('_', ' ')} (comparison) | {b_['rows']} | n/a | {b_['expected_payout_per_nok']:.2f} | "
                         + " ".join(b_["marks"]) + " |")
        close = [n for n, alt in rec["alternatives"].items()
                 if abs(alt["expected_payout_per_nok"] - rec["expected_payout_per_nok"]) < 0.02
                 and abs(alt["p_any_prize"] - rec["p_any_prize"]) < 0.03]
        if close:
            lines += ["", f"The {rec['strategy']} plan and the {' and '.join(close)} plan are within the margin of error of each other: "
                          "pick whichever mix of marks you prefer."]
    if len(plans) > 1 and new_style:
        lines += ["", "## Budget tiers", "",
                  "| Tier | Rows | Cost (NOK) | % of bankroll | Chance of a prize | Expected payout per NOK | Within cap |",
                  "|---|---|---|---|---|---|---|"]
        for p in plans:
            lines.append(f"| {p['tier']} | {p['rows']} | {p['cost_nok']:g} | {p['pct_bankroll']:.2f} % | {p['p_any_prize']:.0%} | "
                         f"{p['expected_payout_per_nok']:.2f} | {'yes' if p['within_cap'] else 'no'} |")
        lines += ["", "More rows raise the chance of a prize, but they do not turn a pool coupon into a profitable one."]
    elif len(plans) > 1:
        extra_h = " Whole coupon, roughly |" if excluded else ""
        lines += ["", "## Budget tiers", "",
                  f"| Tier | Rows | Cost (NOK) | % of bankroll | P(fully correct row){scope} | 1 in |{extra_h} Within cap |",
                  "|---|---|---|---|---|---|" + ("---|" if excluded else "") + "---|"]
        for p in plans:
            extra = ""
            if excluded:
                hi_, lo_ = whole_range(p["p_all_correct"])
                extra = f" 1 in {_one_in(round(1 / hi_))} to {_one_in(round(1 / lo_))} |"
            lines.append(f"| {p['tier']} | {p['rows']} | {p['cost_nok']:g} | {p['pct_bankroll']:.2f} % | "
                         f"{p['p_all_correct']:.2%} | {_one_in(p['one_in'])} |{extra} {'yes' if p['within_cap'] else 'no'} |")
        lines.append("")
        lines.append("More rows raise the chance of a fully correct row, but they do not turn a pool coupon "
                     "into a profitable one.")

    caveats = ["Row price and payout rules are as given by you or the source; check them against Norsk Tipping's current rules."]
    if not new_style:
        caveats.insert(0, "Crowding numbers assume tippers pick matches independently; real tippers pile onto the same favourites, "
                          "so popular rows are probably more crowded than shown.")
    crowd_only = [m for m in matches.values()
                  if any("no bookmaker odds" in r for r in (m.get("confidence_reasons") or []))]
    if new_style and crowd_only:
        caveats.append(f"For {len(crowd_only)} of {len(matches)} matches there are no bookmaker odds, so the probability rests on Norsk Tipping's "
                       "expert tips and the public split. Both were well calibrated on 720 past matches, but they are not independent of "
                       "the crowd, so there is little independent edge on those matches.")
    if new_style:
        caveats.append("Expected payout assumes other tippers pick independently match by match, as the public split says, and a "
                       "final pool as stated above. On 60 past rounds that predicted the number of 10- and 11-correct winners "
                       "within about 5 % and 12-correct winners less well. It is an average over many rounds; one round most likely pays nothing.")
        caveats.append("Extra money from the bonus pool (when nobody has 12 correct) is not counted: that is upside. 10-correct prizes "
                       "were cancelled in 15 of the last 60 rounds because too many shared them; the chance of a prize accounts for that.")
    est = [m for m in matches.values() if m.get("q_estimated")]
    if est:
        caveats.append("Public split is an estimate for match(es) " + ", ".join(f"#{m['slot']}" for m in est) + ".")
    nosplit = [m for m in matches.values() if not m.get("q")]
    if nosplit:
        caveats.append("No public split for match(es) " + ", ".join(f"#{m['slot']}" for m in nosplit)
                       + "; their crowding is unknown, so those marks are chosen on hit chance only.")
    low = [m for m in matches.values() if m.get("confidence") == "low"]
    if low:
        caveats.append("Low-confidence match(es): " + ", ".join(f"#{m['slot']}" for m in low) + ".")
    rescaled = [f"#{m['slot']} ({m['split_note']})" for m in matches.values() if m.get("split_note")]
    if rescaled:
        caveats.append("Public split rescaled to add to 100 %: " + "; ".join(rescaled) + ".")
    for m in matches.values():
        for f in m.get("risk_flags") or []:
            caveats.append(f"#{m['slot']}: {f}")
        caveats += _rejected_notes(m)
    caveats += source_notes
    caveats += notes
    applied_lines = []
    for m in sorted(matches.values(), key=lambda x: x["slot"]):
        items = {}  # one line per news item (source + time), mirrored legs together
        for a in m.get("applied") or []:
            items.setdefault((a.get("source"), a.get("source_time")), []).append(a)
        for (source, source_time), legs in items.items():
            when = _time_or_none(source_time)
            sizes = ", ".join(f"{a['outcome']} {float(a['delta_pp']):+g} pp" for a in legs)
            reasons = "; ".join(dict.fromkeys(str(a.get("reason")) for a in legs if a.get("reason")))
            applied_lines.append(f"- #{m['slot']} {m.get('label') or ''}: {sizes}: {reasons} "
                                 f"[{source}" + (f", {_fmt(when)}" if when else "") + "]")
    if applied_lines:
        lines += ["", "## News used", "", "Adjustments applied to the market probabilities (small, sourced, capped):", ""]
        lines += applied_lines
    lines += ["", "## What could be wrong", ""] + [f"- {c}" for c in caveats]

    lines += ["", "## Sources", ""]
    for s, stamp in parsed_sources:
        when = _fmt(stamp) if stamp else "time not relevant" if s.get("static") else "time unknown"
        lines.append(f"- {s.get('name', 'unnamed')}" + (f" ({s['url']})" if s.get("url") else "") + f", {when}")
    if not parsed_sources:
        lines.append("- none given")
    lines += ["", CLOSING, ""]
    return {"markdown": "\n".join(lines), "warnings": warnings, "recommended_tier": rec["tier"],
            "chance_range": chance_range}


DAY_PAGE = {"SUNDAY": "https://www.norsk-tipping.no/sport/tipping/spill?day=2"}


def _round_name(c):
    try:
        when = datetime.fromisoformat(c["deadline"])
        if OSLO:
            when = when.astimezone(OSLO)
        return f"Tipping, {when:%A} {when.day} {when:%B} (round #{c['game_id']})"
    except (KeyError, TypeError, ValueError):
        return f"Tipping {str(c.get('day', '')).lower()} (round #{c.get('game_id')})"


def input_from_files(options, notes, whys, extra_sources):
    """Assemble the report input from the files the earlier stages wrote."""
    def load(flag):
        with open(options[flag], encoding="utf-8") as f:
            return json.load(f)
    built, value, coupon_file = load("--build"), load("--value"), load("--coupon")
    coupons = coupon_file.get("coupons") or []
    day = options.get("--day")
    if day:
        coupons = [c for c in coupons if c["day"].lower() == day.lower()] or coupons
    if not coupons:
        raise InputError("the coupon file has no coupons")
    c = coupons[0]
    src = coupon_file.get("source") or {}
    sources = [{"name": "Norsk Tipping Tipping API: matches, public split, expert tips, pool size, row price",
                "url": src.get("url"), "fetched_at": src.get("fetched_at")}]
    if "--odds" in options:
        odds = load("--odds")
        s = odds.get("source") or {}
        sources.append({"name": "Bookmaker odds (football-data.co.uk)", "url": s.get("url"),
                        "fetched_at": s.get("odds_file_last_modified") or s.get("fetched_at")})
    sources += extra_sources
    data = {"bankroll_nok": options.get("--bankroll"), "optimizer_result": built, "matches": value["matches"],
            "excluded": value.get("excluded") or [], "sources": sources, "notes": notes, "why": whys,
            "coupon": {"name": _round_name(c), "deadline": c["deadline"],
                       "url": DAY_PAGE.get(c["day"], "https://www.norsk-tipping.no/sport/tipping")}}
    if "--cap-pct" in options:
        data["cap_pct"] = options["--cap-pct"]
    if "--now" in options:
        data["now"] = options["--now"]
    return data


def main(argv):
    args, options, positional, notes, whys, extra_sources, i = argv[1:], {}, [], [], {}, [], 0
    value_flags = ("--build", "--value", "--coupon", "--odds", "--bankroll", "--cap-pct", "--day", "--now", "--out")
    while i < len(args):
        a = args[i]
        if a in value_flags and i + 1 < len(args):
            options[a] = args[i + 1]; i += 2
        elif a == "--note" and i + 1 < len(args):
            notes.append(args[i + 1]); i += 2
        elif a == "--why" and i + 1 < len(args) and "=" in args[i + 1]:
            slot, text = args[i + 1].split("=", 1); whys[slot.strip()] = text.strip(); i += 2
        elif a == "--source" and i + 1 < len(args):  # name|fetched_at|url (all but name optional)
            parts = (args[i + 1].split("|") + ["", ""])[:3]
            extra_sources.append({"name": parts[0], "fetched_at": parts[1] or None, "url": parts[2] or None,
                                  "static": not parts[1]})
            i += 2
        elif a == "--json":
            options[a] = True; i += 1
        elif a.startswith("--"):
            print(__doc__, file=sys.stderr); return 2
        else:
            positional.append(a); i += 1
    auto = "--build" in options
    if (auto and (positional or not all(f in options for f in ("--value", "--coupon", "--bankroll")))) or (not auto and len(positional) != 1):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if auto:
            data = input_from_files(options, notes, whys, extra_sources)
        else:
            raw = sys.stdin.read() if positional[0] == "-" else open(positional[0], encoding="utf-8").read()
            data = json.loads(raw)
        out = build(data)
    except (InputError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except (KeyError, TypeError, AttributeError) as e:
        print(f"error: input has a missing field or the wrong shape ({type(e).__name__}: {e}). "
              "Expected optimizer_result as the optimizer's full output (an object with 'plans') and "
              "matches as the value model's 'matches' list.", file=sys.stderr)
        return 1
    if "--out" in options:
        with open(options["--out"], "w", encoding="utf-8") as f:
            f.write(out["markdown"])
    print(json.dumps(out, indent=2) if "--json" in options else out["markdown"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
