import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/oddsen/skills/oddsen-tipping-value-model"
spec = importlib.util.spec_from_file_location("adjust", SKILL / "scripts/adjust.py")
adj = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adj)

EXAMPLE = json.loads((SKILL / "examples/three-matches.json").read_text())
P = {"H": 0.50, "U": 0.30, "B": 0.20}
Q = {"H": 0.60, "U": 0.25, "B": 0.15}


def adjustment(outcome, delta, **kw):
    base = {"outcome": outcome, "delta_pp": delta, "reason": "r", "source": "s", "status": "confirmed"}
    return dict(base, **kw)


def one(adjustments=None, **kw):
    m = dict({"slot": 1, "label": "m", "p_fair": P, "q": Q, "adjustments": adjustments or []}, **kw)
    return adj.run({"matches": [m]})["matches"][0]


class Basics(unittest.TestCase):
    def test_no_adjustments_leaves_probabilities_unchanged(self):
        r = one()
        for k in "HUB":
            self.assertAlmostEqual(r["p_est"][k], P[k], places=6)
        self.assertEqual(r["confidence"], "high")

    def test_value_ratio_is_p_est_over_q(self):
        r = one()
        self.assertAlmostEqual(r["value_ratio"]["H"], 0.50 / 0.60, places=3)
        self.assertAlmostEqual(r["value_ratio"]["B"], 0.20 / 0.15, places=3)

    def test_balanced_adjustment_moves_probability(self):
        r = one([adjustment("H", -3), adjustment("B", 3)])
        self.assertAlmostEqual(r["p_est"]["H"], 0.47, places=6)
        self.assertAlmostEqual(r["p_est"]["B"], 0.23, places=6)
        self.assertAlmostEqual(sum(r["p_est"].values()), 1.0, places=6)

    def test_unbalanced_adjustment_is_renormalised(self):
        r = one([adjustment("H", -4)])
        self.assertAlmostEqual(sum(r["p_est"].values()), 1.0, places=6)
        self.assertLess(r["p_est"]["H"], 0.50)
        self.assertGreater(r["p_est"]["U"], 0.30)  # the freed mass is spread proportionally

    def test_missing_split_gives_no_ratio_and_lower_confidence(self):
        r = adj.run({"matches": [{"slot": 1, "label": "m", "p_fair": P}]})["matches"][0]
        self.assertIsNone(r["value_ratio"])
        self.assertIn("no public split", r["confidence_reasons"])

    def test_q_floor_prevents_exploding_ratios(self):
        r = one(q={"H": 0.0, "U": 0.5, "B": 0.5})
        self.assertLess(r["value_ratio"]["H"], 30)


class Guards(unittest.TestCase):
    def test_unconfirmed_news_is_a_flag_not_a_number(self):
        r = one([adjustment("H", -4, status="unconfirmed")])
        self.assertAlmostEqual(r["p_est"]["H"], P["H"], places=6)
        self.assertTrue(any(f.startswith("unconfirmed") for f in r["risk_flags"]))
        self.assertIn("unconfirmed team news", r["confidence_reasons"])

    def test_priced_in_news_is_not_applied(self):
        r = one([adjustment("H", -4, market_likely_priced_in=True)])
        self.assertAlmostEqual(r["p_est"]["H"], P["H"], places=6)
        self.assertIn("priced this in", r["rejected"][0]["why"])

    def test_adjustment_without_reason_or_source_is_rejected(self):
        r = one([adjustment("H", -2, reason=""), adjustment("B", 2, source=" ")])
        self.assertEqual(r["applied"], [])
        self.assertEqual({x["why"] for x in r["rejected"]}, {"no reason given", "no source given"})

    def test_bad_outcome_or_delta_is_rejected(self):
        r = one([adjustment("X", 2), {"outcome": "H", "delta_pp": "lots", "reason": "r", "source": "s"}])
        self.assertEqual(r["applied"], [])
        self.assertEqual(len(r["rejected"]), 2)

    def test_per_outcome_cap(self):
        r = one([adjustment("H", -9)])
        # H is capped at -5 pp: 0.45 / (0.45 + 0.30 + 0.20) after renormalising.
        self.assertAlmostEqual(r["p_est"]["H"], 0.45 / 0.95, places=5)
        self.assertIn("adjustments were capped", r["confidence_reasons"])
        self.assertTrue(any("caps" in f for f in r["risk_flags"]))

    def test_per_match_cap_scales_total_movement(self):
        r = one([adjustment("H", -5), adjustment("B", 5), adjustment("U", -5)])
        # 15 pp requested, scaled to 8 pp in total: each moves 8/3 pp, then renormalised.
        step = 0.08 / 3
        raw = {"H": 0.50 - step, "U": 0.30 - step, "B": 0.20 + step}
        total = sum(raw.values())
        for k in "HUB":
            self.assertAlmostEqual(r["p_est"][k], raw[k] / total, places=5)

    def test_user_approval_lifts_caps(self):
        r = one([adjustment("H", -9)], user_approved=True)
        self.assertEqual(r["risk_flags"], [])
        self.assertAlmostEqual(r["p_est"]["H"], 0.41 / 0.91, places=5)  # full -9 pp, renormalised

    def test_probability_floor(self):
        r = adj.run({"matches": [{"slot": 1, "label": "m", "p_fair": {"H": 0.02, "U": 0.48, "B": 0.50},
                                  "user_approved": True, "adjustments": [adjustment("H", -9)]}]})["matches"][0]
        self.assertGreaterEqual(r["p_est"]["H"], 0.009)

    def test_tiny_delta_is_flagged_as_a_probable_unit_mistake(self):
        r = one([adjustment("H", -0.03)])
        self.assertTrue(any("check the unit" in f for f in r["risk_flags"]))
        self.assertEqual(one([adjustment("H", -3)])["risk_flags"], [])

    def test_percentages_instead_of_fractions_get_a_hint(self):
        with self.assertRaises(adj.InputError) as ctx:
            adj.run({"matches": [{"slot": 1, "p_fair": {"H": 51, "U": 27, "B": 22}}]})
        self.assertIn("fractions", str(ctx.exception))

    def test_many_adjustments_lower_confidence(self):
        r = one([adjustment("H", -1), adjustment("U", 1), adjustment("B", 0.5)])
        self.assertIn("3 adjustments applied", r["confidence_reasons"])

    def test_engine_low_confidence_and_estimated_split_stack(self):
        r = one(confidence="low", q_estimated=True)
        self.assertEqual(r["confidence"], "low")
        self.assertEqual(len(r["confidence_reasons"]), 2)


class ExampleAndHandoff(unittest.TestCase):
    def test_example(self):
        result = adj.run(EXAMPLE)
        by_slot = {m["slot"]: m for m in result["matches"]}
        self.assertEqual(len(by_slot[1]["applied"]), 2)
        self.assertEqual(len(by_slot[2]["applied"]), 0)
        self.assertEqual(len(by_slot[2]["rejected"]), 2)
        self.assertEqual(by_slot[3]["status"], "no_market")
        self.assertEqual([e["slot"] for e in result["excluded"]], [3])

    def test_handoff_to_optimizer_includes_q(self):
        result = adj.run(EXAMPLE)
        spec2 = importlib.util.spec_from_file_location(
            "optimize", ROOT / "plugins/oddsen/skills/oddsen-tipping-coupon-optimizer/scripts/optimize.py")
        opt = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(opt)
        plan = opt.optimize({"row_price_nok": 1, "budget_nok": 4, "risk": "contrarian",
                             "matches": result["optimizer_matches"]})
        self.assertEqual(len(plan["plans"][-1]["marks"]), 2)
        self.assertTrue(any("estimate" in w for w in plan["warnings"]))  # q_estimated carried over

    def test_empty_and_invalid_input(self):
        with self.assertRaises(adj.InputError):
            adj.run({"matches": []})
        with self.assertRaises(adj.InputError):
            adj.run({"matches": [{"slot": 1, "p_fair": {"H": 0.5, "U": 0.3, "B": 0.3}}]})


if __name__ == "__main__":
    unittest.main()
