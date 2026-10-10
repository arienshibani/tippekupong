#!/usr/bin/env python3
"""Copy shared/*.md into every skill's references/ folder.

A Claude Code plugin install only contains plugins/oddsen/, so the skills cannot see /shared.
Their SKILL.md files say "read references/<file>.md", so each skill carries a copy. The copies
are committed; this script keeps them identical to /shared.

Usage:
    python3 scripts/sync_references.py           # write the copies
    python3 scripts/sync_references.py --check   # exit 1 if any copy is missing or differs (for CI and tests)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "shared"
SKILLS = ROOT / "plugins/oddsen/skills"


def main(argv):
    check = "--check" in argv
    problems, written = [], 0
    for skill in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        for src in sorted(SHARED.glob("*.md")):
            dest = skill / "references" / src.name
            if dest.exists() and dest.read_bytes() == src.read_bytes():
                continue
            if check:
                problems.append(f"{dest.relative_to(ROOT)} is {'missing' if not dest.exists() else 'out of date'}")
            else:
                dest.parent.mkdir(exist_ok=True)
                dest.write_bytes(src.read_bytes())
                written += 1
    if check:
        for p in problems:
            print(p, file=sys.stderr)
        if problems:
            print("run: python3 scripts/sync_references.py", file=sys.stderr)
        return 1 if problems else 0
    print(f"{written} reference file(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
