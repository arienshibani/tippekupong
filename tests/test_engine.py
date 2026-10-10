import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/oddsen/skills/oddsen-tipping-probability-engine"
spec = importlib.util.spec_from_file_location("engine", SKILL / "scripts/engine.py")
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

EXAMPLE = json.loads((SKILL / "examples/two-matches.json").read_text())
NOW = "2026-10-10T12:00:00Z"


def quote(book, h, u, b, fetched="2026-10-10T11:00:00Z", **extra):
    return dict({"book": book, "odds": {"H": h, "U": u, "B": b}, "fetched_at": fetched}, **extra)


def run(quotes, **kw):
    data = dict({"now": NOW, "matches": [{"slot": 1, "label": "m", "quotes": quotes}]}, **kw)
    return eng.run(data)["matches"][0]


class Devig(unittest.TestCase):
    def test_reference_example_from_odds_math(self):
        odds = {"H": 2.40, "U": 3.30, "B": 3.00}
        self.assertAlmostEqual(eng.booksum(odds) - 1, 0.0530, places=3)
        p, used, _ = eng.devig(odds, "multiplicative")
        self.assertEqual(used, "multiplicative")
        self.assertAlmostEqual(p["H"], (1 / 2.40) / eng.booksum(odds), places=9)

    def test_every_method_sums_to_one(self):
        for odds in ({"H": 2.40, "U": 3.30, "B": 3.00}, {"H": 1.20, "U": 7.00, "B": 15.0}):
            for method in eng.METHODS:
                p, _, _ = eng.devig(odds, method)
                self.assertAlmostEqual(sum(p.values()), 1.0, places=9, msg=(method, odds))
                self.assertTrue(all(v > 0 for v in p.values()))

    def test_power_and_shin_shift_probability_to_the_favourite(self):
        odds = {"H": 1.20, "U": 7.00, "B": 15.0}
        mult, _, _ = eng.devig(odds, "multiplicative")
        for method in ("power", "shin"):
            p, _, _ = eng.devig(odds, method)
            self.assertGreater(p["H"], mult["H"], method)
            self.assertLess(p["B"], mult["B"], method)

    def test_additive_falls_back_when_it_would_go_negative(self):
        odds = {"H": 1.01, "U": 30.0, "B": 100.0}
        p, used, note = eng.devig(odds, "additive")
        self.assertEqual(used, "multiplicative")
        self.assertIn("non-positive", note)
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)

    def test_no_margin_market_is_normalised_with_a_note(self):
        p, used, note = eng.devig({"H": 2.0, "U": 4.0, "B": 4.0}, "shin")
        self.assertEqual(used, "multiplicative")
        self.assertIsNotNone(note)
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)


class Consensus(unittest.TestCase):
    def test_single_book_equals_its_devig_and_is_low_confidence(self):
        m = run([quote("A", 2.40, 3.30, 3.00)])
        p, _, _ = eng.devig({"H": 2.40, "U": 3.30, "B": 3.00}, "multiplicative")
        for k in "HUB":
            self.assertAlmostEqual(m["p_fair"][k], p[k], places=5)
        self.assertEqual(m["confidence"], "low")
        self.assertIn("single book", m["confidence_reasons"])
        self.assertIsNone(m["spread_top_outcome"])

    def test_lower_margin_book_gets_more_weight(self):
        sharp = quote("sharp", 2.00, 3.50, 4.20)       # ~2.4 % margin
        soft = quote("soft", 1.80, 3.20, 3.80)         # ~10 % margin
        m = run([sharp, soft])
        shares = {b["book"]: b["weight_share"] for b in m["books"]}
        self.assertGreater(shares["sharp"], shares["soft"])
        self.assertAlmostEqual(sum(shares.values()), 1.0, places=2)
        self.assertAlmostEqual(sum(m["p_fair"].values()), 1.0, places=5)

    def test_explicit_weight_multiplies(self):
        a = run([quote("a", 2.0, 3.5, 4.2), quote("b", 2.0, 3.5, 4.2, weight=3.0)])
        shares = {b["book"]: b["weight_share"] for b in a["books"]}
        self.assertAlmostEqual(shares["b"], 0.75, places=2)

    def test_stale_and_invalid_quotes_are_dropped_with_reasons(self):
        m = run([
            quote("fresh", 2.0, 3.5, 4.2),
            quote("old", 2.2, 3.3, 3.5, fetched="2026-10-10T02:00:00Z"),
            {"book": "partial", "odds": {"H": 2.0, "U": 3.0}, "fetched_at": "2026-10-10T11:00:00Z"},
            quote("badodds", 0.9, 3.0, 3.0),
            quote("badtime", 2.0, 3.0, 3.0, fetched="yesterday-ish"),
        ])
        self.assertEqual(m["n_books"], 1)
        reasons = {d["book"]: d["reason"] for d in m["dropped"]}
        self.assertIn("stale", reasons["old"])
        self.assertIn("need decimal odds", reasons["partial"])
        self.assertIn("need decimal odds", reasons["badodds"])
        self.assertIn("unreadable", reasons["badtime"])

    def test_norwegian_decimal_commas_are_accepted(self):
        m = run([{"book": "pasted", "odds": {"H": "2,40", "U": " 3,30", "B": "3.00"},
                  "fetched_at": "2026-10-10T11:00:00Z"}])
        p, _, _ = eng.devig({"H": 2.40, "U": 3.30, "B": 3.00}, "multiplicative")
        self.assertAlmostEqual(m["p_fair"]["H"], p["H"], places=5)

    def test_no_usable_quote_means_no_market_and_no_made_up_numbers(self):
        m = run([])
        self.assertEqual(m["status"], "no_market")
        self.assertIsNone(m["p_fair"])

    def test_disagreeing_books_lower_confidence(self):
        m = run([quote("a", 1.50, 4.0, 7.0), quote("b", 2.10, 3.4, 3.6)])
        self.assertEqual(m["confidence"], "low")
        self.assertTrue(any("disagree" in r for r in m["confidence_reasons"]))

    def test_undated_quote_is_kept_but_flagged(self):
        q = quote("pasted", 2.4, 3.3, 3.0)
        del q["fetched_at"]
        m = run([q])
        self.assertEqual(m["status"], "ok")
        self.assertIn("undated quote", m["confidence_reasons"])

    def test_bad_method_is_rejected(self):
        with self.assertRaises(eng.InputError):
            eng.run({"method": "magic", "matches": [{"quotes": []}]})
        empty = eng.run({"matches": []})  # allowed: nothing on the coupon had bookmaker odds
        self.assertEqual((empty["matches"], empty["optimizer_matches"]), ([], []))


class SecondRunFixes(unittest.TestCase):
    def test_time_without_a_zone_is_dropped_with_a_clear_reason(self):
        m = run([quote("a", 2.0, 3.5, 4.2, fetched="2026-10-10T11:00:00")])
        self.assertEqual(m["status"], "no_market")
        self.assertIn("offset", m["dropped"][0]["reason"])

    def test_offset_times_are_converted_not_misread(self):
        # 13:30 at +02:00 is 11:30 UTC, i.e. 30 minutes old at 12:00 UTC.
        m = run([quote("a", 2.0, 3.5, 4.2, fetched="2026-10-10T13:30:00+02:00")], max_age_hours=1)
        self.assertEqual(m["status"], "ok")
        # 07:00 at +02:00 is 05:00 UTC, i.e. 7 h old.
        m = run([quote("a", 2.0, 3.5, 4.2, fetched="2026-10-10T07:00:00+02:00")])
        self.assertIn("stale", m["dropped"][0]["reason"])

    def test_now_without_a_zone_is_an_input_error(self):
        with self.assertRaises(eng.InputError):
            eng.run({"now": "2026-10-10T12:00:00", "matches": [{"quotes": []}]})

    def test_excluded_entries_carry_the_dropped_reasons(self):
        result = eng.run({"now": NOW, "matches": [{"slot": 5, "label": "x", "quotes": [
            quote("old", 2.3, 3.3, 3.1, fetched="2026-10-10T04:00:00Z")]}]})
        entry = result["excluded"][0]
        self.assertEqual(entry["slot"], 5)
        self.assertIn("stale (8.0 h old)", entry["dropped"][0]["reason"])

    def test_text_mode_shows_margin_weight_and_time_per_book(self):
        text = eng.to_text(eng.run(EXAMPLE))
        self.assertIn("margin", text)
        self.assertIn("weight", text)
        self.assertIn("taken 2026-10-10T11:40:00Z", text)


class ExampleAndHandoff(unittest.TestCase):
    def test_example_runs_and_hands_off_to_the_optimizer(self):
        result = eng.run(EXAMPLE)
        by_slot = {m["slot"]: m for m in result["matches"]}
        self.assertEqual(by_slot[1]["n_books"], 2)  # the 10-hour-old quote is dropped
        self.assertEqual(by_slot[3]["status"], "no_market")
        self.assertEqual([e["slot"] for e in result["excluded"]], [3])

        spec2 = importlib.util.spec_from_file_location(
            "optimize", ROOT / "plugins/oddsen/skills/oddsen-tipping-coupon-optimizer/scripts/optimize.py")
        opt = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(opt)
        plan = opt.optimize({"row_price_nok": 1, "budget_nok": 4,
                             "matches": result["optimizer_matches"]})
        self.assertEqual(len(plan["plans"][-1]["marks"]), 2)


if __name__ == "__main__":
    unittest.main()
