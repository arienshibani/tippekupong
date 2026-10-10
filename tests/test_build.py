import importlib.util
import itertools
import json
import math
import random
import statistics
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "build", ROOT / "plugins/tippekupong/skills/tippekupong-optimizer/scripts/build.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

HISTORY = json.loads((ROOT / "tests/fixtures/nt_history_60_rounds.json").read_text())["games"]
IDX = {"H": 0, "U": 1, "B": 2}


def mini_matches(n=5, seed=3):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        raw = [rng.random() + 0.2 for _ in range(3)]
        p = [x / sum(raw) for x in raw]
        raw = [x * (0.7 + 0.6 * rng.random()) for x in p]
        q = [x / sum(raw) for x in raw]
        out.append({"slot": i + 1, "label": f"m{i + 1}", "p": p, "q": q, "has_q": True})
    return out


class PayoutRulesAgainstRealRounds(unittest.TestCase):
    """The rule in shared/tipping-payout-rules.md must reproduce the prizes Norsk Tipping actually paid."""

    @staticmethod
    def predict(turnover, w12, w11, w10):
        pool = b.PRIZE_SHARE * turnover
        pot12, pot11, pot10 = (pool * s for s in b.TIER_SHARE)
        prize10 = b.floor_prize(pot10 / w10) if w10 else 0
        if prize10 < b.MIN_PRIZE:
            prize10 = 0
            pot12 += pot10 / 2
            pot11 += pot10 / 2
        return (b.floor_prize(pot12 / w12) if w12 else 0, b.floor_prize(pot11 / w11) if w11 else 0, prize10)

    def test_prize_per_winner_matches_history(self):
        exact = {"12": 0, "11": 0, "10": 0}
        total = {"12": 0, "11": 0, "10": 0}
        for g in HISTORY:
            w, a = g["winners"], g["prize_nok"]
            pred = dict(zip(("12", "11", "10"), self.predict(g["turnover_nok"], w["12"], w["11"], w["10"])))
            for tier in ("12", "11", "10"):
                if w[tier] == 0 or (tier == "12" and w[tier] <= 1):
                    continue  # no winners, or a lone winner who also gets the bonus pool
                total[tier] += 1
                exact[tier] += pred[tier] == a[tier]
        self.assertEqual(exact["10"], total["10"])        # 60 of 60 when this was written
        self.assertGreaterEqual(exact["11"], total["11"] - 2)  # 59 of 60
        self.assertGreaterEqual(exact["12"], total["12"] - 6)  # 46 of 50; misses are bonus-pool carry-overs, always upward
        for g in HISTORY:  # a carry-over only ever adds money, never removes it
            w, a = g["winners"], g["prize_nok"]
            if w["12"] > 1:
                self.assertGreaterEqual(a["12"] + 5, self.predict(g["turnover_nok"], w["12"], w["11"], w["10"])[0])

    def test_independent_crowd_model_predicts_winner_counts(self):
        for tier, k, low, high in (("11", 1, 0.85, 1.15), ("10", 2, 0.85, 1.20)):
            ratios = []
            for g in HISTORY:
                q = [[x / 100 for x in row] for row in g["public"]]
                res = [IDX[r] for r in g["results"]]
                poly = b.crowd_poly(q, res)
                expected = g["turnover_nok"] * poly[k]
                if expected > 0 and g["winners"][tier] > 0:
                    ratios.append(g["winners"][tier] / expected)
            self.assertGreater(len(ratios), 50)
            self.assertTrue(low <= statistics.median(ratios) <= high, (tier, statistics.median(ratios)))

    def test_tier_ten_is_cancelled_in_a_quarter_of_history(self):
        cancelled = sum(1 for g in HISTORY if g["prize_nok"]["10"] == 0 and g["winners"]["10"] > 0)
        self.assertEqual(cancelled, 15)
        self.assertGreater(cancelled / len(HISTORY), 0.2)


class Mechanics(unittest.TestCase):
    def test_floor_prize_and_pots(self):
        self.assertEqual(b.floor_prize(1269.9), 1265)
        self.assertEqual(b.floor_prize(4.99), 0)
        pot12, pot11, pot10, cancelled = b.pots_for(2_000_000, 500)       # plenty of room: tier 10 paid
        self.assertFalse(cancelled)
        self.assertAlmostEqual(pot12, 0.55 * 0.27 * 2_000_000)
        pot12c, pot11c, _, cancelled = b.pots_for(2_000_000, 500_000)     # 3.4 NOK each: cancelled
        self.assertTrue(cancelled)
        self.assertAlmostEqual(pot12c - pot12, pot10 / 2)
        self.assertAlmostEqual(pot11c - pot11, pot10 / 2)

    def test_tier_payout_is_continuous_across_the_poisson_switch(self):
        below = b.tier_payout(100_000, 3, b.POISSON_EXACT_BELOW - 0.01)
        above = b.tier_payout(100_000, 3, b.POISSON_EXACT_BELOW + 0.01)
        self.assertAlmostEqual(below / above, 1.0, delta=0.03)

    def test_tier_payout_edge_cases(self):
        self.assertEqual(b.tier_payout(1000, 0, 5), 0.0)
        self.assertEqual(b.tier_payout(0, 3, 5), 0.0)
        self.assertEqual(b.tier_payout(1000, 1, 1000, min_prize=10.0), 0.0)  # prize 0.99 < 10
        self.assertGreater(b.tier_payout(1000, 1, 50, min_prize=10.0), 0.0)  # prize 19 >= 10
        # a lone row with nobody else in the tier takes the whole pot (rounded down)
        self.assertAlmostEqual(b.tier_payout(1000, 1, 1e-9), 1000, delta=1.0)

    def test_row_counts_match_enumeration(self):
        rng = random.Random(5)
        for _ in range(60):
            n = rng.randint(3, 6)
            masks = [rng.randint(1, 7) for _ in range(n)]
            o = tuple(rng.randint(0, 2) for _ in range(n))
            counts = [0, 0, 0]
            for row in itertools.product(*[[k for k in range(3) if (m >> k) & 1] for m in masks]):
                wrong = sum(1 for i in range(n) if row[i] != o[i])
                if wrong < 3:
                    counts[wrong] += 1
            self.assertEqual(list(b.row_counts(masks, o)), counts, (masks, o))

    def test_neutral_value_matches_enumeration(self):
        ms = mini_matches(5)
        rng = random.Random(9)
        for _ in range(8):
            masks = [rng.randint(1, 7) for _ in ms]
            expected = 0.0
            for o in itertools.product(range(3), repeat=5):
                prob = math.prod(ms[i]["p"][o[i]] for i in range(5))
                expected += prob * sum(v * c for v, c in zip(b.TYPICAL_PRIZE, b.row_counts(masks, o)))
            self.assertAlmostEqual(b.neutral_value(ms, masks), expected, places=9)

    def test_exact_hit_probabilities_sum_correctly(self):
        ms = mini_matches(5)
        masks = [3, 1, 7, 2, 5]
        p0, p1, p2 = b.exact_hit_probs(ms, masks)
        brute = [0.0, 0.0, 0.0]
        for o in itertools.product(range(3), repeat=5):
            miss = sum(1 for i in range(5) if not (masks[i] >> o[i]) & 1)
            if miss < 3:
                brute[miss] += math.prod(ms[i]["p"][o[i]] for i in range(5))
        self.assertAlmostEqual(p0, brute[0], places=12)
        self.assertAlmostEqual(p1, brute[0] + brute[1], places=12)
        self.assertAlmostEqual(p2, sum(brute), places=12)


class EvaluatorAgainstBruteForce(unittest.TestCase):
    def brute(self, ms, masks, turnover, price):
        rows_total = turnover / price
        total = 0.0
        for o in itertools.product(range(3), repeat=len(ms)):
            prob = math.prod(ms[i]["p"][o[i]] for i in range(len(ms)))
            total += prob * b.outcome_payout([m["q"] for m in ms], rows_total, turnover, o, b.row_counts(masks, o))
        return total

    def test_monte_carlo_agrees_with_full_enumeration(self):
        ms = mini_matches(6, seed=4)
        for turnover in (30_000.0, 400_000.0):
            ev = b.Evaluator(ms, turnover, 1.0, 40_000, seed=11)
            for masks in ([1, 2, 4, 1, 2, 4], [3, 1, 6, 2, 1, 5], [7, 3, 1, 1, 1, 2]):
                exact = self.brute(ms, masks, turnover, 1.0)
                got = ev.evaluate(masks)["ev"]
                self.assertAlmostEqual(got / exact, 1.0, delta=0.06, msg=(turnover, masks, got, exact))

    def test_expected_payout_scales_with_rows_for_independent_equal_rows(self):
        # Doubling a hopeless match to a full cover adds rows and so adds expected payout.
        ms = mini_matches(6, seed=2)
        ev = b.Evaluator(ms, 200_000.0, 1.0, 20_000, seed=3)
        small = ev.evaluate([1, 1, 1, 1, 1, 1])["ev"]
        wide = ev.evaluate([7, 7, 1, 1, 1, 1])["ev"]
        self.assertGreater(wide, small)


class Search(unittest.TestCase):
    def all_systems(self, n, max_rows):
        for masks in itertools.product(range(1, 8), repeat=n):
            if b.rows_of(masks) <= max_rows:
                yield list(masks)

    def test_prize_chance_search_is_near_the_exact_optimum(self):
        ms = mini_matches(5, seed=8)
        ev = b.Evaluator(ms, 100_000.0, 1.0, 200, seed=1)
        for max_rows in (4, 12, 40):
            best = max(b.neutral_value(ms, m) for m in self.all_systems(5, max_rows))
            got = b.neutral_value(ms, b.search(ms, ev, max_rows, "prize-chance"))
            self.assertGreaterEqual(got, 0.97 * best, max_rows)

    def test_search_respects_the_row_limit(self):
        ms = mini_matches(6, seed=6)
        ev = b.Evaluator(ms, 100_000.0, 1.0, 300, seed=1)
        for goal in b.GOALS:
            for max_rows in (1, 6, 20):
                masks = b.search(ms, ev, max_rows, goal, floor=0.5 * b.neutral_value(ms, [7] * 6))
                self.assertLessEqual(b.rows_of(masks), max_rows)

    def test_balanced_keeps_most_of_the_prize_chance(self):
        ms = mini_matches(6, seed=5)
        ev = b.Evaluator(ms, 200_000.0, 1.0, 1500, seed=2)
        pc = b.search(ms, ev, 24, "prize-chance")
        floor = b.BALANCED_FLOOR * b.neutral_value(ms, pc)
        bal = b.search(ms, ev, 24, "balanced", floor=floor, start_masks=pc)
        self.assertGreaterEqual(b.neutral_value(ms, bal), 0.9 * floor)
        self.assertGreaterEqual(ev.evaluate(bal)["ev"], 0.97 * ev.evaluate(pc)["ev"])

    def test_baselines(self):
        ms = mini_matches(6, seed=1)
        pub = b.public_system(ms, 12)
        self.assertLessEqual(b.rows_of(pub), 12)
        hit = b.hit_system(ms, 12)
        self.assertLessEqual(b.rows_of(hit), 12)
        best = max(math.prod(sum(ms[i]["p"][k] for k in range(3) if (m[i] >> k) & 1) for i in range(6))
                   for m in self.all_systems(6, 12))
        got = math.prod(sum(ms[i]["p"][k] for k in range(3) if (hit[i] >> k) & 1) for i in range(6))
        self.assertAlmostEqual(got, best, places=12)


class BuildEndToEnd(unittest.TestCase):
    def data(self, **kw):
        ms = mini_matches(8, seed=12)
        base = {"row_price_nok": 1, "budget_nok": 24, "turnover_nok": 1_500_000, "samples": 600, "final_samples": 3000,
                "matches": [{"slot": m["slot"], "label": m["label"], "p": dict(zip("HUB", m["p"])),
                             "q": dict(zip("HUB", m["q"]))} for m in ms]}
        base.update(kw)
        return base

    def test_plans_respect_budget_and_describe_every_match(self):
        result = b.build(self.data(max_budget_nok=60))
        self.assertEqual([p["tier"] for p in result["plans"]], ["cheap", "base", "max"])
        for plan in result["plans"]:
            self.assertLessEqual(plan["cost_nok"], plan["tier_budget_nok"] + 1e-9)
            self.assertEqual(len(plan["marks"]), 8)
            self.assertEqual(plan["rows"], math.prod(len(m["outcomes"]) for m in plan["marks"]))
            self.assertEqual(set(plan["baselines"]), {"follow_the_public", "maximise_chance_of_all_correct"})
            self.assertEqual(list(plan["alternatives"]), ["prize-chance"])
            self.assertGreater(plan["expected_payout_nok"], 0)
            self.assertGreater(plan["p_10_or_more_correct"], plan["p_all_correct"])
        spend = [p["cost_nok"] for p in result["plans"]]
        self.assertEqual(spend, sorted(spend))

    def test_bankroll_cap_cuts_every_tier(self):
        result = b.build(self.data(budget_nok=100, max_budget_nok=300, bankroll_nok=1000))
        self.assertTrue(result["budget_capped"])
        self.assertEqual(result["requested_budget_nok"], 100)
        for plan in result["plans"]:
            self.assertLessEqual(plan["cost_nok"], 20 + 1e-9)  # 2 % of 1000 NOK
        self.assertTrue(any("above the 2 % cap" in w for w in result["warnings"]))

    def test_same_input_gives_the_same_output(self):
        a, c = b.build(self.data()), b.build(self.data())
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(c, sort_keys=True))

    def test_prize_chance_goal_raises_the_chance_of_a_prize(self):
        balanced = b.build(self.data(goal="balanced"))["plans"][-1]
        chance = b.build(self.data(goal="prize-chance"))["plans"][-1]
        self.assertGreaterEqual(chance["p_10_or_more_correct"] + 1e-9, 0.9 * balanced["p_10_or_more_correct"])
        self.assertEqual(chance["strategy"], "prize-chance")

    def test_crowd_following_pays_less_per_nok_than_the_balanced_plan(self):
        # The public picks are crowded, so shared prizes make them worth less per NOK (60 real rounds agree).
        plan = b.build(self.data(budget_nok=48, final_samples=20000))["plans"][-1]
        self.assertGreaterEqual(plan["expected_payout_per_nok"], 0.97 * plan["baselines"]["follow_the_public"]["expected_payout_per_nok"])

    def test_inputs_are_validated(self):
        bad = self.data()
        bad["matches"][0]["p"] = {"H": 0.5, "U": 0.3, "B": 0.3}
        with self.assertRaises(b.InputError):
            b.build(bad)
        with self.assertRaises(b.InputError):
            b.build(self.data(matches=self.data()["matches"][:2]))
        with self.assertRaises(b.InputError):
            b.build(self.data(goal="jackpot"))
        with self.assertRaises(b.InputError):
            b.build(self.data(budget_nok=0))
        with self.assertRaises(b.InputError):
            b.build(self.data(budget_nok=100, bankroll_nok=40))  # 2 % of 40 NOK < one row

    def test_percentages_missing_split_and_missing_turnover_are_handled_with_warnings(self):
        d = self.data()
        d["matches"][0]["p"] = {k: v * 100 for k, v in d["matches"][0]["p"].items()}
        del d["matches"][1]["q"]
        del d["turnover_nok"]
        result = b.build(d)
        text = " ".join(result["warnings"])
        self.assertIn("no public split", text)
        self.assertIn("assuming 2.5 M NOK", text)
        self.assertIsNone(result["plans"][0]["marks"][1]["q"])

    def test_old_risk_names_still_map(self):
        self.assertEqual(b.build(self.data(risk="safe"))["goal"], "prize-chance")
        self.assertEqual(b.build(self.data(risk="contrarian"))["goal"], "balanced")


if __name__ == "__main__":
    unittest.main()
