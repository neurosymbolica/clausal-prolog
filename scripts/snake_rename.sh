#!/usr/bin/env bash
# Word-boundary rename of predicate names across an explicit file set.
# Usage: snake_rename.sh <file1> <file2> ... -- Old1=new1 Old2=new2 ...
# Scoped deliberately: pass only the module source + its tests/fixtures/docs,
# never historical dirs (implementation_plans/, docs/superpowers/, todo/).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

files=()
while [ "${1:-}" != "--" ]; do
  [ -z "${1:-}" ] && { echo "missing -- separator"; exit 2; }
  files+=("$1"); shift
done
shift  # drop --
pairs=("$@")

for f in "${files[@]}"; do
  [ -f "$f" ] || { echo "skip (absent): $f"; continue; }
  for p in "${pairs[@]}"; do
    old="${p%%=*}"; new="${p#*=}"
    sed -i -E "s/\\b${old}\\b/${new}/g" "$f"
  done
done
echo "renamed ${#pairs[@]} names across ${#files[@]} files"
