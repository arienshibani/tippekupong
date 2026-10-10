#!/usr/bin/env python3
"""Versioning helper for releases.

Usage:
    python3 scripts/release.py version              # print the current version
    python3 scripts/release.py check                # versions agree and CHANGELOG has a section for it (CI)
    python3 scripts/release.py notes <version>      # print that version's CHANGELOG section (release notes)
    python3 scripts/release.py bump patch|minor|major|X.Y.Z
        moves the "Unreleased" entries into a new dated section and updates both manifests

The release workflow (.github/workflows/release.yml) creates the GitHub release when a version
that has no tag yet lands on main. Standard library only.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins/tippekupong/.claude-plugin/plugin.json"
MARKET = ROOT / ".claude-plugin/marketplace.json"
CHANGELOG = ROOT / "CHANGELOG.md"
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ReleaseError(Exception):
    pass


def read_versions():
    plugin = json.loads(PLUGIN.read_text())["version"]
    market = json.loads(MARKET.read_text())["plugins"][0]["version"]
    return plugin, market


def section(text, version):
    """Body of '## <version> ...' up to the next '## ', or None."""
    m = re.search(rf"^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else None


def check():
    plugin, market = read_versions()
    problems = []
    if not SEMVER.match(plugin):
        problems.append(f"plugin version '{plugin}' is not X.Y.Z")
    if plugin != market:
        problems.append(f"plugin.json says {plugin} but marketplace.json says {market}")
    body = section(CHANGELOG.read_text(), plugin)
    if not body:
        problems.append(f"CHANGELOG.md has no section (or an empty one) for {plugin}")
    return problems


def next_version(current, level):
    if SEMVER.match(level):
        return level
    major, minor, patch = map(int, SEMVER.match(current).groups())
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ReleaseError("bump needs patch, minor, major or X.Y.Z")


def bump(level, today=None):
    current, _ = read_versions()
    new = next_version(current, level)
    if new == current:
        raise ReleaseError(f"already at {current}")
    text = CHANGELOG.read_text()
    unreleased = section(text, "Unreleased")
    if not unreleased:
        raise ReleaseError("write the changes under '## Unreleased' in CHANGELOG.md first")
    stamp = (today or date.today()).isoformat()
    text = re.sub(r"^## Unreleased\b.*?(?=^## )", f"## Unreleased\n\n## {new} - {stamp}\n\n{unreleased}\n\n",
                  text, count=1, flags=re.S | re.M)
    CHANGELOG.write_text(text)
    for path, getter in ((PLUGIN, lambda d: d), (MARKET, lambda d: d["plugins"][0])):
        data = json.loads(path.read_text())
        getter(data)["version"] = new
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return current, new


def main(argv):
    try:
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd == "version":
            print(read_versions()[0])
        elif cmd == "check":
            problems = check()
            for p in problems:
                print(p, file=sys.stderr)
            return 1 if problems else 0
        elif cmd == "notes" and len(argv) == 3:
            body = section(CHANGELOG.read_text(), argv[2])
            if not body:
                raise ReleaseError(f"no CHANGELOG section for {argv[2]}")
            print(body)
        elif cmd == "bump" and len(argv) == 3:
            old, new = bump(argv[2])
            print(f"{old} -> {new}. Review CHANGELOG.md, then commit and push to main; the release workflow does the rest.")
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except ReleaseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
