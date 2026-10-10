import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/oddsen/skills"


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rnd = load("render", "oddsen-tipping-coupon-output/scripts/render.py")
opt = load("optimize", "oddsen-tipping-coupon-optimizer/scripts/optimize.py")
adj = load("adjust", "oddsen-tipping-value-model/scripts/adjust.py")
eng = load("engine", "oddsen-tipping-probability-engine/scripts/engine.py")

EXAMPLE = json.loads((SKILLS / "oddsen-tipping-coupon-output/examples/full-coupon.json").read_text())


def example(**kw):
    data = copy.deepcopy(EXAMPLE)
    data.update(kw)
    return data


class Rendering(unittest.TestCase):
    def test_recommends_largest_tier_within_cap(self):
        out = rnd.build(example())
        self.assertEqual(out["recommended_tier"], "base")  # max is 4.8 % of a 1000 NOK bankroll
        self.assertIn("1.60 % of bankroll", out["markdown"])
        self.assertTrue(any("'max' tier is above" in w for w in out["warnings"]))

    def test_cost_always_shown_as_share_of_bankroll(self):
        md = rnd.build(example(bankroll_nok=500, cap_pct=4))["markdown"]
        self.assertIn("3.20 % of bankroll", md)  # 16 NOK of 500 NOK

    def test_cheapest_plan_over_cap_warns(self):
        out = rnd.build(example(bankroll_nok=100))
        self.assertEqual(out["recommended_tier"], "cheap")
        self.assertTrue(any("above the 2 % cap" in w for w in out["warnings"]))

    def test_closing_text_and_core_sections(self):
        md = rnd.build(example())["markdown"]
        for needle in ("Estimated, not certain", "Hjelpelinjen", "## What could be wrong", "## Sources",
                       "Copy into your own coupon", "nothing is placed for you", "independently"):
            self.assertIn(needle, md)

    def test_excluded_matches_are_called_out(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("Not covered by this plan", md)
        self.assertIn("#7", md)

    def test_estimated_split_and_low_confidence_are_surfaced(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("Public split is an estimate for match(es) #2", md)
        self.assertIn("Low-confidence match(es): #2", md)

    def test_own_why_text_overrides_auto_text(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("62 % of the public back it", md)

    def test_pipes_in_text_do_not_break_the_table(self):
        data = example(why={"1": "a | b"})
        md = rnd.build(data)["markdown"]
        self.assertIn("a / b", md)

    def test_stale_source_and_deadline_warnings(self):
        data = example(now="2026-10-10T14:30:00Z", max_source_age_hours=2)
        warnings = rnd.build(data)["warnings"]
        self.assertTrue(any("h old" in w for w in warnings))
        self.assertTrue(any("Less than an hour" in w for w in warnings))
        warnings = rnd.build(example(now="2026-10-10T16:00:00Z"))["warnings"]
        self.assertTrue(any("deadline has passed" in w for w in warnings))

    def test_every_possible_row_is_flagged(self):
        res = opt.optimize({"row_price_nok": 1, "budget_nok": 9, "risk": "balanced", "matches": [
            {"slot": 1, "label": "a", "p": {"H": .5, "U": .3, "B": .2}},
            {"slot": 2, "label": "b", "p": {"H": .4, "U": .3, "B": .3}}]})
        out = rnd.build({"bankroll_nok": 10000, "optimizer_result": res, "matches": []})
        self.assertTrue(any("every possible row" in w for w in out["warnings"]))


class Guardrails(unittest.TestCase):
    def test_overconfident_wording_is_rejected(self):
        for text in ("This is a safe pick", "A sure thing", "It's a lock", "Certain to win", "Guaranteed",
                     "helt sikker", "Banker of the week"):
            with self.assertRaises(rnd.InputError, msg=text):
                rnd.build(example(why={"1": text}))
            with self.assertRaises(rnd.InputError, msg=text):
                rnd.build(example(notes=[text]))

    def test_uncertain_and_unlock_style_words_are_fine(self):
        rnd.build(example(why={"1": "Highly uncertain match; the blockade at the back may matter"}))

    def test_bankroll_required_and_positive(self):
        for bad in (None, 0, -5, "abc"):
            data = example()
            data["bankroll_nok"] = bad
            with self.assertRaises(rnd.InputError):
                rnd.build(data)

    def test_no_plans(self):
        with self.assertRaises(rnd.InputError):
            rnd.build({"bankroll_nok": 100, "optimizer_result": {"plans": []}})


class EndToEnd(unittest.TestCase):
    """Odds -> probabilities -> adjustments -> covers -> report, all on pasted data."""

    def test_pipeline(self):
        now = "2026-10-10T12:00:00Z"
        quotes = {
            1: [("sharp", 1.90, 3.60, 4.40), ("soft", 1.80, 3.40, 4.00)],
            2: [("sharp", 2.60, 3.30, 2.90)],
            3: [("sharp", 3.00, 3.30, 2.40), ("soft", 2.80, 3.20, 2.30)],
            4: [("sharp", 1.60, 3.90, 6.00)],
        }
        matches = [{"slot": s, "label": f"Match {s}", "quotes": [
            {"book": b, "odds": {"H": h, "U": u, "B": a}, "fetched_at": "2026-10-10T11:30:00Z"}
            for b, h, u, a in qs]} for s, qs in quotes.items()]
        e = eng.run({"now": now, "matches": matches})
        splits = {1: (.60, .22, .18), 2: (.38, .28, .34), 3: (.30, .22, .48), 4: (.70, .18, .12)}
        vm_in = []
        for m in e["matches"]:
            vm_in.append({"slot": m["slot"], "label": m["label"], "p_fair": m["p_fair"],
                          "confidence": m["confidence"], "q": dict(zip("HUB", splits[m["slot"]])),
                          "adjustments": []})
        vm = adj.run({"matches": vm_in})
        res = opt.optimize({"row_price_nok": 1, "budget_nok": 6, "max_budget_nok": 12,
                            "risk": "balanced", "matches": vm["optimizer_matches"]})
        out = rnd.build({"bankroll_nok": 1000, "now": now, "optimizer_result": res,
                         "matches": vm["matches"], "excluded": vm["excluded"],
                         "sources": [{"name": "pasted odds", "fetched_at": "2026-10-10T11:30:00Z"}]})
        self.assertIn("% of bankroll", out["markdown"])
        self.assertEqual(out["markdown"].count("| **"), 4)  # one table row per match


if __name__ == "__main__":
    unittest.main()
