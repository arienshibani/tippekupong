import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/tippekupong/skills"
SNAPSHOT = ROOT / "tests/fixtures/nt_live_info_2026-10-10.json"
HISTORY = json.loads((ROOT / "tests/fixtures/nt_history_60_rounds.json").read_text())["games"]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, SKILLS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fc = load("fetch_coupon", "tippekupong-fixtures/scripts/fetch_coupon.py")
fo = load("fetch_odds", "tippekupong-odds/scripts/fetch_odds.py")
bl = load("blend", "tippekupong-probabilities/scripts/blend.py")
RAW = json.loads(SNAPSHOT.read_text())
NOW = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)


class FetchCoupon(unittest.TestCase):
    def test_snapshot_parses_into_three_coupons(self):
        coupons = fc.parse_live_info(RAW)
        self.assertEqual([c["day"] for c in coupons], ["SUNDAY", "MIDWEEK", "SATURDAY"])
        sunday = coupons[0]
        self.assertEqual(len(sunday["matches"]), 12)
        self.assertEqual(sunday["row_price_nok"], 1.0)
        self.assertEqual(sunday["deadline"], "2026-10-11T14:25:00+02:00")
        self.assertEqual(sunday["turnover_nok"], 704593.0)
        first = sunday["matches"][0]
        self.assertEqual((first["slot"], first["home"], first["away"], first["league"]),
                         (1, "Lillestrøm", "Molde", "NOR Eliteserien"))
        for m in sunday["matches"]:
            for key in ("public", "expert"):
                self.assertAlmostEqual(sum(m[key].values()), 1.0, places=9)
        self.assertAlmostEqual(first["public"]["H"], 0.39)
        self.assertAlmostEqual(first["expert"]["B"], 0.40)

    def test_selection(self):
        coupons = fc.parse_live_info(RAW)
        self.assertEqual(fc.select(coupons, "next", NOW)[0]["day"], "SUNDAY")
        self.assertEqual(fc.select(coupons, "midtuke", NOW)[0]["day"], "MIDWEEK")
        self.assertEqual(fc.select(coupons, "Saturday", NOW)[0]["day"], "SATURDAY")
        self.assertEqual(len(fc.select(coupons, "all", NOW)), 3)
        with self.assertRaises(fc.FetchError):
            fc.select(coupons, "friday", NOW)

    def test_warnings_for_a_closed_or_started_coupon(self):
        result = fc.build(RAW, "2026-10-10T16:00:00+00:00", "sunday", estimate_turnover=False, now=datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(result["warnings"], [])
        closed = fc.build(RAW, "x", "sunday", estimate_turnover=False, now=datetime(2026, 10, 11, 13, 0, tzinfo=timezone.utc))  # deadline is 12:25 UTC
        self.assertTrue(any("deadline" in w and "passed" in w for w in closed["warnings"]))
        started = json.loads(json.dumps(RAW))
        started["gameDays"][0]["game"]["matches"][3]["status"]["value"] = "STARTED"
        warned = fc.build(started, "x", "sunday", estimate_turnover=False, now=datetime(2026, 10, 11, 10, 0, tzinfo=timezone.utc))
        self.assertTrue(any("have started" in w for w in warned["warnings"]))

    def test_turnover_estimate_uses_last_comparable_round(self):
        sunday_before = next(g for g in HISTORY if g["sale_stop"].startswith("2026-10-04"))
        fake = lambda url, cache: ({"sales": {"fullTime": {"saleStopDate": sunday_before["sale_stop"],
                                                            "saleAmount": {"amount": str(sunday_before["turnover_nok"])}}}}, False)
        result = fc.build(RAW, "x", "sunday", fetch=fake, now=NOW)
        c = result["coupons"][0]
        self.assertEqual(c["turnover_estimate_nok"], sunday_before["turnover_nok"])
        self.assertIn("last week", c["turnover_estimate_basis"])

    def test_turnover_estimate_ignores_a_different_weekday_or_a_failure(self):
        saturday = next(g for g in HISTORY if g["sale_stop"].startswith("2026-10-03"))
        wrong_day = lambda url, cache: ({"sales": {"fullTime": {"saleStopDate": saturday["sale_stop"],
                                                                 "saleAmount": {"amount": "9999999"}}}}, False)
        c = fc.build(RAW, "x", "sunday", fetch=wrong_day, now=NOW)["coupons"][0]
        self.assertEqual(c["turnover_estimate_nok"], c["turnover_nok"])
        def broken(url, cache):
            raise fc.FetchError("down")
        c = fc.build(RAW, "x", "sunday", fetch=broken, now=NOW)["coupons"][0]
        self.assertEqual(c["turnover_estimate_nok"], c["turnover_nok"])

    def test_estimate_never_lowers_the_turnover(self):
        small = lambda url, cache: ({"sales": {"fullTime": {"saleStopDate": "2026-10-04T14:25:00+02:00",
                                                             "saleAmount": {"amount": "1000"}}}}, False)
        c = fc.build(RAW, "x", "sunday", fetch=small, now=NOW)["coupons"][0]
        self.assertEqual(c["turnover_estimate_nok"], c["turnover_nok"])

    def test_shape_changes_fail_loudly(self):
        with self.assertRaises(fc.FetchError):
            fc.parse_live_info({"nothing": []})
        broken = json.loads(json.dumps(RAW))
        del broken["gameDays"][0]["game"]["sales"]
        with self.assertRaises(fc.FetchError):
            fc.parse_live_info(broken)

    def test_cli_with_a_saved_file_and_the_failure_message(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fc.main(["fetch_coupon.py", "--file", str(SNAPSHOT), "--day", "sunday", "--text"])
        self.assertEqual(code, 0)
        self.assertIn("Lillestrøm - Molde", out.getvalue())
        with contextlib.redirect_stderr(err):
            code = fc.main(["fetch_coupon.py", "--file", "/nonexistent/file.json"])
        self.assertEqual(code, 1)
        self.assertIn("paste the coupon", err.getvalue())

    def test_the_script_never_asks_for_credentials(self):
        text = (SKILLS / "tippekupong-fixtures/scripts/fetch_coupon.py").read_text().lower()
        for word in ("password", "bankid", "cookie", "authorization", "bearer", "token", "post("):
            self.assertNotIn(word, text, word)
        self.assertIn('headers={"User-Agent": USER_AGENT, "Accept": "application/json"}',
                      (SKILLS / "tippekupong-fixtures/scripts/fetch_coupon.py").read_text())  # the only headers it sends


CSV = """Div,Date,Time,HomeTeam,AwayTeam,B365H,B365D,B365A,PPH,PPD,PPA,BFEH,BFED,BFEA
E0,11/10/2026,17:30,Liverpool,Man City,2.7,3.6,2.45,2.63,3.6,2.4,2.62,3.7,2.5
E0,11/10/2026,14:00,Crystal Palace,Nott'm Forest,2.7,3.2,2.7,2.63,3.25,2.63,,,
E0,25/10/2026,14:00,Hull,Everton,3.7,3.4,2.05,3.6,3.3,2.05,3.5,3.4,2.1
E1,11/10/2026,15:00,Hull,Wrexham,2.0,3.3,3.6,,,,,,
"""
COUPON = {"coupons": [{"day": "SUNDAY", "matches": [
    {"slot": 10, "label": "Liverpool - Manchester City", "home": "Liverpool", "away": "Manchester City",
     "league": "ENG Premier League", "kickoff": "2026-10-11T17:30:00+02:00"},
    {"slot": 11, "label": "Crystal Palace - Nottingham F", "home": "Crystal Palace", "away": "Nottingham F",
     "league": "ENG Premier League", "kickoff": "2026-10-11T15:00:00+02:00"},
    {"slot": 12, "label": "Hull - Everton", "home": "Hull", "away": "Everton",
     "league": "ENG Premier League", "kickoff": "2026-10-11T15:00:00+02:00"},
    {"slot": 1, "label": "Lillestrøm - Molde", "home": "Lillestrøm", "away": "Molde",
     "league": "NOR Eliteserien", "kickoff": "2026-10-11T19:15:00+02:00"},
    {"slot": 7, "label": "Hull - Wrexham AFC", "home": "Hull", "away": "Wrexham AFC",
     "league": "ENG Championship", "kickoff": "2026-10-11T16:00:00+02:00"}]}]}
FILE_TIME = datetime(2026, 10, 9, 9, 20, tzinfo=timezone.utc)


class FetchOdds(unittest.TestCase):
    def result(self):
        return fo.build(COUPON, CSV, FILE_TIME, "2026-10-10T16:30:00+00:00")

    def test_names_are_normalised_across_the_two_spellings(self):
        self.assertEqual(fo.norm("Manchester City"), fo.norm("Man City"))
        self.assertEqual(fo.norm("Nottingham F"), fo.norm("Nott'm Forest"))
        self.assertEqual(fo.norm("Wrexham AFC"), fo.norm("Wrexham"))
        self.assertEqual(fo.norm("Bodø/Glimt"), "bodo glimt")
        self.assertNotEqual(fo.norm("Manchester United"), fo.norm("Manchester City"))

    def test_matches_are_found_with_complete_odds_only(self):
        r = self.result()
        by_slot = {m["slot"]: m for m in r["matches"]}
        self.assertEqual(set(by_slot), {10, 11, 7})
        self.assertEqual({q["book"] for q in by_slot[10]["quotes"]}, {"Bet365", "Paddy Power", "Betfair Exchange"})
        self.assertEqual({q["book"] for q in by_slot[11]["quotes"]}, {"Bet365", "Paddy Power"})  # exchange cells empty
        liverpool = next(q for q in by_slot[10]["quotes"] if q["book"] == "Bet365")
        self.assertEqual(liverpool["odds"], {"H": 2.7, "U": 3.6, "B": 2.45})

    def test_pp_is_paddy_power_not_pinnacle(self):
        names = {q["book"] for m in self.result()["matches"] for q in m["quotes"]}
        self.assertIn("Paddy Power", names)
        self.assertNotIn("Pinnacle", names)

    def test_fixture_on_another_date_is_not_matched(self):
        r = self.result()
        unmatched = {u["slot"]: u for u in r["unmatched"]}
        self.assertIn(12, unmatched)  # the Hull - Everton row in the file is 25/10, two weeks later
        self.assertIn(1, unmatched)
        self.assertIn("not in football-data", unmatched[1]["reason"])

    def test_quotes_carry_the_file_time_and_the_age_is_reported(self):
        r = self.result()
        self.assertTrue(all(q["fetched_at"] == "2026-10-09T09:20:00+00:00" for m in r["matches"] for q in m["quotes"]))
        self.assertAlmostEqual(r["source"]["odds_age_hours"], 31.2, delta=0.1)
        self.assertTrue(any("31.2 h old" in n for n in r["notes"]))

    def test_output_feeds_the_engine(self):
        engine = load("engine", "tippekupong-probabilities/scripts/engine.py")
        out = engine.run(dict(self.result(), now="2026-10-10T16:30:00Z"))
        self.assertEqual({m["slot"] for m in out["matches"] if m["status"] == "ok"}, {10, 11, 7})
        self.assertEqual(out["source"]["odds_age_hours"], self.result()["source"]["odds_age_hours"])

    def test_offline_cli(self):
        with tempfile.TemporaryDirectory() as d:
            coupon, fixtures = Path(d) / "coupon.json", Path(d) / "fixtures.csv"
            coupon.write_text(json.dumps(COUPON)); fixtures.write_text(CSV)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = fo.main(["fetch_odds.py", "--coupon", str(coupon), "--fixtures-file", str(fixtures), "--text"])
            self.assertEqual(code, 0)
            self.assertIn("Liverpool - Manchester City", out.getvalue())


def coupon_match(slot=1, public=(0.4, 0.3, 0.3), expert=(0.5, 0.25, 0.25)):
    return {"slot": slot, "label": f"m{slot}", "league": "x",
            "public": dict(zip("HUB", public)) if public else None, "expert": dict(zip("HUB", expert)) if expert else None}


def engine_match(p, books=3, confidence="ok"):
    return {"slot": 1, "p_fair": dict(zip("HUB", p)), "n_books": books, "confidence": confidence}


class Blend(unittest.TestCase):
    def test_crowd_only_is_an_even_mix_and_low_confidence(self):
        m = bl.blend_match(coupon_match(), None, None)
        self.assertEqual(m["weights"], {"expert": 0.5, "public": 0.5})
        self.assertAlmostEqual(m["p_fair"]["H"], 0.45)
        self.assertEqual(m["confidence"], "low")
        self.assertIn("no bookmaker odds", m["confidence_reasons"][0])
        self.assertAlmostEqual(sum(m["p_fair"].values()), 1.0, places=5)

    def test_several_books_get_the_biggest_weight(self):
        m = bl.blend_match(coupon_match(), engine_match((0.6, 0.2, 0.2)), 5.0)
        self.assertEqual(m["weights"], {"market": 0.55, "expert": 0.25, "public": 0.2})
        self.assertEqual(m["confidence"], "ok")
        self.assertAlmostEqual(m["p_fair"]["H"], 0.55 * 0.6 + 0.25 * 0.5 + 0.2 * 0.4)

    def test_old_odds_lose_a_quarter_of_their_weight_without_lowering_confidence(self):
        m = bl.blend_match(coupon_match(), engine_match((0.6, 0.2, 0.2)), 31.0)
        self.assertAlmostEqual(m["weights"]["market"], 0.55 * 0.75 / (0.55 * 0.75 + 0.45), places=3)
        self.assertEqual(m["confidence"], "ok")
        self.assertTrue(any("31 h old" in n for n in m["notes"]))

    def test_a_single_bookmaker_is_trusted_less(self):
        m = bl.blend_match(coupon_match(), engine_match((0.6, 0.2, 0.2), books=1), 2.0)
        self.assertEqual(m["weights"], {"market": 0.4, "expert": 0.3, "public": 0.3})
        self.assertEqual(m["confidence"], "low")
        self.assertIn("only one bookmaker priced this match", m["confidence_reasons"])

    def test_missing_ingredients_renormalise_or_skip(self):
        m = bl.blend_match(coupon_match(public=None), None, None)
        self.assertEqual(m["weights"], {"expert": 1.0})
        self.assertIsNone(m["q"])
        self.assertIsNone(bl.blend_match(coupon_match(public=None, expert=None), None, None))

    def test_probabilities_always_sum_to_one(self):
        for public, expert, market in (((0.4, 0.3, 0.3), (0.5, 0.25, 0.25), (0.6, 0.2, 0.2)),
                                       ((0.1, 0.1, 0.8), (0.34, 0.33, 0.33), None)):
            m = bl.blend_match(coupon_match(public=public, expert=expert), engine_match(market) if market else None, 3.0)
            self.assertAlmostEqual(sum(m["p_fair"].values()), 1.0, places=5)

    def test_build_picks_the_requested_day(self):
        coupon = {"coupons": [{"day": "SUNDAY", "matches": [coupon_match(1)]}, {"day": "MIDWEEK", "matches": [coupon_match(2)]}]}
        self.assertEqual(bl.build(coupon, {}, "midweek")["matches"][0]["slot"], 2)
        self.assertEqual(bl.build(coupon, {}, None)["matches"][0]["slot"], 1)


class WholeChainThroughFiles(unittest.TestCase):
    """Run every stage as a command, passing only files, on saved data: this is the contract between the skills."""

    def run_script(self, rel, *args, cwd):
        r = subprocess.run([sys.executable, "-I", str(SKILLS / rel), *args], capture_output=True, text=True, cwd=cwd, timeout=240)
        self.assertEqual(r.returncode, 0, f"{rel} {args}\n{r.stderr}")
        return r.stdout

    def test_chain(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "fixtures.csv").write_text(CSV)
            self.run_script("tippekupong-fixtures/scripts/fetch_coupon.py", "--file", str(SNAPSHOT), "--day", "sunday",
                            "--out", "coupon.json", cwd=d)
            # the saved CSV has fixtures for three of the coupon's matches
            self.run_script("tippekupong-odds/scripts/fetch_odds.py", "--coupon", "coupon.json",
                            "--fixtures-file", "fixtures.csv", "--out", "odds.json", cwd=d)
            engine = self.run_script("tippekupong-probabilities/scripts/engine.py", "odds.json", cwd=d)
            (d / "engine.json").write_text(engine)
            self.run_script("tippekupong-probabilities/scripts/blend.py", "--coupon", "coupon.json",
                            "--engine", "engine.json", "--out", "blend.json", cwd=d)
            (d / "news.json").write_text(json.dumps({"4": [
                {"outcome": "H", "delta_pp": -3, "reason": "striker out", "source": "club", "source_time": "2026-10-10T17:00:00+02:00"},
                {"outcome": "B", "delta_pp": 3, "reason": "mirror", "source": "club", "source_time": "2026-10-10T17:00:00+02:00"}]}))
            value = self.run_script("tippekupong-news/scripts/adjust.py", "blend.json", "--news", "news.json", cwd=d)
            (d / "value.json").write_text(value)
            self.run_script("tippekupong-optimizer/scripts/build.py", "--value", "value.json", "--coupon", "coupon.json",
                            "--budget", "100", "--bankroll", "2500", "--samples", "500", "--final-samples", "4000",
                            "--out", "build.json", cwd=d)
            report = self.run_script("tippekupong-report/scripts/render.py", "--build", "build.json", "--value", "value.json",
                                     "--coupon", "coupon.json", "--odds", "odds.json", "--bankroll", "2500",
                                     "--now", "2026-10-10T16:30:00Z", "--note", "test run", cwd=d)
            built = json.loads((d / "build.json").read_text())
            self.assertTrue(built["budget_capped"])
            for plan in built["plans"]:
                self.assertLessEqual(plan["cost_nok"], 50 + 1e-9)
                self.assertEqual(len(plan["marks"]), 12)
            self.assertIn("Chance of winning a prize", report)
            self.assertIn("News used", report)
            self.assertIn("You asked for 100 NOK", report)
            self.assertIn("Bookmaker odds (football-data.co.uk)", report)
            self.assertEqual(report.count("| **"), 13)  # 12 matches plus the chosen strategy in the comparison table
            self.assertIn("Hjelpelinjen", report)
            self.assertIn("# Tipping recommendation" if False else "# Tipping coupon recommendation: Tipping, Sunday 11 October (round #", report)
            self.assertIn("| Kick-off |", report)
            self.assertIn("Sø. 14:30", report)           # Fredrikstad - Tromsø, 14:30 Oslo time
            self.assertNotIn("1/X/2", report)
            self.assertIn("rekker**", report)             # the "Ditt system" check line
            self.assertNotIn("in line", report)
            self.assertNotIn("confidence medium", report)
            self.assertEqual(report.count("no bookmaker odds (expert tips"), 0)  # shortened in the table
            self.assertIn("Strategy: balanced", report)
            self.assertRegex(report, r"following the public with \d+ rows")
            self.assertIn("may already reflect the news", report)  # news on a match without odds, public split read after it


if __name__ == "__main__":
    unittest.main()
