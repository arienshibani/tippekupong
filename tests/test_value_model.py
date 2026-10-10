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

    def test_several_unconfirmed_items_become_one_flag(self):
        r = one([adjustment("H", -3, status="unconfirmed", reason="may rotate"),
                 adjustment("B", 3, status="unconfirmed", reason="may rotate")])
        flags = [f for f in r["risk_flags"] if "unconfirmed" in f]
        self.assertEqual(len(flags), 1)
        self.assertIn("H -3 pp, B +3 pp", flags[0])
        self.assertEqual(flags[0].count("may rotate"), 1)

    def test_no_market_match_keeps_dropped_quote_reasons(self):
        dropped = [{"book": "soft", "reason": "stale (8.0 h old)"}]
        result = adj.run({"matches": [{"slot": 5, "label": "x", "p_fair": None, "dropped": dropped}]})
        self.assertEqual(result["excluded"][0]["dropped"], dropped)

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

    def test_percentages_and_rounding_are_accepted_with_a_note(self):
        r = adj.run({"matches": [{"slot": 1, "p_fair": {"H": 50, "U": 30, "B": 20},
                                  "q": {"H": 49, "U": 27, "B": 25}}]})["matches"][0]
        self.assertAlmostEqual(r["p_est"]["H"], 0.5, places=6)
        self.assertAlmostEqual(sum(r["q"].values()), 1.0, places=5)
        self.assertIn("given as percentages adding to 101 %", r["split_note"])
        self.assertTrue(any("public split" in n for n in r["notes"]))
        clean = adj.run({"matches": [{"slot": 1, "p_fair": {"H": 50, "U": 30, "B": 20},
                                      "q": {"H": 49, "U": 27, "B": 24}}]})["matches"][0]
        self.assertIsNone(clean["split_note"])  # exactly 100 %: nothing to say
        self.assertEqual(clean["notes"], [])

    def test_nonsense_totals_are_rejected_and_every_failing_match_is_listed(self):
        bad = {"H": .5, "U": .3, "B": .3}
        with self.assertRaises(adj.InputError) as ctx:
            adj.run({"matches": [{"slot": 1, "p_fair": bad}, {"slot": 2, "p_fair": P}, {"slot": 3, "p_fair": bad}]})
        self.assertIn("match 1", str(ctx.exception))
        self.assertIn("match 3", str(ctx.exception))

    def test_confidence_counts_news_items_not_adjustment_legs(self):
        mirrored = one([adjustment("H", -2, source="club"), adjustment("U", 1, source="club"),
                        adjustment("B", 1, source="club")])
        self.assertEqual(mirrored["confidence_reasons"], [])  # one news item split three ways
        many = one([adjustment("H", -1, source="a"), adjustment("U", 1, source="b"), adjustment("B", 0.5, source="c")])
        self.assertIn("3 news items applied", many["confidence_reasons"])

    def test_engine_low_confidence_and_estimated_split_stack(self):
        r = one(confidence="low", q_estimated=True)
        self.assertEqual(r["confidence"], "low")
        self.assertEqual(len(r["confidence_reasons"]), 2)


class Timing(unittest.TestCase):
    """News is judged against the times the odds were taken (books[].fetched_at)."""
    BOOKS = [{"book": "sharp", "fetched_at": "2026-10-10T11:30:00Z"},
             {"book": "soft", "fetched_at": "2026-10-10T11:10:00Z"}]
    NOW = "2026-10-10T12:00:00Z"

    def news(self, source_time, **kw):
        m = {"slot": 1, "label": "m", "p_fair": P, "q": Q, "books": self.BOOKS,
             "adjustments": [adjustment("H", -3, source_time=source_time, **kw), adjustment("B", 3, source_time=source_time, **kw)]}
        return adj.run({"now": self.NOW, "matches": [m]})["matches"][0]

    def test_news_well_before_the_odds_is_priced_in(self):
        r = self.news("2026-10-10T10:15:00+00:00")  # 55 min before the earliest odds
        self.assertEqual(r["applied"], [])
        self.assertIn("announced 55 min before the earliest odds", r["rejected"][0]["why"])
        self.assertAlmostEqual(r["p_est"]["H"], P["H"], places=6)

    def test_news_after_the_latest_odds_is_applied(self):
        r = self.news("2026-10-10T11:40:00Z")
        self.assertEqual(len(r["applied"]), 2)
        self.assertAlmostEqual(r["p_est"]["H"], 0.47, places=6)

    def test_news_close_to_the_odds_times_is_flagged_not_applied(self):
        r = self.news("2026-10-10T11:00:00Z")  # 10 min before the earliest odds: too close to call
        self.assertEqual(r["applied"], [])
        self.assertIn("too close", r["rejected"][0]["why"])
        self.assertTrue(any("could not tell if it was priced in" in f for f in r["risk_flags"]))
        between = self.news("2026-10-10T11:20:00Z")  # between the two quotes
        self.assertEqual(between["applied"], [])

    def test_gap_is_exactly_fifteen_minutes(self):
        self.assertEqual(self.news("2026-10-10T10:55:00Z")["applied"], [])           # 15 min: priced in
        self.assertIn("priced this in", self.news("2026-10-10T10:55:00Z")["rejected"][0]["why"])
        self.assertIn("too close", self.news("2026-10-10T10:56:00Z")["rejected"][0]["why"])  # 14 min

    def test_explicit_flag_beats_the_automatic_rule(self):
        r = self.news("2026-10-10T11:40:00Z", market_likely_priced_in=True)
        self.assertEqual(r["applied"], [])
        r = self.news("2026-10-10T10:15:00Z", market_likely_priced_in=False)
        self.assertEqual(len(r["applied"]), 2)

    def test_without_times_or_books_the_script_does_not_guess(self):
        m = {"slot": 1, "label": "m", "p_fair": P, "adjustments": [adjustment("H", -3), adjustment("B", 3)]}
        self.assertEqual(len(adj.run({"now": self.NOW, "matches": [m]})["matches"][0]["applied"]), 2)
        zoneless = self.news("2026-10-10T10:15:00")  # no zone: ignored for timing, applied
        self.assertEqual(len(zoneless["applied"]), 2)

    def test_fresh_news_gets_a_note(self):
        r = self.news("2026-10-10T11:45:00Z")  # 15 min before "now"
        self.assertEqual(sum("only 15 min old" in n for n in r["notes"]), 1)  # one note for the news item, not per leg
        self.assertTrue(any(n.startswith("news applied: H -3 pp, B +3 pp") for n in r["notes"]))
        older = adj.run({"now": "2026-10-10T14:00:00Z", "matches": [{"slot": 1, "label": "m", "p_fair": P, "books": self.BOOKS,
                         "adjustments": [adjustment("H", -3, source_time="2026-10-10T11:45:00Z")]}]})["matches"][0]
        self.assertFalse(any("min old" in n for n in older["notes"]))

    def test_unconfirmed_and_priced_in_items_need_no_size(self):
        r = one([{"outcome": "H", "reason": "may rotate", "source": "tweet", "status": "unconfirmed"},
                 {"outcome": "B", "reason": "old news", "source": "club", "market_likely_priced_in": True}])
        self.assertEqual(r["applied"], [])
        self.assertTrue(any("unconfirmed team news, not applied: H (may rotate)" in f for f in r["risk_flags"]))
        self.assertEqual(len(r["rejected"]), 2)

    def test_a_confirmed_news_item_still_needs_a_size(self):
        r = one([{"outcome": "H", "reason": "r", "source": "s"}])
        self.assertIn("delta_pp missing", r["rejected"][0]["why"])

    def test_bad_now_is_an_input_error(self):
        with self.assertRaises(adj.InputError):
            adj.run({"now": "2026-10-10T12:00:00", "matches": [{"slot": 1, "p_fair": P}]})


class NewsOnMatchesWithoutOdds(unittest.TestCase):
    """No bookmaker odds to compare with: the only market-like data is the public split, read at a known time."""

    def run_news(self, news_time, read_at="2026-10-10T16:42:00Z", books=None):
        m = {"slot": 1, "label": "m", "p_fair": P, "q": Q, "public_read_at": read_at,
             "adjustments": [adjustment("H", -3, source_time=news_time), adjustment("B", 3, source_time=news_time)]}
        if books:
            m["books"] = books
        return adj.run({"now": "2026-10-10T17:00:00Z", "matches": [m]})["matches"][0]

    def test_news_before_the_split_was_read_is_flagged_but_still_applied(self):
        r = self.run_news("2026-10-10T15:45:00Z")
        self.assertEqual(len(r["applied"]), 2)
        flags = [f for f in r["risk_flags"] if "may already reflect the news" in f]
        self.assertEqual(len(flags), 1)  # one flag for the news item, not one per leg
        self.assertIn("57 min before the public split was read", flags[0])

    def test_news_after_the_split_was_read_is_not_flagged(self):
        r = self.run_news("2026-10-10T16:50:00Z")
        self.assertEqual([f for f in r["risk_flags"] if "public split" in f], [])

    def test_with_bookmaker_odds_the_odds_times_decide_instead(self):
        books = [{"book": "x", "fetched_at": "2026-10-10T16:30:00Z"}]
        r = self.run_news("2026-10-10T15:45:00Z", books=books)  # 45 min before the odds: priced in
        self.assertEqual(r["applied"], [])
        self.assertEqual([f for f in r["risk_flags"] if "public split" in f], [])

    def test_no_read_time_no_flag(self):
        r = self.run_news("2026-10-10T15:45:00Z", read_at=None)
        self.assertEqual([f for f in r["risk_flags"] if "public split" in f], [])


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
