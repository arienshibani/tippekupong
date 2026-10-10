#!/usr/bin/env python3
"""Build a Tipping coupon (a system of marks) that maximises EXPECTED PAYOUT within a budget.

Usage:
    python3 build.py input.json            # JSON result on stdout
    python3 build.py input.json --text     # human-readable summary
    cat input.json | python3 build.py -    # read stdin
    python3 build.py --value value.json --coupon coupon.json --budget 50 --bankroll 3000 \\
                     [--max-budget N] [--cap-pct N] [--goal balanced|prize-chance] [--day sunday] [--out f.json] [--text]
        assembles the input from oddsen-tipping-value-model's output and oddsen-tipping-fixtures' coupon file
        (row price and the estimated final turnover come from the coupon)

Input JSON:
    {
      "row_price_nok": 1.0,
      "budget_nok": 50,                 # tier "base"; "cheap" is half of it
      "max_budget_nok": 100,            # optional: adds a "max" tier
      "bankroll_nok": 3000,             # with it, every tier is cut to cap_pct % of the bankroll
      "cap_pct": 2,                     # only if the user set their own cap (default 2)
      "turnover_nok": 2600000,          # expected FINAL turnover of the round (see fetch_coupon.py)
      "goal": "balanced",               # "balanced" (default) or "prize-chance"
      "matches": [{"slot": 1, "label": "A - B",
                   "p": {"H": .45, "U": .27, "B": .28},     # estimated true probabilities
                   "q": {"H": .39, "U": .24, "B": .37}}],   # public split (what other tippers pick)
      "samples": 2500, "final_samples": 30000, "seed": 7    # optional
    }

Strategies. "prize-chance": maximise the chance of winning something, weighting the tiers by typical
prize sizes (exact, ignores the crowd). "balanced" (default): maximise the expected payout while
keeping at least 80 % of the best prize-chance value, which in practice means choosing among
near-equally likely outcomes the ones fewer other tippers pick. Both are computed for every tier;
the chosen one is in "plans", the other under "alternatives". A pure "maximise expected payout"
strategy is deliberately not offered: it drifts to long shots (about a 0.4 % chance of any prize),
and its payout cannot be estimated reliably (standard error above 15 %; on fresh samples it
scored below the balanced plan, 0.39 against 0.46 per NOK, because the search overfits rare jackpots).

Model (rules and evidence in shared/tipping-payout-rules.md). The prize pool is 55 % of the round's
turnover. Tier "12 correct" and tier "11 correct" each get 27 % of it, tier "10 correct" gets
31 %, 15 % goes to a bonus pool (ignored here: upside only). Each winner gets pot / winners,
rounded down to 5 kr. If a tier-10 prize would be under 10 kr, that tier pays nothing and its pot
is split equally over the 12 and 11 tiers. The number of OTHER winning rows in a tier is Poisson
with mean = rows in play x probability that a row picked like the public (independently per match,
from "q") has exactly that many wrong. Our expected payout is summed over all possible results:
tier 12 exactly (over our own rows), tiers 11 and 10 by Monte Carlo with the true probabilities "p".

The search is a greedy fill followed by single-match local moves; it needs no numpy. Standard
library only.
"""
import itertools
import json
import math
import random
import sys

OUTCOMES = ("H", "U", "B")
MARK = {"H": "1", "U": "X", "B": "2"}
RISK_ALIASES = {"safe": "prize-chance", "balanced": "balanced", "contrarian": "balanced"}
GOALS = ("balanced", "prize-chance")
TYPICAL_PRIZE = (1750.0, 90.0, 10.0)  # median prize per winner in 12 / 11 / 10 correct, last 60 rounds
BALANCED_FLOOR = 0.80

PRIZE_SHARE = 0.55
TIER_SHARE = (0.27, 0.27, 0.31)  # all correct, one wrong, two wrong (12, 11, 10 of 12)
ROUND_DOWN = 5.0
MIN_PRIZE = 10.0
KAPPA = (1.0, 1.0, 1.0)          # crowd-count calibration per tier; 1.0 fits 60 rounds within ~6 %
POISSON_EXACT_BELOW = 40.0
Q_FLOOR = 0.02
RESCALE_TOL = 0.02


class InputError(ValueError):
    pass


# ----------------------------------------------------------------------------- input handling
def _probs(raw, where, floor=0.0):
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
        raise InputError(f"{where}: H+U+B adds to {total:g}; give fractions such as 0.51 or percentages adding to about 100")
    if abs(total - 1.0) > 1e-4:  # smaller gaps are just decimals rounded upstream
        note = (note + "; " if note else f"added to {total:.1%}; ") + "divided by the total"
    else:
        note = None
    if floor:
        vals = {k: max(v, floor) for k, v in vals.items()}
        total = sum(vals.values())
    return [vals[k] / total for k in OUTCOMES], note


def parse_input(data):
    warnings = []
    try:
        price = float(data["row_price_nok"])
        budget = float(data["budget_nok"])
    except (KeyError, TypeError, ValueError):
        raise InputError("row_price_nok and budget_nok are required numbers")
    if price <= 0 or budget <= 0:
        raise InputError("row_price_nok and budget_nok must be positive")
    max_budget = float(data["max_budget_nok"]) if data.get("max_budget_nok") is not None else None
    if max_budget is not None and max_budget < budget:
        raise InputError("max_budget_nok must be >= budget_nok")
    requested, capped, bankroll, cap_pct = budget, False, None, None
    if data.get("bankroll_nok") is not None:
        try:
            bankroll, cap_pct = float(data["bankroll_nok"]), float(data.get("cap_pct", 2))
        except (TypeError, ValueError):
            raise InputError("bankroll_nok and cap_pct must be numbers")
        if bankroll <= 0 or cap_pct <= 0:
            raise InputError("bankroll_nok and cap_pct must be positive")
        cap_budget = bankroll * cap_pct / 100
        if cap_budget < price - 1e-9:
            raise InputError(f"a {cap_pct:g} % cap of {bankroll:g} NOK is {cap_budget:g} NOK, less than one row ({price:g} NOK)")
        if budget > cap_budget + 1e-9:
            warnings.append(f"requested budget {budget:g} NOK is {budget / bankroll:.1%} of the bankroll, above the "
                            f"{cap_pct:g} % cap; plans are built at the cap ({cap_budget:g} NOK)")
            budget, capped = cap_budget, True
        if max_budget is not None and max_budget > cap_budget + 1e-9:
            warnings.append(f"max budget {max_budget:g} NOK is above the cap; the max tier is built at the cap")
            max_budget = cap_budget
    goal = data.get("goal") or RISK_ALIASES.get(data.get("risk"), "balanced")
    if goal not in GOALS:
        raise InputError("goal must be 'balanced' or 'prize-chance'")
    raw = data.get("matches") or []
    if len(raw) < 3:
        raise InputError("need at least 3 matches")
    matches, errors = [], []
    for idx, m in enumerate(raw):
        slot, label = m.get("slot", idx + 1), m.get("label") or f"Match {m.get('slot', idx + 1)}"
        try:
            p, p_note = _probs(m.get("p"), f"match {slot} p")
            q, q_note = (None, None)
            if m.get("q") is not None:
                q, q_note = _probs(m["q"], f"match {slot} q", floor=Q_FLOOR)
        except InputError as e:
            errors.append(str(e)); continue
        for note, what in ((p_note, "p"), (q_note, "public split")):
            if note:
                warnings.append(f"match {slot} ({label}): {what} {note}")
        if q is None:
            q = list(p)
            warnings.append(f"match {slot} ({label}): no public split; the crowd is assumed to pick in line with the true odds")
        if m.get("q_estimated"):
            warnings.append(f"match {slot} ({label}): public split is an estimate, not observed")
        matches.append({"slot": slot, "label": label, "p": p, "q": q, "has_q": m.get("q") is not None})
    if errors:
        raise InputError("; ".join(errors))
    try:
        turnover = float(data.get("turnover_nok") or 0)
    except (TypeError, ValueError):
        raise InputError("turnover_nok must be a number")
    if turnover <= 0:
        turnover = 2_500_000.0
        warnings.append("no turnover given; assuming 2.5 M NOK (typical round). Expected payout per NOK barely depends on it")
    return {"price": price, "budget": budget, "max_budget": max_budget, "requested": requested, "capped": capped,
            "bankroll": bankroll, "cap_pct": cap_pct, "goal": goal, "matches": matches, "turnover": turnover,
            "samples": int(data.get("samples", 5000)), "final_samples": int(data.get("final_samples", 100000)),
            "seed": int(data.get("seed", 7))}, warnings


# ----------------------------------------------------------------------------- payout model
def poisson_pmf_iter(lam, upto):
    p = math.exp(-lam)
    for x in range(upto + 1):
        yield x, p
        p *= lam / (x + 1)


def floor_prize(amount):
    return math.floor(amount / ROUND_DOWN + 1e-9) * ROUND_DOWN


def tier_payout(pot, a, lam, min_prize=0.0):
    """Expected NOK we receive from one tier: a of our rows, Poisson(lam) other winning rows."""
    if a <= 0 or pot <= 0:
        return 0.0
    if lam >= POISSON_EXACT_BELOW:
        prize = floor_prize(pot / (a + lam))
        return a * prize if prize >= min_prize else 0.0
    total = 0.0
    for x, pmf in poisson_pmf_iter(lam, int(lam + 9 * math.sqrt(lam + 1) + 12)):
        prize = floor_prize(pot / (a + x))
        if prize >= min_prize:
            total += pmf * a * prize
    return total


def crowd_poly(q, o, n_tiers=3):
    """P(a row picked like the public has exactly k wrong) for k = 0, 1, 2, given the result o."""
    poly = [1.0] + [0.0] * (n_tiers - 1)
    for i, k in enumerate(o):
        qi = q[i][k]
        new = [0.0] * n_tiers
        for d in range(n_tiers):
            new[d] += poly[d] * qi
            if d + 1 < n_tiers:
                new[d + 1] += poly[d] * (1.0 - qi)
        poly = new
    return poly


def pots_for(turnover, lam2):
    """(pot12, pot11, pot10, cancelled10) given the expected number of OTHER tier-10 rows."""
    pool = PRIZE_SHARE * turnover
    pot12, pot11, pot10 = (pool * s for s in TIER_SHARE)
    w10 = max(lam2, 1.0)
    cancelled = floor_prize(pot10 / w10) < MIN_PRIZE
    if cancelled:
        pot12 += pot10 / 2
        pot11 += pot10 / 2
    return pot12, pot11, pot10, cancelled


def outcome_payout(q, turnover_rows, turnover, o, a):
    """Expected NOK from all three tiers if the result is o and we hold a = (a0, a1, a2) rows."""
    c = crowd_poly(q, o)
    lam = [KAPPA[k] * turnover_rows * c[k] for k in range(3)]
    pot12, pot11, pot10, cancelled = pots_for(turnover, lam[2])
    total = tier_payout(pot12, a[0], lam[0]) + tier_payout(pot11, a[1], lam[1])
    if not cancelled:
        total += tier_payout(pot10, a[2], lam[2], MIN_PRIZE)
    return total


def row_counts(masks, o):
    """Our rows with exactly 0, 1, 2 wrong picks for the result o (tuple of outcome indices)."""
    miss, ns = [], [bin(m).count("1") for m in masks]
    wrong = [n - 1 for n in ns]
    for i, k in enumerate(o):
        if not (masks[i] >> k) & 1:
            miss.append(i)
            if len(miss) > 2:
                return (0, 0, 0)
    s1 = sum(wrong)
    if not miss:
        e2 = (s1 * s1 - sum(w * w for w in wrong)) / 2
        return (1, s1, e2)
    if len(miss) == 1:
        i = miss[0]
        return (0, ns[i], ns[i] * (s1 - wrong[i]))
    i, j = miss
    return (0, 0, ns[i] * ns[j])


# ----------------------------------------------------------------------------- evaluator
class Evaluator:
    def __init__(self, matches, turnover, price, samples, seed):
        self.n = len(matches)
        self.p = [m["p"] for m in matches]
        self.q = [m["q"] for m in matches]
        self.turnover = turnover
        self.rows_total = turnover / price
        self.rng = random.Random(seed)
        cum = [(p[0], p[0] + p[1]) for p in self.p]
        self.samples = []
        self.lam1, self.lam2, self.pot11, self.pot10, self.cancel = [], [], [], [], []
        for _ in range(samples):
            u = [self.rng.random() for _ in range(self.n)]
            o = tuple(0 if u[i] < cum[i][0] else 1 if u[i] < cum[i][1] else 2 for i in range(self.n))
            c = crowd_poly(self.q, o)
            lam = [KAPPA[k] * self.rows_total * c[k] for k in range(3)]
            pot12, pot11, pot10, cancelled = pots_for(turnover, lam[2])
            self.samples.append(o)
            self.lam1.append(lam[1]); self.lam2.append(lam[2])
            self.pot11.append(pot11); self.pot10.append(pot10); self.cancel.append(cancelled)

    def evaluate(self, masks, detail=False):
        """Expected payout (NOK) of the system, plus chance of any prize and a standard error."""
        ns = [bin(m).count("1") for m in masks]
        wrong = [n - 1 for n in ns]
        s1 = sum(wrong)
        e2_all = (s1 * s1 - sum(w * w for w in wrong)) / 2
        total = total_sq = 0.0
        prizes = 0
        for idx, o in enumerate(self.samples):
            m1 = m2 = -1
            miss = 0
            for i in range(self.n):
                if not (masks[i] >> o[i]) & 1:
                    miss += 1
                    if miss > 2:
                        break
                    if miss == 1:
                        m1 = i
                    else:
                        m2 = i
            if miss > 2:
                continue
            if miss == 0:
                a1, a2 = s1, e2_all
                prizes += 1
            elif miss == 1:
                a1, a2 = ns[m1], ns[m1] * (s1 - wrong[m1])
                prizes += 1
            else:
                a1, a2 = 0, ns[m1] * ns[m2]
                if not self.cancel[idx]:
                    prizes += 1
            value = 0.0
            if a1:
                value += tier_payout(self.pot11[idx], a1, self.lam1[idx])
            if a2 and not self.cancel[idx]:
                value += tier_payout(self.pot10[idx], a2, self.lam2[idx], MIN_PRIZE)
            total += value
            total_sq += value * value
        m = len(self.samples)
        mc = total / m
        # tier 12: exact over our own rows
        ev12 = 0.0
        for o in itertools.product(*[[k for k in range(3) if (mask >> k) & 1] for mask in masks]):
            prob = 1.0
            for i, k in enumerate(o):
                prob *= self.p[i][k]
            c = crowd_poly(self.q, o)
            lam = [KAPPA[k] * self.rows_total * c[k] for k in range(3)]
            pot12 = pots_for(self.turnover, lam[2])[0]
            ev12 += prob * tier_payout(pot12, 1, lam[0])
        var = max(total_sq / m - mc * mc, 0.0)
        return {"ev": mc + ev12, "ev12": ev12, "ev_mc": mc, "se": math.sqrt(var / m), "p_prize": prizes / m}


# ----------------------------------------------------------------------------- system helpers
def rows_of(masks):
    r = 1
    for m in masks:
        r *= bin(m).count("1")
    return r


def mass(match, mask):
    return sum(match["p"][k] for k in range(3) if (mask >> k) & 1)


def exact_hit_probs(matches, masks):
    """Exact P(best row has 0 / <=1 / <=2 wrong) from the per-match covered probabilities."""
    poly = [1.0, 0.0, 0.0]
    for m, mask in zip(matches, masks):
        s = mass(m, mask)
        new = [0.0] * 3
        for d in range(3):
            new[d] += poly[d] * s
            if d + 1 < 3:
                new[d + 1] += poly[d] * (1 - s)
        poly = new
    return poly[0], poly[0] + poly[1], poly[0] + poly[1] + poly[2]


def neutral_value(matches, masks):
    """Exact expected payout if every winning row paid a typical prize (no sharing, crowd ignored)."""
    poly = [1.0, 0.0, 0.0]
    for m, mask in zip(matches, masks):
        s, n = mass(m, mask), bin(mask).count("1")
        new = [0.0] * 3
        for d in range(3):
            new[d] += poly[d] * s
            if d + 1 < 3:
                new[d + 1] += poly[d] * (n - s)
        poly = new
    return sum(v * c for v, c in zip(TYPICAL_PRIZE, poly))


def search(matches, evaluator, max_rows, goal, floor=None, start_masks=None):
    """Greedy fill, then single-match local moves. goal: prize-chance | balanced."""
    n = len(matches)
    cache = {}

    def score(masks):
        key = tuple(masks)
        if key not in cache:
            nev = neutral_value(matches, masks)
            if goal == "prize-chance":
                cache[key] = nev
            else:
                ev = evaluator.evaluate(masks)["ev"]
                if goal == "balanced" and floor and nev < floor:
                    ev *= (nev / floor) ** 3
                cache[key] = ev
        return cache[key]

    seeds = []
    if start_masks and rows_of(start_masks) <= max_rows:
        seeds.append(list(start_masks))
    base = [1 << max(range(3), key=lambda k: m["p"][k]) for m in matches]
    if base not in seeds:
        seeds.append(base)
    if goal == "balanced":
        value = [1 << max(range(3), key=lambda k: m["p"][k] * m["p"][k] / m["q"][k]) for m in matches]
        if value not in seeds:
            seeds.append(value)
    best_masks, best_score = None, -1.0
    for masks in seeds:
        masks = list(masks)
        cur = score(masks)
        while True:  # greedy fill: the single outcome with the best gain per extra row
            options = []
            for i in range(n):
                for k in range(3):
                    if (masks[i] >> k) & 1:
                        continue
                    trial = masks[:]
                    trial[i] |= 1 << k
                    r = rows_of(trial)
                    if r <= max_rows:
                        s = score(trial)
                        if s > cur:
                            options.append(((s - cur) / (r - rows_of(masks)), s, trial))
            if not options:
                break
            _, cur, masks = max(options, key=lambda o: o[0])
        improved = True
        while improved:  # local refinement: any single-match change of the mark set
            improved = False
            for i in range(n):
                for new in range(1, 8):
                    if new == masks[i]:
                        continue
                    trial = masks[:]
                    trial[i] = new
                    if rows_of(trial) > max_rows:
                        continue
                    s = score(trial)
                    if s > cur + 1e-12:
                        cur, masks, improved = s, trial, True
            if not improved and goal == "prize-chance":  # the exact objective is cheap: also try two matches at once
                for i, j in itertools.combinations(range(n), 2):
                    for mi in range(1, 8):
                        for mj in range(1, 8):
                            if (mi, mj) == (masks[i], masks[j]):
                                continue
                            trial = masks[:]
                            trial[i], trial[j] = mi, mj
                            if rows_of(trial) > max_rows:
                                continue
                            s = score(trial)
                            if s > cur + 1e-12:
                                cur, masks, improved = s, trial, True
        if cur > best_score:
            best_masks, best_score = masks, cur
    return best_masks


def public_system(matches, max_rows):
    """Baseline: what following the public ("Folket") looks like at this budget."""
    masks = [1 << max(range(3), key=lambda k: m["q"][k]) for m in matches]
    while True:
        best = None
        for i, m in enumerate(matches):
            for k in range(3):
                if (masks[i] >> k) & 1:
                    continue
                trial = masks[:]
                trial[i] |= 1 << k
                r = rows_of(trial)
                if r > max_rows:
                    continue
                cur_mass = sum(m["q"][j] for j in range(3) if (masks[i] >> j) & 1)
                gain = m["q"][k] / cur_mass
                score = (gain - 1) / (r - rows_of(masks))
                if best is None or score > best[0]:
                    best = (score, trial)
        if not best:
            return masks
        masks = best[1]


def hit_system(matches, max_rows):
    """Baseline: the system with the best chance of all correct (exact, by dynamic programming over rows)."""
    options = []
    for m in matches:
        order = sorted(range(3), key=lambda k: -m["p"][k])
        options.append([(n, sum(1 << k for k in order[:n]), sum(m["p"][k] for k in order[:n])) for n in (1, 2, 3)])
    dp = {1: (1.0, ())}
    for opts in options:
        nxt = {}
        for rows, (prob, choice) in dp.items():
            for n, mask, ms in opts:
                r2 = rows * n
                if r2 > max_rows:
                    continue
                if r2 not in nxt or prob * ms > nxt[r2][0]:
                    nxt[r2] = (prob * ms, choice + (mask,))
        dp = nxt
    return list(dp[max(dp, key=lambda r: dp[r][0])][1])


# ----------------------------------------------------------------------------- planning
def describe(matches, masks, tier, tier_budget, price, final_eval, baselines, strategy):
    marks, mean_vi, win_vi = [], 1.0, 1.0
    for m, mask in zip(matches, masks):
        outs = [k for k in range(3) if (mask >> k) & 1]
        ratio = [m["p"][k] / m["q"][k] for k in range(3)]
        s = sum(m["p"][k] for k in outs)
        mean_vi *= sum(ratio[k] for k in outs) / len(outs)
        win_vi *= sum(m["p"][k] * ratio[k] for k in outs) / s
        marks.append({"slot": m["slot"], "label": m["label"], "outcomes": [OUTCOMES[k] for k in outs],
                      "mark": "".join(MARK[OUTCOMES[k]] for k in outs), "cover": {1: "single", 2: "half", 3: "full"}[len(outs)],
                      "p_covered": round(s, 4), "p": {OUTCOMES[k]: round(m["p"][k], 4) for k in range(3)},
                      "q": {OUTCOMES[k]: round(m["q"][k], 4) for k in range(3)} if m["has_q"] else None,
                      "value_ratio": {OUTCOMES[k]: round(ratio[k], 3) for k in range(3)} if m["has_q"] else None})
    rows = rows_of(masks)
    p12, p11, p10 = exact_hit_probs(matches, masks)
    cost = rows * price
    has_q = any(m["has_q"] for m in matches)
    return {
        "tier": tier, "strategy": strategy, "tier_budget_nok": round(tier_budget, 2), "rows": rows, "cost_nok": round(cost, 2),
        "marks": marks,
        "p_all_correct": p12, "one_in": round(1 / p12) if p12 > 0 else None,
        "p_11_or_more_correct": p11, "p_10_or_more_correct": p10,
        "p_any_prize": round(final_eval["p_prize"], 4),
        "expected_payout_nok": round(final_eval["ev"], 2),
        "expected_payout_per_nok": round(final_eval["ev"] / cost, 4),
        "expected_payout_se_nok": round(final_eval["se"], 2),
        "baselines": baselines,
        "mean_row_value_index": round(mean_vi, 4) if has_q else None,
        "win_value_index": round(win_vi, 4) if has_q else None,
    }


def build(data):
    cfg, warnings = parse_input(data)
    matches, price = cfg["matches"], cfg["price"]
    caps = [("cheap", math.floor(round(cfg["budget"] * 0.5 / price, 9))), ("base", math.floor(round(cfg["budget"] / price, 9)))]
    if cfg["max_budget"] is not None and cfg["max_budget"] > cfg["budget"]:
        caps.append(("max", math.floor(round(cfg["max_budget"] / price, 9))))
    if caps[1][1] < 1:
        raise InputError("budget does not cover a single row")
    search_eval = Evaluator(matches, cfg["turnover"], price, cfg["samples"], cfg["seed"])
    final_eval = Evaluator(matches, cfg["turnover"], price, cfg["final_samples"], cfg["seed"] + 1)
    plans, seen, previous = [], set(), None
    for tier, cap in caps:
        cap = max(cap, 1)
        found = {}
        found["prize-chance"] = search(matches, search_eval, cap, "prize-chance", start_masks=previous)
        floor = BALANCED_FLOOR * neutral_value(matches, found["prize-chance"])
        found["balanced"] = search(matches, search_eval, cap, "balanced", floor=floor, start_masks=found["prize-chance"])
        chosen = found[cfg["goal"]]
        key = tuple(chosen)
        if key in seen:
            warnings.append(f"tier '{tier}' identical to a cheaper tier; omitted")
            continue
        seen.add(key)
        previous = chosen
        base = {"follow_the_public": public_system(matches, cap), "maximise_chance_of_all_correct": hit_system(matches, cap)}
        baselines = {}
        for name, bm in base.items():
            ev = final_eval.evaluate(bm)
            baselines[name] = {"rows": rows_of(bm), "expected_payout_per_nok": round(ev["ev"] / (rows_of(bm) * price), 4),
                               "marks": ["".join(MARK[OUTCOMES[k]] for k in range(3) if (m >> k) & 1) for m in bm]}
        plan = describe(matches, chosen, tier, cap * price, price, final_eval.evaluate(chosen), baselines, cfg["goal"])
        plan["alternatives"] = {}
        for name in GOALS:
            if name != cfg["goal"]:
                alt = describe(matches, found[name], tier, cap * price, price, final_eval.evaluate(found[name]), {}, name)
                plan["alternatives"][name] = {k: alt[k] for k in (
                    "strategy", "rows", "cost_nok", "marks", "p_all_correct", "p_10_or_more_correct", "p_any_prize",
                    "expected_payout_nok", "expected_payout_per_nok", "expected_payout_se_nok")}
        plans.append(plan)
    return {"goal": cfg["goal"], "row_price_nok": price, "budget_nok": cfg["budget"],
            "requested_budget_nok": cfg["requested"], "budget_capped": cfg["capped"],
            "bankroll_nok": cfg["bankroll"], "cap_pct": cfg["cap_pct"], "turnover_nok": cfg["turnover"],
            "risk": {"balanced": "balanced", "prize-chance": "safe"}[cfg["goal"]],
            "model": {"prize_share": PRIZE_SHARE, "tier_share": list(TIER_SHARE), "samples": cfg["samples"],
                      "final_samples": cfg["final_samples"], "seed": cfg["seed"]},
            "plans": plans, "warnings": warnings}


def to_text(result):
    lines = [f"goal={result['goal']}  row price={result['row_price_nok']:g} NOK  turnover assumed {result['turnover_nok']:,.0f} NOK".replace(",", " ")]
    for plan in result["plans"]:
        lines += ["", f"[{plan['tier']}] {plan['rows']} rows, {plan['cost_nok']:g} NOK: expected payout "
                      f"{plan['expected_payout_nok']:g} NOK ({plan['expected_payout_per_nok']:.2f} per NOK, "
                      f"se {plan['expected_payout_se_nok']:g}), chance of any prize {plan['p_any_prize']:.0%}, "
                      f"12 correct 1 in {plan['one_in']:,}".replace(",", " ")]
        b = plan["baselines"]
        lines.append("    per NOK: follow the public {:.2f} | maximise chance of all correct {:.2f}".format(
            b["follow_the_public"]["expected_payout_per_nok"], b["maximise_chance_of_all_correct"]["expected_payout_per_nok"]))
        for m in plan["marks"]:
            lines.append(f"    {m['slot']:>2}  {m['mark']:<4} {m['cover']:<6} {m['label']}")
    lines += [f"warning: {w}" for w in result["warnings"]]
    return "\n".join(lines)


def input_from_files(value_path, coupon_path, options, day=None):
    """Assemble the input from the value model's output and the fetched coupon, plus command-line options."""
    with open(value_path, encoding="utf-8") as f:
        value = json.load(f)
    with open(coupon_path, encoding="utf-8") as f:
        coupon = json.load(f)
    coupons = coupon.get("coupons") or []
    if not coupons:
        raise InputError("the coupon file has no coupons")
    if day:
        coupons = [c for c in coupons if c["day"].lower() == day.lower()] or coupons
    chosen = coupons[0]
    data = {"row_price_nok": chosen["row_price_nok"], "turnover_nok": chosen.get("turnover_estimate_nok") or chosen["turnover_nok"],
            "matches": value["optimizer_matches"]}
    for flag, key in (("--budget", "budget_nok"), ("--max-budget", "max_budget_nok"), ("--bankroll", "bankroll_nok"),
                      ("--cap-pct", "cap_pct"), ("--goal", "goal"), ("--samples", "samples"), ("--final-samples", "final_samples"), ("--seed", "seed")):
        if flag in options:
            data[key] = options[flag] if flag == "--goal" else float(options[flag])
    return data


def main(argv):
    args, options, positional, i = argv[1:], {}, [], 0
    value_flags = ("--value", "--coupon", "--day", "--budget", "--max-budget", "--bankroll", "--cap-pct", "--goal",
                   "--samples", "--final-samples", "--seed", "--out")
    while i < len(args):
        if args[i] in value_flags and i + 1 < len(args):
            options[args[i]] = args[i + 1]; i += 2
        elif args[i] == "--text":
            options["--text"] = True; i += 1
        elif args[i].startswith("--"):
            print(__doc__, file=sys.stderr); return 2
        else:
            positional.append(args[i]); i += 1
    from_files = "--value" in options or "--coupon" in options
    if (from_files and (positional or "--value" not in options or "--coupon" not in options)) or (not from_files and len(positional) != 1):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if from_files:
            data = input_from_files(options["--value"], options["--coupon"], options, options.get("--day"))
        else:
            data = json.loads(sys.stdin.read() if positional[0] == "-" else open(positional[0], encoding="utf-8").read())
        result = build(data)
    except (InputError, OSError, json.JSONDecodeError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2)
    if "--out" in options:
        with open(options["--out"], "w", encoding="utf-8") as f:
            f.write(text)
    print(to_text(result) if "--text" in options else text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
