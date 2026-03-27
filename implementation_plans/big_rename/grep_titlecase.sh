#!/usr/bin/env bash
# Grep every source file under clausal/ for TitleCase names.
# For each file, writes a numbered-line output file mirroring the
# directory tree under  implementation_plans/big_rename/results/clausal/...
#
# Excludes: __pycache__, *.pyc, *.pyo, .so files, build/, dist/, *.egg-info,
#           implementation_plans/
#
# TitleCase pattern: a word boundary, then an uppercase letter followed by
# at least one lowercase letter, then another uppercase letter — the classic
# TitleCase / PascalCase signature.  We also require at least 2 characters
# total so we skip single caps like "I" or enum-style ALL_CAPS.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_DIR="$(cd "$(dirname "$0")" && pwd)/results"

# Clean previous run
rm -rf "$RESULTS_DIR"

# TitleCase regex: uppercase letter, then one or more lowercase, then another
# uppercase letter somewhere later — i.e. at least two "humps" or one
# uppercase-start + lowercase continuation that isn't ALL_CAPS.
# Simpler: match [A-Z][a-z]+[A-Z] anywhere in a word, OR a standalone
# [A-Z][a-z]{2,} token (single-word TitleCase like "Solve" or "Domain").
PATTERN='[A-Z][a-z]+[A-Z0-9]|[A-Z][a-z]{2,}'

# Find all text source files under clausal/, excluding junk
find "$REPO_ROOT/clausal" "$REPO_ROOT/tests" "$REPO_ROOT/docs" \
    -type f \
    \( -name '*.py' -o -name '*.clausal' -o -name '*.pl' -o -name '*.md' -o -name '*.rst' -o -name '*.txt' -o -name '*.toml' -o -name '*.cfg' -o -name '*.yaml' -o -name '*.yml' -o -name '*.sh' \) \
    ! -path '*/__pycache__/*' \
    ! -path '*/build/*' \
    ! -path '*/dist/*' \
    ! -path '*.egg-info/*' \
    ! -path '*/implementation_plans/*' \
    | sort | while IFS= read -r filepath; do

    # Make path relative to repo root
    relpath="${filepath#"$REPO_ROOT"/}"

    # Grep for TitleCase, with line numbers (-n)
    # Use grep -E (extended regex) and -n for line numbers
    matches=$(grep -nE "$PATTERN" "$filepath" 2>/dev/null || true)

    if [ -n "$matches" ]; then
        outfile="$RESULTS_DIR/$relpath"
        mkdir -p "$(dirname "$outfile")"
        echo "$matches" > "$outfile"
    fi
done

# Summary
total_files=$(find "$RESULTS_DIR" -type f 2>/dev/null | wc -l)
echo "Done. $total_files files with TitleCase matches written under:"
echo "  $RESULTS_DIR"
