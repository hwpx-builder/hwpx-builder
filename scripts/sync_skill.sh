#!/usr/bin/env bash
# Refresh the local, untracked skill copy at .claude/skills/hwpx-builder/ from
# the repo root.
#
# The repo root *is* the skill — SKILL.md, hwpxkit/, references/, examples/ and
# scripts/ are exactly what a skill directory holds. Claude Code only discovers
# skills under `.claude/skills/<name>/`, so working inside this repo needs a copy
# there. That copy is gitignored: committing it would mean two copies of every
# file in one repo, and they would drift the first time you edited either one.
#
#   ./scripts/sync_skill.sh        # after changing anything at the repo root
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/.claude/skills/hwpx-builder"

rm -rf "$DEST"
mkdir -p "$DEST"
cp "$ROOT"/SKILL.md "$ROOT"/LICENSE "$ROOT"/NOTICE "$ROOT"/pyproject.toml "$DEST"/
cp -r "$ROOT"/hwpxkit "$ROOT"/references "$ROOT"/scripts "$ROOT"/examples "$DEST"/
rm -rf "$DEST"/hwpxkit/__pycache__

echo "synced -> $DEST ($(find "$DEST" -type f | wc -l | tr -d ' ') files)"
