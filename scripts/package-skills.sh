#!/usr/bin/env bash
# Build one self-contained zip per skill into dist/, for upload to Claude.ai / Claude desktop.
# Shared references in /shared are copied into each skill's references/ folder.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$ROOT/plugins/oddsen/skills"
DIST="$ROOT/dist"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT

rm -rf "$DIST" && mkdir -p "$DIST"

shopt -s nullglob
count=0
for skill in "$SKILLS_DIR"/*/; do
  name="$(basename "$skill")"
  [[ -f "$skill/SKILL.md" ]] || { echo "skip $name (no SKILL.md)"; continue; }

  cp -R "$skill" "$BUILD/$name"
  mkdir -p "$BUILD/$name/references"
  cp "$ROOT"/shared/*.md "$BUILD/$name/references/"

  (cd "$BUILD" && zip -qr "$DIST/$name.zip" "$name")
  echo "built dist/$name.zip"
  count=$((count + 1))
done

echo "$count skill(s) packaged."
