import contextlib
import copy
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/tippekupong/skills"


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rnd = load("render", "tippekupong-report/scripts/render.py")
opt = load("optimize", "tippekupong-optimizer/scripts/optimize.py")
adj = load("adjust", "tippekupong-news/scripts/adjust.py")
eng = load("engine", "tippekupong-probabilities/scripts/engine.py")

EXAMPLE = json.loads((SKILLS / "tippekupong-report/examples/full-coupon.json").read_text())
# The example has a 1 000 NOK bankroll and tiers of 8 / 12 / 18 NOK (0.8 / 1.2 / 1.8 %), all within the
# default 2 % cap. A 500 NOK bankroll puts only the cheapest tier (1.6 %) within the cap.


def example(**kw):
    data = copy.deepcopy(EXAMPLE)
    data.update(kw)
    return data


class Rendering(unittest.TestCase):
    def test_recommends_largest_tier_within_cap(self):
        out = rnd.build(example())
        self.assertEqual(out["recommended_tier"], "max")
        self.assertIn("## Recommended: max tier", out["markdown"])
        self.assertIn("1.80 % of bankroll", out["markdown"])

    def test_tiers_over_the_cap_are_not_recommended(self):
        out = rnd.build(example(bankroll_nok=500))
        self.assertEqual(out["recommended_tier"], "cheap")
        self.assertTrue(any("'max' tier is above the default 2 % cap" in w for w in out["warnings"]))

    def test_cost_always_shown_as_share_of_bankroll(self):
        md = rnd.build(example(bankroll_nok=500))["markdown"]
        self.assertIn("1.60 % of bankroll", md)  # 8 NOK of 500 NOK

    def test_when_nothing_fits_the_heading_says_not_recommended(self):
        out = rnd.build(example(bankroll_nok=100))
        self.assertEqual(out["recommended_tier"], "cheap")
        self.assertIn("## Cheapest plan: cheap tier (above the default 2 % cap, not recommended)", out["markdown"])
        self.assertNotIn("## Recommended", out["markdown"])
        self.assertTrue(any("NOT recommended" in w for w in out["warnings"]))

    def test_cap_the_user_set_is_called_theirs(self):
        out = rnd.build(example(bankroll_nok=500, cap_pct=1))
        self.assertTrue(any("above your 1 % cap" in w for w in out["warnings"]))

    def test_closing_text_and_core_sections(self):
        md = rnd.build(example())["markdown"]
        for needle in ("Estimated, not certain", "Hjelpelinjen", "## What could be wrong", "## Sources",
                       "Copy into your own coupon", "nothing is placed for you", "independently"):
            self.assertIn(needle, md)

    def test_own_why_text_overrides_auto_text(self):
        self.assertIn("62 % of the public back it", rnd.build(example())["markdown"])

    def test_pipes_in_text_do_not_break_the_table(self):
        self.assertIn("a / b", rnd.build(example(why={"1": "a | b"}))["markdown"])

    def test_every_possible_row_is_flagged(self):
        res = opt.optimize({"row_price_nok": 1, "budget_nok": 9, "risk": "balanced", "matches": [
            {"slot": 1, "label": "a", "p": {"H": .5, "U": .3, "B": .2}},
            {"slot": 2, "label": "b", "p": {"H": .4, "U": .3, "B": .3}}]})
        out = rnd.build({"bankroll_nok": 10000, "optimizer_result": res, "matches": []})
        self.assertTrue(any("every possible row" in w for w in out["warnings"]))


class UnanalysedMatches(unittest.TestCase):
    def test_whole_coupon_range_is_the_bold_headline(self):
        out = rnd.build(example())
        md = out["markdown"]
        self.assertRegex(md, r"\*\*Chance that the whole coupon contains a fully correct row: roughly 1 in \d+ to 1 in \d+\.\*\*")
        self.assertIn("analysed matches alone give", md)
        self.assertNotIn("(analysed matches only): **", md)
        hi, lo = out["chance_range"]
        self.assertAlmostEqual(hi / lo, 0.55 / 0.30, places=6)

    def test_no_range_when_every_match_was_analysed(self):
        out = rnd.build(example(excluded=[]))
        self.assertIsNone(out["chance_range"])
        self.assertNotIn("whole coupon contains", out["markdown"])
        self.assertIn("Estimated chance that the coupon contains a fully correct row", out["markdown"])
        self.assertNotIn("Whole coupon, roughly", out["markdown"])

    def test_tier_table_has_a_whole_coupon_column(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("| Whole coupon, roughly |", md)
        self.assertRegex(md, r"\| 1 in \d+ to \d+ \|")

    def test_cost_of_covering_an_unanalysed_match_is_quantified(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("doubles the cost to 36 NOK (3.60 % of bankroll, above the default 2 % cap)", md)
        self.assertIn("triples it to 54 NOK", md)
        roomy = rnd.build(example(bankroll_nok=10000))["markdown"]
        self.assertIn("doubles the cost to 36 NOK (0.36 % of bankroll)", roomy)

    def grid_lines(self, md):
        block = md.split("```")[1].strip("\n").splitlines()
        return block[0], block[1:]  # header line, one line per match

    def test_grid_has_a_placeholder_in_slot_order(self):
        header, grid = self.grid_lines(rnd.build(example())["markdown"])
        self.assertEqual([int(line.split()[0]) for line in grid], [1, 2, 3, 4, 5, 6, 7])
        self.assertIn("not analysed: mark it yourself", grid[-1])
        self.assertIn("?  ?  ?", grid[-1])

    def test_dropped_quote_reason_reaches_the_report_without_nested_brackets(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("#7 Illustrative M - N: no usable market (Retail book (illustrative) - stale (8.0 h old))", md)


class CouponPageLayout(unittest.TestCase):
    """The report speaks the coupon page's language: H / U / B and boxes, not 1 / X / 2."""

    def md(self):
        return rnd.build(example())["markdown"]

    def grid(self):
        block = self.md().split("```")[1].strip("\n").splitlines()
        return block[0], block[1:]

    def test_no_one_x_two_notation_is_left_in_the_report(self):
        md = self.md()
        self.assertNotIn("1/X/2", md)
        self.assertNotIn("1X2", md)
        header, rows = self.grid()
        self.assertTrue(header.rstrip().endswith("H  U  B"))

    def test_boxes_follow_the_marks(self):
        data = example()
        marks = {m["slot"]: m for m in data["optimizer_result"]["plans"][-1]["marks"]}
        header, rows = self.grid()
        by_slot = {int(r.split()[0]): r for r in rows}
        for slot, m in marks.items():
            expected = "  ".join(rnd.TICK if k in m["outcomes"] else rnd.EMPTY for k in "HUB")
            self.assertTrue(by_slot[slot].rstrip().endswith(expected), (slot, by_slot[slot], expected))

    def test_columns_line_up_with_the_header(self):
        header, rows = self.grid()
        col = header.rindex("H")
        for r in rows:
            if "?" not in r:
                self.assertIn(r[col], (rnd.TICK, rnd.EMPTY), r)

    def test_kickoffs_are_written_as_the_site_writes_them(self):
        header, rows = self.grid()
        self.assertTrue(any("Sø. " in r or "Lø. " in r for r in rows))
        self.assertNotIn("Sun ", self.md())

    def test_check_line_says_what_ditt_system_should_show(self):
        data = example()
        rec = data["optimizer_result"]["plans"][-1]
        self.assertIn(f"\"Ditt system\" on the page should say **{rec['rows']} rekker** ({rec['cost_nok']:g} kr)", self.md())
        self.assertIn("H = hjemmeseier (home win), U = uavgjort (draw), B = borteseier (away win)", self.md())

    def test_table_marks_are_letters(self):
        md = self.md()
        self.assertIn("| p (est) H/U/B | Public H/U/B |", md)
        row = next(line for line in md.splitlines() if line.startswith("| 3 |"))
        self.assertRegex(row, r"\*\*(H|U|B|HU|UB|HB|HUB)\*\*")


class PrefilledLink(unittest.TestCase):
    """The coupon page accepts ?day=N&rows=[UB,H,...] and ticks the boxes (checked on the live page: 96 rekker)."""

    SUNDAY = [["U", "B"], ["H", "U"], ["H"], ["H", "B"], ["H"], ["B"], ["H"], ["H"], ["B"], ["H", "B"], ["H", "U", "B"], ["U", "B"]]

    def marks(self, outcomes=None):
        return [{"slot": i + 1, "outcomes": o} for i, o in enumerate(outcomes or self.SUNDAY)]

    def test_exact_link_matches_the_one_verified_on_the_live_page(self):
        self.assertEqual(
            rnd.prefilled_link("SUNDAY", self.marks(), []),
            "https://www.norsk-tipping.no/sport/tipping/spill?day=2&rows=%5BUB,HU,H,HB,H,B,H,H,B,HB,HUB,UB%5D")

    def test_row_count_in_the_link_is_the_product_the_page_shows(self):
        link = rnd.prefilled_link("SUNDAY", self.marks(), [])
        rows = link.split("%5B")[1].split("%5D")[0].split(",")
        product = 1
        for r in rows:
            product *= len(r)
        self.assertEqual(product, 96)  # "Ditt system 96 rekker" on the live page

    def test_day_numbers_follow_the_site(self):
        self.assertIn("?day=1&", rnd.prefilled_link("SATURDAY", self.marks(), []))
        self.assertIn("?day=3&", rnd.prefilled_link("midweek", self.marks(), []))

    def test_letters_are_always_in_h_u_b_order(self):
        link = rnd.prefilled_link("SUNDAY", self.marks([["B", "U", "H"], ["B", "H"], ["U", "B"]]), [])
        self.assertTrue(link.endswith("%5BHUB,HB,UB%5D"))

    def test_no_link_when_it_cannot_be_complete(self):
        self.assertIsNone(rnd.prefilled_link("SUNDAY", self.marks(), [{"slot": 13}]))           # a match was not analysed
        self.assertIsNone(rnd.prefilled_link("SUNDAY", self.marks()[1:], []))                   # slots do not start at 1
        self.assertIsNone(rnd.prefilled_link("FRIDAY", self.marks(), []))                       # unknown round

    def test_report_puts_the_link_after_the_grid_and_falls_back_when_incomplete(self):
        data = example(coupon={"name": "x", "day": "SUNDAY", "deadline": "2026-10-11T14:25:00+02:00",
                               "url": "https://example.invalid/page"}, excluded=[])
        data["optimizer_result"]["plans"][-1]["marks"] = [m for m in data["optimizer_result"]["plans"][-1]["marks"]]
        md = rnd.build(data)["markdown"]
        self.assertRegex(md, r"\*\*Pre-filled coupon:\*\* https://www\.norsk-tipping\.no/sport/tipping/spill\?day=2&rows=%5B[HUB,]+%5D")
        self.assertIn("then buy it yourself", md)
        self.assertNotIn("https://example.invalid/page", md)
        incomplete = rnd.build(example(coupon={"day": "SUNDAY", "url": "https://example.invalid/page"}))["markdown"]  # has an unanalysed match
        self.assertNotIn("Pre-filled coupon", incomplete)
        self.assertIn("Public coupon page: https://example.invalid/page", incomplete)


class NewsAndRisk(unittest.TestCase):
    def test_applied_news_gets_its_own_section_with_source_and_time(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("## News used", md)
        self.assertIn("#3 Illustrative E - F: B -2 pp, H +2 pp: Away top scorer ruled out, announced 11:50; Same news, mirrored", md)
        self.assertEqual(md.count("club site (illustrative), 2026-10-10 13:50"), 1)  # mirrored legs share one line
        self.assertIn("club site (illustrative), 2026-10-10 13:50 Oslo (11:50 UTC)", md)

    def test_no_news_section_when_nothing_was_applied(self):
        data = example()
        for m in data["matches"]:
            m["applied"] = []
        self.assertNotIn("## News used", rnd.build(data)["markdown"])

    def test_priced_in_and_unconfirmed_news_are_surfaced_once_each(self):
        md = rnd.build(example())["markdown"]
        self.assertEqual(md.count("unconfirmed team news, not applied"), 1)  # mirrored pair merged
        self.assertIn("H -3 pp, B +3 pp", md)
        self.assertIn("#4: news adjustment not applied (announced 75 min before the earliest odds were taken", md)

    def test_risk_column_shows_notes_and_is_blank_only_for_clean_matches(self):
        md = rnd.build(example())["markdown"]
        row3 = next(line for line in md.splitlines() if line.startswith("| 3 |"))
        self.assertIn("news applied: B -2 pp, H +2 pp", row3)
        self.assertIn("only 10 min old", row3)
        row4 = next(line for line in md.splitlines() if line.startswith("| 4 |"))
        self.assertTrue(row4.rstrip().endswith("| – |"))

    def test_rescaled_public_split_is_disclosed(self):
        data = example()
        data["matches"][0]["split_note"] = "given as percentages adding to 101 %; divided by the total"
        md = rnd.build(data)["markdown"]
        self.assertIn("Public split rescaled to add to 100 %: #1 (given as percentages adding to 101 %", md)

    def test_value_index_is_explained_in_plain_words_first(self):
        md = rnd.build(example())["markdown"]
        self.assertIn("as crowded as their probability suggests", md)
        self.assertIn("leans toward hit chance rather than payout", md)
        self.assertIn("1.0 is a row picked the way the public picks", md)


class TimesAndSources(unittest.TestCase):
    def test_deadline_in_oslo_time_with_time_left(self):
        if rnd.OSLO is None:
            self.skipTest("no tz database")
        md = rnd.build(example())["markdown"]
        self.assertIn("Deadline 2026-10-10 17:00 Oslo (15:00 UTC), 3 h 0 min left", md)

    def test_deadline_alias(self):
        a = rnd.build(example(coupon={"deadline": "2026-10-10T17:00:00+02:00"}))["markdown"]
        b = rnd.build(example(coupon={"deadline_utc": "2026-10-10T15:00:00Z"}))["markdown"]
        self.assertEqual(a.split("\n")[2], b.split("\n")[2])

    def test_source_times_are_shown_in_oslo_time_too(self):
        if rnd.OSLO is None:
            self.skipTest("no tz database")
        md = rnd.build(example())["markdown"]
        self.assertIn("Sharp book odds (illustrative), 2026-10-10 13:40 Oslo (11:40 UTC)", md)

    def test_time_without_a_zone_is_rejected_not_guessed(self):
        with self.assertRaises(rnd.InputError):
            rnd.build(example(coupon={"deadline": "2026-10-10T17:00:00"}))
        with self.assertRaises(rnd.InputError):
            rnd.build(example(now="2026-10-10T12:00:00"))
        out = rnd.build(example(sources=[{"name": "x", "fetched_at": "2026-10-10T11:00:00"}]))
        self.assertTrue(any("no time zone" in w for w in out["warnings"]))

    def test_undated_source_is_a_caveat_not_a_top_warning(self):
        out = rnd.build(example(sources=[{"name": "list", "static": True}, {"name": "rumour tweet"}]))
        self.assertFalse(any("rumour tweet" in w for w in out["warnings"]))
        self.assertFalse(any("'list'" in w for w in out["markdown"].splitlines() if w.startswith(">")))
        self.assertIn("Source 'rumour tweet' has no timestamp", out["markdown"])
        self.assertIn("time not relevant", out["markdown"])

    def test_stale_source_and_deadline_warnings(self):
        data = example(now="2026-10-10T14:30:00Z", max_source_age_hours=2)
        warnings = rnd.build(data)["warnings"]
        self.assertTrue(any("h old" in w for w in warnings))
        self.assertTrue(any("Less than an hour" in w for w in warnings))
        warnings = rnd.build(example(now="2026-10-10T16:00:00Z"))["warnings"]
        self.assertTrue(any("deadline has passed" in w for w in warnings))


class BudgetAndCap(unittest.TestCase):
    def capped_result(self, **kw):
        data = {"row_price_nok": 2, "budget_nok": 100, "bankroll_nok": 2500, "risk": "balanced",
                "max_budget_nok": 150, "matches": [
                    {"slot": i, "label": f"m{i}", "p": {"H": .45, "U": .30, "B": .25}} for i in range(1, 9)]}
        data.update(kw)
        return opt.optimize(data)

    def test_over_cap_request_is_cut_to_the_cap_and_explained(self):
        res = self.capped_result()
        out = rnd.build({"bankroll_nok": 2500, "optimizer_result": res, "matches": []})
        self.assertEqual(out["recommended_tier"], "base")
        self.assertTrue(any("You asked for 100 NOK (4.0% of your bankroll)" in w and "built at the cap (50 NOK)" in w
                            for w in out["warnings"]))
        self.assertEqual(sum("100 NOK" in w for w in out["warnings"]), 1)  # the optimizer's twin warning is not repeated
        for plan in res["plans"]:
            self.assertLessEqual(plan["cost_nok"], 50 + 1e-9)

    def test_unused_budget_is_explained(self):
        data = example()
        data["optimizer_result"]["plans"][-1]["tier_budget_nok"] = 20
        data["optimizer_result"]["plans"][-1]["cost_nok"] = 18
        self.assertIn("Uses 18 of the 20 NOK for this tier", rnd.build(data)["markdown"])

    def test_optimizer_split_warnings_are_not_repeated_at_the_top(self):
        data = example()
        data["optimizer_result"]["warnings"] = ["match 2 (x): no public split; crowding unknown",
                                                "match 3 (y): public split is an estimate, not observed",
                                                "tier 'max' identical to a cheaper tier; omitted"]
        out = rnd.build(data)
        self.assertEqual([w for w in out["warnings"] if "public split" in w], [])
        self.assertTrue(any("identical to a cheaper tier" in w for w in out["warnings"]))

    def test_standard_line_does_not_nudge_towards_more_rows(self):
        md = rnd.build(example())["markdown"]
        self.assertNotIn("diminishing returns", md)
        self.assertIn("do not turn a pool coupon into a profitable one", md)


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

    def test_malformed_input_gives_a_readable_error(self):
        bad = example()
        bad["optimizer_result"] = bad["optimizer_result"]["plans"]  # list instead of object
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(bad, f)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = rnd.main(["render.py", f.name])
        self.assertEqual(code, 1)
        self.assertIn("wrong shape", err.getvalue())
        Path(f.name).unlink()


class ReportWording(unittest.TestCase):
    def match(self, p, q=None):
        d = {"p_est": dict(zip("HUB", p))}
        if q:
            d["q"] = dict(zip("HUB", q))
            d["value_ratio"] = {k: d["p_est"][k] / d["q"][k] for k in "HUB"}
        return d

    def test_auto_reason_says_something_only_when_there_is_something_to_say(self):
        why = rnd._auto_why
        self.assertEqual(why({"outcomes": ["H"]}, self.match((.6, .25, .15), (.6, .25, .15))), "likeliest outcome (60%)")
        self.assertIn("flat match, no outcome above 38%", why({"outcomes": ["H", "U", "B"]}, self.match((.38, .31, .31))))
        self.assertEqual(why({"outcomes": ["U", "H"]}, self.match((.40, .33, .27))), "the two likeliest outcomes")
        self.assertIn("includes B (27%) because fewer tippers back it", why({"outcomes": ["H", "B"]}, self.match((.40, .33, .27))))
        self.assertIn("not the likeliest (30% against 50% for H)", why({"outcomes": ["B"]}, self.match((.5, .2, .3))))
        self.assertNotIn("in line", why({"outcomes": ["H"]}, self.match((.5, .3, .2), (.5, .3, .2))))

    def test_auto_reason_flags_clearly_under_and_over_backed_outcomes_only(self):
        text = rnd._auto_why({"outcomes": ["H", "B"]}, self.match((.4, .3, .3), (.30, .30, .40)))
        self.assertIn("H is under-backed (public 30%)", text)
        self.assertIn("B is over-backed (public 40%)", text)
        mild = rnd._auto_why({"outcomes": ["H"]}, self.match((.4, .3, .3), (.36, .32, .32)))
        self.assertNotIn("backed", mild)

    def test_risk_column_is_short_and_marks_low_confidence_once(self):
        m = {"confidence": "low", "confidence_reasons": ["no bookmaker odds (expert tips and public split only)"],
             "notes": ["news applied: H -3 pp, B +3 pp"]}
        self.assertEqual(rnd._risk_text(m), "no bookmaker odds; news applied: H -3 pp, B +3 pp (low confidence)")
        self.assertEqual(rnd._risk_text({"confidence": "high", "confidence_reasons": [], "notes": []}), "–")
        self.assertEqual(rnd._risk_text({"confidence": "medium", "confidence_reasons": ["one bookmaker only"]}), "one bookmaker only")
        self.assertNotIn("confidence medium", rnd._risk_text({"confidence": "medium", "confidence_reasons": ["no public split"]}))

    def plan(self, epn, se_nok=0.2, cost=48, rows_pub=48):
        return {"tier": "base", "strategy": "balanced", "rows": cost, "cost_nok": cost, "tier_budget_nok": cost,
                "marks": [], "p_all_correct": 0.004, "one_in": 250, "p_any_prize": 0.14,
                "expected_payout_nok": epn * cost, "expected_payout_per_nok": epn, "expected_payout_se_nok": se_nok,
                "baselines": {"follow_the_public": {"rows": rows_pub, "expected_payout_per_nok": 0.35, "marks": []},
                              "maximise_chance_of_all_correct": {"rows": 54, "expected_payout_per_nok": 0.44, "marks": []}}}

    def test_edge_wording_follows_the_numbers(self):
        for epn, needle in ((0.52, "a small edge"), (0.47, "about the same as an average ticket"), (0.45, "about the same as an average ticket"),
                            (0.497, "about the same as an average ticket"), (0.41, "below an average ticket")):
            text = " ".join(rnd._payout_lines(self.plan(epn), "", 48))
            self.assertIn(needle, text, epn)
        self.assertIn("differences under about 0.02 per NOK are noise", text)

    def test_baselines_are_quoted_with_their_own_row_counts(self):
        text = " ".join(rnd._payout_lines(self.plan(0.47, rows_pub=36), "", 48))
        self.assertIn("following the public with 36 rows", text)
        self.assertIn("best chance of all 12 (54 rows)", text)
        self.assertNotIn("same budget", text)

    def test_round_name_is_readable(self):
        c = {"day": "SUNDAY", "game_id": 69453, "deadline": "2026-10-11T14:25:00+02:00"}
        self.assertEqual(rnd._round_name(c), "Tipping, Sunday 11 October (round #69453)")
        self.assertEqual(rnd._round_name({"day": "MIDWEEK", "game_id": 1}), "Tipping midweek (round #1)")


class EndToEnd(unittest.TestCase):
    """Odds -> probabilities -> adjustments -> covers -> report, all on pasted data."""

    def test_pipeline_with_cap_news_timing_and_a_missing_market(self):
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
        matches.append({"slot": 5, "label": "Match 5", "quotes": []})
        e = eng.run({"now": now, "matches": matches})
        splits = {1: (.60, .22, .18), 2: (.38, .28, .34), 3: (.30, .22, .48), 4: (.70, .18, .12)}
        vm_in = []
        for m in e["matches"]:
            d = dict(m)
            if m["slot"] in splits:
                d["q"] = dict(zip("HUB", splits[m["slot"]]))
            d["adjustments"] = []
            if m["slot"] == 2:  # announced 11:45, after the 11:30 quotes: applied
                d["adjustments"] = [
                    {"outcome": "H", "delta_pp": -2, "reason": "keeper out", "source": "club",
                     "source_time": "2026-10-10T11:45:00Z"},
                    {"outcome": "B", "delta_pp": 2, "reason": "mirror", "source": "club",
                     "source_time": "2026-10-10T11:45:00Z"}]
            if m["slot"] == 3:  # announced 10:00, long before the quotes: priced in
                d["adjustments"] = [{"outcome": "H", "delta_pp": -2, "reason": "old news", "source": "club",
                                     "source_time": "2026-10-10T10:00:00Z"}]
            vm_in.append(d)
        vm = adj.run({"now": now, "matches": vm_in})
        by_slot = {m["slot"]: m for m in vm["matches"] if m["status"] == "ok"}
        self.assertEqual(len(by_slot[2]["applied"]), 2)
        self.assertEqual(by_slot[3]["applied"], [])
        res = opt.optimize({"row_price_nok": 2, "budget_nok": 300, "bankroll_nok": 1000, "risk": "balanced",
                            "matches": vm["optimizer_matches"]})
        self.assertTrue(res["budget_capped"])  # 300 NOK is 30 % of 1000 NOK
        out = rnd.build({"bankroll_nok": 1000, "now": now, "optimizer_result": res,
                         "matches": vm["matches"], "excluded": vm["excluded"],
                         "sources": [{"name": "pasted odds", "fetched_at": "2026-10-10T11:30:00Z"}]})
        md = out["markdown"]
        self.assertEqual(out["recommended_tier"], "base")
        self.assertIn("You asked for 300 NOK", md)
        self.assertIn("## News used", md)
        self.assertIn("#5 Match 5", md)
        self.assertEqual(md.count("| **"), 4)  # one table row per analysed match


if __name__ == "__main__":
    unittest.main()
