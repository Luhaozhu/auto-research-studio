#!/usr/bin/env bash
# Vendor shared/ master copies into each skill so every skill is a
# self-contained, independently-distributable closure (PLAN.md section 1.1).
#
# Edit code ONLY in shared/. Run this before publishing. CI should run
# `vendor.sh --check` to fail if any vendored copy drifted from its master.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARED="$ROOT/shared"
SKILLS="$ROOT/skills"

# Which shared assets each skill needs: "<skill>:<lib csv>:<agents csv>"
MANIFEST=(
  "research-wiki:semantic_scholar.py,vault_io.py:librarian.md"
  "idea-forge:semantic_scholar.py,vault_io.py:generator.md,reviewer.md"
  "idea-to-pr:semantic_scholar.py,vault_io.py:reviewer.md"
  "code-to-idea:semantic_scholar.py,vault_io.py:generator.md,reviewer.md"
)

CHECK=0
[[ "${1:-}" == "--check" ]] && CHECK=1

sync_file() {  # src dst
  local src="$1" dst="$2"
  [[ -f "$src" ]] || { echo "  ! master missing: $src" >&2; return 1; }
  if [[ $CHECK -eq 1 ]]; then
    if ! cmp -s "$src" "$dst"; then
      echo "DRIFT: $dst differs from master $src" >&2
      return 1
    fi
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  vendored $(basename "$src") -> ${dst#$ROOT/}"
  fi
}

rc=0
for row in "${MANIFEST[@]}"; do
  IFS=':' read -r skill libs agents <<< "$row"
  skill_dir="$SKILLS/$skill"
  [[ -d "$skill_dir" ]] || { echo "skip (no skill dir): $skill"; continue; }
  echo "[$skill]"
  IFS=',' read -ra LIBS <<< "$libs"
  for f in "${LIBS[@]}"; do
    sync_file "$SHARED/lib/$f" "$skill_dir/scripts/lib/$f" || rc=1
  done
  IFS=',' read -ra AGS <<< "$agents"
  for a in "${AGS[@]}"; do
    sync_file "$SHARED/agents/$a" "$skill_dir/agents/$a" || rc=1
  done
done

if [[ $CHECK -eq 1 && $rc -eq 0 ]]; then echo "vendor check OK"; fi
exit $rc
