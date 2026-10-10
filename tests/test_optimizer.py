import importlib.util
import itertools
import json
import math
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/oddsen/skills/oddsen-tipping-coupon-optimizer"
spec = importlib.util.spec_from_file_location("optimize", SKILL / "scripts/optimize.py")
opt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opt)

EXAMPLE = json.loads((SKILL / "examples/three-match.json").read_text())


def match(p, q=None, slot=1):
    m = {"slot": slot, "p": dict(zip("HUB", p))}
    if q:
        m["q"] = dict(zip("HUB", q))
    return m


def random_probs(rng):
    raw = [rng.random() + 0.05 for _ in range(3)]
    s = sum(raw)
    return [x / s for x in raw]


def brute_force(matches, max_rows):
    """Best P over every non-empty subset of outcomes in every match."""
    subsets = [s for n in (1, 2, 3) for s in itertools.combinations("HUB", n)]
    best = 0.0
    for combo in itertools.product(subsets, repeat=len(matches)):
        if math.prod(len(s) for s in combo) > max_rows:
            continue
        prob = math.prod(sum(m["p"][k] for k in s) for m, s in zip(matches, combo))
        best = max(best, prob)
    return best


class WorkedExample(unittest.TestCase):
    """Numbers from shared/tipping-pool-math.md."""

    def test_two_row_budget_covers_the_flattest_match(self):
        data = dict(EXAMPLE, budget_nok=2, risk="safe")
        plan = opt.optimize(data)["plans"][-1]
        self.assertEqual(plan["rows"], 2)
        self.assertAlmostEqual(plan["p_all_correct"], 0.55 * 0.70 * 0.42, places=6)
        covers = {m["slot"]: m["cover"] for m in plan["marks"]}
        # Match 2 has the least dominant top outcome (.40), so it gets the half cover.
        self.assertEqual(covers, {1: "single", 2: "half", 3: "single"})

    def test_single_row_is_most_likely_outcome_per_match(self):
        data = dict(EXAMPLE, budget_nok=1, risk="safe")
        plan = opt.optimize(data)["plans"][-1]
        self.assertEqual(plan["rows"], 1)
        self.assertAlmostEqual(plan["p_all_correct"], 0.55 * 0.40 * 0.42, places=6)

    def test_value_ratios_match_reference_table(self):
        cfg, _ = opt.parse_input(EXAMPLE)
        ratios = opt.value_ratios(cfg["matches"][2])
        self.assertAlmostEqual(ratios["H"], 1.50, places=2)
        self.assertAlmostEqual(ratios["B"], 0.70, places=2)


class Optimality(unittest.TestCase):
    def test_dp_matches_brute_force_for_safe_risk(self):
        rng = random.Random(7)
        for _ in range(40):
            n = rng.randint(1, 5)
            matches = [match(random_probs(rng), slot=i + 1) for i in range(n)]
            max_rows = rng.randint(1, 3 ** n)
            _, prob, _ = opt.solve(
                [dict(m, q=None) for m in matches], lam=0.0, max_rows=max_rows)
            self.assertAlmostEqual(prob, brute_force(matches, max_rows), places=9)

    def test_rows_never_exceed_budget(self):
        rng = random.Random(11)
        for _ in range(40):
            n = rng.randint(1, 8)
            data = {
                "row_price_nok": rng.choice([0.5, 1, 2.5]),
                "budget_nok": rng.randint(1, 300),
                "risk": rng.choice(["safe", "balanced", "contrarian"]),
                "matches": [match(random_probs(rng), random_probs(rng), i + 1) for i in range(n)],
            }
            if data["budget_nok"] < data["row_price_nok"]:
                continue
            for plan in opt.optimize(data)["plans"]:
                self.assertLessEqual(plan["cost_nok"], data["budget_nok"] + 1e-9)
                self.assertEqual(plan["rows"], math.prod(len(m["outcomes"]) for m in plan["marks"]))

    def test_more_budget_never_lowers_probability(self):
        data = dict(EXAMPLE, row_price_nok=1, budget_nok=6, max_budget_nok=27, risk="balanced")
        probs = [p["p_all_correct"] for p in opt.optimize(data)["plans"]]
        self.assertEqual(probs, sorted(probs))

    def test_each_plan_reports_the_budget_it_was_built_for(self):
        data = dict(EXAMPLE, row_price_nok=1, budget_nok=4, max_budget_nok=9, risk="safe")
        plans = {p["tier"]: p for p in opt.optimize(data)["plans"]}
        self.assertEqual(plans["cheap"]["tier_budget_nok"], 2)
        self.assertEqual(plans["base"]["tier_budget_nok"], 4)
        self.assertEqual(plans["max"]["tier_budget_nok"], 9)
        for p in plans.values():
            self.assertLessEqual(p["cost_nok"], p["tier_budget_nok"])

    def test_full_cover_when_budget_allows(self):
        data = dict(EXAMPLE, budget_nok=27, risk="safe")
        plan = opt.optimize(data)["plans"][-1]
        self.assertAlmostEqual(plan["p_all_correct"], 1.0, places=9)
        self.assertEqual(plan["rows"], 27)


class BankrollCap(unittest.TestCase):
    matches = [{"slot": i, "label": f"m{i}", "p": {"H": .45, "U": .30, "B": .25}} for i in range(1, 9)]

    def run_opt(self, **kw):
        data = {"row_price_nok": 2, "budget_nok": 100, "bankroll_nok": 2500, "risk": "safe", "matches": self.matches}
        data.update(kw)
        return opt.optimize(data)

    def test_over_cap_budget_is_cut_to_the_cap(self):
        res = self.run_opt()  # 100 NOK is 4 % of 2500 NOK; the 2 % cap is 50 NOK
        self.assertTrue(res["budget_capped"])
        self.assertEqual(res["requested_budget_nok"], 100)
        self.assertEqual(res["budget_nok"], 50)
        for plan in res["plans"]:
            self.assertLessEqual(plan["cost_nok"], 50 + 1e-9)
        self.assertTrue(any("above the 2 % cap" in w and "built at the cap (50 NOK)" in w for w in res["warnings"]))

    def test_budget_that_was_never_exactly_twice_the_cap_is_cut_too(self):
        for budget in (120, 150, 999):
            res = self.run_opt(budget_nok=budget)
            self.assertLessEqual(max(p["cost_nok"] for p in res["plans"]), 50 + 1e-9, budget)

    def test_max_budget_above_the_cap_is_cut_and_tiers_merge(self):
        res = self.run_opt(budget_nok=50, max_budget_nok=500)
        self.assertLessEqual(max(p["cost_nok"] for p in res["plans"]), 50 + 1e-9)
        self.assertTrue(any("max budget" in w for w in res["warnings"]))

    def test_budget_within_the_cap_is_untouched(self):
        res = self.run_opt(budget_nok=40)
        self.assertFalse(res["budget_capped"])
        self.assertEqual(res["budget_nok"], 40)

    def test_user_set_cap_is_used(self):
        res = self.run_opt(budget_nok=100, cap_pct=4)
        self.assertFalse(res["budget_capped"])
        res = self.run_opt(budget_nok=100, cap_pct=1)
        self.assertEqual(res["budget_nok"], 25)

    def test_cap_below_one_row_is_an_error(self):
        with self.assertRaises(opt.InputError):
            self.run_opt(bankroll_nok=50, row_price_nok=2)  # 2 % of 50 NOK = 1 NOK < one row

    def test_without_a_bankroll_nothing_is_capped(self):
        data = {"row_price_nok": 2, "budget_nok": 100, "risk": "safe", "matches": self.matches}
        res = opt.optimize(data)
        self.assertFalse(res["budget_capped"])
        self.assertEqual(res["budget_nok"], 100)


class RiskPreference(unittest.TestCase):
    def test_contrarian_prefers_under_owned_outcome_in_a_single(self):
        # Outcome U is slightly less likely but far less crowded than H.
        m = match([0.45, 0.40, 0.15], [0.75, 0.10, 0.15])
        data = {"row_price_nok": 1, "budget_nok": 1, "matches": [m]}
        safe = opt.optimize(dict(data, risk="safe"))["plans"][-1]
        bold = opt.optimize(dict(data, risk="contrarian"))["plans"][-1]
        self.assertEqual(safe["marks"][0]["mark"], "H")
        self.assertEqual(bold["marks"][0]["mark"], "U")

    def test_missing_split_warns_and_is_neutral(self):
        data = {"row_price_nok": 1, "budget_nok": 2, "matches": [match([0.5, 0.3, 0.2])]}
        result = opt.optimize(data)
        self.assertTrue(any("no public split" in w for w in result["warnings"]))
        self.assertIsNone(result["plans"][-1]["mean_row_value_index"])


class Validation(unittest.TestCase):
    def test_probabilities_must_sum_to_one(self):
        with self.assertRaises(opt.InputError):
            opt.optimize({"row_price_nok": 1, "budget_nok": 1, "matches": [match([0.5, 0.3, 0.3])]})

    def test_clean_percentages_are_accepted_silently(self):
        data = {"row_price_nok": 1, "budget_nok": 1, "matches": [
            {"slot": 1, "label": "x", "p": {"H": 51, "U": 27, "B": 22}}]}
        result = opt.optimize(data)
        self.assertEqual([w for w in result["warnings"] if "percentages" in w], [])
        self.assertAlmostEqual(result["plans"][-1]["marks"][0]["p_covered"], 0.51, places=2)

    def test_percentages_that_do_not_add_to_100_are_noted(self):
        data = {"row_price_nok": 1, "budget_nok": 3, "matches": [
            {"slot": 1, "label": "x", "p": {"H": 51, "U": 27, "B": 23}}]}
        result = opt.optimize(data)
        self.assertTrue(any("given as percentages adding to 101 %; divided by the total" in w for w in result["warnings"]))

    def test_rounding_errors_are_rescaled_not_rejected(self):
        for triple in ({"H": .48, "U": .27, "B": .26}, {"H": 48, "U": 27, "B": 26}, {"H": 0.5, "U": 0.3, "B": 0.21}):
            result = opt.optimize({"row_price_nok": 1, "budget_nok": 2,
                                   "matches": [{"slot": 1, "label": "x", "p": triple}]})
            self.assertTrue(any("divided by the total" in w for w in result["warnings"]), triple)

    def test_nonsense_totals_are_rejected_and_all_failing_matches_are_listed(self):
        bad = {"H": 0.5, "U": 0.3, "B": 0.3}  # adds to 1.1
        with self.assertRaises(opt.InputError) as ctx:
            opt.optimize({"row_price_nok": 1, "budget_nok": 2, "matches": [
                {"slot": 1, "p": bad}, {"slot": 2, "p": {"H": .5, "U": .3, "B": .2}}, {"slot": 3, "p": bad}]})
        message = str(ctx.exception)
        self.assertIn("match 1", message)
        self.assertIn("match 3", message)
        self.assertNotIn("match 2", message)

    def test_budget_below_one_row(self):
        with self.assertRaises(opt.InputError):
            opt.optimize(dict(EXAMPLE, row_price_nok=5, budget_nok=4))

    def test_missing_required_fields(self):
        with self.assertRaises(opt.InputError):
            opt.optimize({"matches": EXAMPLE["matches"]})
        with self.assertRaises(opt.InputError):
            opt.optimize({"row_price_nok": 1, "budget_nok": 1, "matches": []})

    def test_public_split_floor_avoids_exploding_ratios(self):
        m = match([0.3, 0.3, 0.4], [0.0, 0.5, 0.5])
        cfg, _ = opt.parse_input({"row_price_nok": 1, "budget_nok": 1, "matches": [m]})
        self.assertGreater(cfg["matches"][0]["q"]["H"], 0)
        self.assertLess(opt.value_ratios(cfg["matches"][0])["H"], 20)


if __name__ == "__main__":
    unittest.main()
