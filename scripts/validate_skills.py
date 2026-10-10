#!/usr/bin/env python3
"""Validate every skill under plugins/tippekupong/skills.

Checks: SKILL.md exists, has YAML frontmatter with `name` and `description`,
name matches folder and is kebab-case, description <= 1024 chars,
and the manifests parse as JSON.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "tippekupong" / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def plain_scalar_problem(text: str):
    """Claude Code reads frontmatter leniently, but strict YAML parsers (the skills.sh CLI, Claude.ai uploads,
    directory scanners) reject an unquoted value containing ': ' or ' #'. Such a skill is silently skipped."""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    for line in (m.group(1).splitlines() if m else []):
        if line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value[:1] in ("'", '"', ">", "|"):
            continue
        if ": " in value or " #" in value or value.endswith(":"):
            return f"`{key.strip()}` has an unquoted ': ' or ' #' that strict YAML parsers reject; reword it or quote the whole value"
    return None


def main() -> int:
    errors = []

    for manifest in [ROOT / ".claude-plugin" / "marketplace.json",
                     ROOT / "plugins" / "tippekupong" / ".claude-plugin" / "plugin.json"]:
        try:
            json.loads(manifest.read_text())
        except Exception as e:  # noqa: BLE001
            errors.append(f"{manifest.relative_to(ROOT)}: invalid JSON ({e})")

    skills = [p for p in SKILLS.iterdir() if p.is_dir()] if SKILLS.exists() else []
    for d in sorted(skills):
        rel = d.relative_to(ROOT)
        md = d / "SKILL.md"
        if not md.exists():
            errors.append(f"{rel}: missing SKILL.md")
            continue
        fm = frontmatter(md.read_text())
        name, desc = fm.get("name"), fm.get("description")
        if not name:
            errors.append(f"{rel}: frontmatter missing `name`")
        elif name != d.name:
            errors.append(f"{rel}: name '{name}' != folder '{d.name}'")
        elif not NAME_RE.match(name):
            errors.append(f"{rel}: name '{name}' is not kebab-case")
        if not desc:
            errors.append(f"{rel}: frontmatter missing `description`")
        elif len(desc) > 1024:
            errors.append(f"{rel}: description is {len(desc)} chars (max 1024)")
        elif plain_scalar_problem(md.read_text()):
            errors.append(f"{rel}: {plain_scalar_problem(md.read_text())}")

    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(skills)} skill(s) checked, {len(errors)} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
