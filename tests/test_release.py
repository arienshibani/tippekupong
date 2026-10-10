import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release", ROOT / "scripts/release.py")
rel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rel)

CHANGELOG = """# Changelog

Intro text.

## Unreleased

### Added

- A new thing

## 1.2.3 - 2026-01-01

### Fixed

- An old thing

## 1.2.0 - 2025-12-01

Older.
"""


class RepoIsReleasable(unittest.TestCase):
    def test_versions_agree_and_the_changelog_has_a_section(self):
        self.assertEqual(rel.check(), [], rel.check())

    def test_current_version_is_semver_and_notes_exist(self):
        version = rel.read_versions()[0]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertTrue(rel.section((ROOT / "CHANGELOG.md").read_text(), version))


class Helpers(unittest.TestCase):
    def test_section_extracts_one_version(self):
        self.assertEqual(rel.section(CHANGELOG, "1.2.3"), "### Fixed\n\n- An old thing")
        self.assertEqual(rel.section(CHANGELOG, "1.2.0"), "Older.")
        self.assertIsNone(rel.section(CHANGELOG, "9.9.9"))
        self.assertIn("A new thing", rel.section(CHANGELOG, "Unreleased"))

    def test_section_does_not_confuse_prefixes(self):
        self.assertIsNone(rel.section("## 1.2.30 - x\n\nbody\n", "1.2.3"))

    def test_next_version(self):
        self.assertEqual(rel.next_version("1.2.3", "patch"), "1.2.4")
        self.assertEqual(rel.next_version("1.2.3", "minor"), "1.3.0")
        self.assertEqual(rel.next_version("1.2.3", "major"), "2.0.0")
        self.assertEqual(rel.next_version("1.2.3", "2.5.0"), "2.5.0")
        with self.assertRaises(rel.ReleaseError):
            rel.next_version("1.2.3", "huge")


class Bump(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (rel.PLUGIN, rel.MARKET, rel.CHANGELOG)
        rel.PLUGIN, rel.MARKET, rel.CHANGELOG = self.tmp / "plugin.json", self.tmp / "market.json", self.tmp / "CHANGELOG.md"
        rel.PLUGIN.write_text(json.dumps({"name": "x", "version": "1.2.3"}))
        rel.MARKET.write_text(json.dumps({"name": "m", "plugins": [{"name": "x", "version": "1.2.3"}]}))
        rel.CHANGELOG.write_text(CHANGELOG)

    def tearDown(self):
        rel.PLUGIN, rel.MARKET, rel.CHANGELOG = self.saved
        shutil.rmtree(self.tmp)

    def test_bump_moves_unreleased_into_a_dated_section_and_updates_both_manifests(self):
        old, new = rel.bump("minor", today=date(2026, 3, 4))
        self.assertEqual((old, new), ("1.2.3", "1.3.0"))
        text = rel.CHANGELOG.read_text()
        self.assertIn("## Unreleased\n\n## 1.3.0 - 2026-03-04\n\n### Added\n\n- A new thing", text)
        self.assertEqual(rel.section(text, "Unreleased"), "")
        self.assertEqual(rel.read_versions(), ("1.3.0", "1.3.0"))
        self.assertEqual(rel.check(), [])

    def test_bump_refuses_when_nothing_is_written_down(self):
        rel.CHANGELOG.write_text(CHANGELOG.replace("### Added\n\n- A new thing\n", ""))
        with self.assertRaises(rel.ReleaseError):
            rel.bump("patch")
        self.assertEqual(rel.read_versions(), ("1.2.3", "1.2.3"))  # nothing was changed

    def test_check_reports_mismatches(self):
        rel.MARKET.write_text(json.dumps({"plugins": [{"version": "1.2.2"}]}))
        self.assertTrue(any("marketplace.json says 1.2.2" in p for p in rel.check()))
        rel.PLUGIN.write_text(json.dumps({"version": "2.0.0"}))
        self.assertTrue(any("no section" in p for p in rel.check()))


if __name__ == "__main__":
    unittest.main()
