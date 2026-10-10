import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/tippekupong/skills"
SHARED = ROOT / "shared"


class ReferencesTravelWithTheSkills(unittest.TestCase):
    """A plugin install contains only plugins/tippekupong/, so each skill must carry its own references/."""

    def skills(self):
        return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())

    def test_every_referenced_file_exists_in_the_skill_and_matches_shared(self):
        pattern = re.compile(r"references/([A-Za-z0-9_.-]+\.md)")
        checked = 0
        for skill in self.skills():
            for name in sorted(set(pattern.findall((skill / "SKILL.md").read_text()))):
                local, shared = skill / "references" / name, SHARED / name
                self.assertTrue(shared.exists(), f"{skill.name} mentions references/{name} but shared/{name} does not exist")
                self.assertTrue(local.exists(), f"{skill.name}/references/{name} is missing: run scripts/sync_references.py")
                self.assertEqual(local.read_bytes(), shared.read_bytes(), f"{local} differs from shared/{name}")
                checked += 1
        self.assertGreater(checked, 25)

    def test_the_sync_script_agrees(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/sync_references.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_responsible_gambling_is_in_every_skill(self):
        for skill in self.skills():
            self.assertTrue((skill / "references/responsible-gambling.md").exists(), skill.name)


if __name__ == "__main__":
    unittest.main()
