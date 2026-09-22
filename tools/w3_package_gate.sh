#!/usr/bin/env bash
# W3 package gate -- run the OUT-OF-TREE `_get_dispatch` implementors' suites
# (clausal-provenance, clausal-scipy, clausal-spacy: 11 implementors, 2026-09-22)
# against an engine ROOM, in a venv of the gate's own.
#
# Why its own venv: the namespace merge in clausal/modules/__init__.py is keyed
# to site-packages (installed distributions and the editable finder's
# NAMESPACES), so a package tree sitting under packages/ is NOT importable from
# a checkout -- all three suites were red on main for that reason alone, and
# "NEW 0 / GONE 0 across the packages" compared two piles of rubble.  And the
# shared venv is symlinked by every lane, so nothing gets installed into it.
#
# What varies and what is fixed: the ENGINE is the room's (cwd wins: pytest is
# run from inside the room, and the script asserts clausal.__file__ is there);
# the PACKAGES are re-installed editable from the room's packages/ on every
# run (--no-deps: their `clausal>=` requirement is the room), so a change under
# packages/ is under test too.  Compare two rooms by diffing the .set files.
#
# Usage:  tools/w3_package_gate.sh <venv-dir> <room> <out-prefix>
#   writes <out-prefix>.txt (pytest output) and <out-prefix>.set (sorted
#   FAILED/ERROR node ids), and prints the set size and the summary line.
#
# Known pre-existing reds on the 2026-09-22 baseline (105 / 1566 at 34a6dc79):
# clausal-spacy fixtures FAIL rather than skip without spacy installed (spacy
# is not installed here on purpose -- it is heavy and the implementor imports
# without it); clausal-scipy's units/dims tests; clausal-provenance's fixtures.
# None of those is W2's; the gate is a DIFF, not a green bar.
set -euo pipefail
venv=$1; room=$2; out=$3
room=$(cd "$room" && pwd)
if [ ! -x "$venv/bin/python" ]; then
    python3 -m venv "$venv"
    "$venv/bin/pip" install -q pytest numpy scipy
fi
"$venv/bin/pip" install -q --no-deps \
    -e "$room/packages/clausal-provenance" \
    -e "$room/packages/clausal-scipy" \
    -e "$room/packages/clausal-spacy"
cd "$room"
"$venv/bin/python" - "$room" <<'PY'
import sys, clausal, clausal.modules.provenance, clausal.modules.py.scipy_stats
room = sys.argv[1]
assert clausal.__file__.startswith(room), clausal.__file__
assert clausal.modules.provenance.__file__.startswith(room), clausal.modules.provenance.__file__
print("engine:", clausal.__file__)
PY
set +e
timeout 900 "$venv/bin/python" -m pytest \
    packages/clausal-provenance/tests packages/clausal-scipy/tests packages/clausal-spacy/tests \
    -q -rfE -p no:cacheprovider --continue-on-collection-errors > "$out.txt" 2>&1
echo "exit=$?" >> "$out.txt"
set -e
grep -E "^(FAILED|ERROR) " "$out.txt" | sed -E 's/ - .*//' | sort -u > "$out.set"
echo "set size: $(wc -l < "$out.set")  (denominator: $(grep -cE '^(FAILED|ERROR) ' "$out.txt") FAILED/ERROR lines)"
grep -E "^[0-9]+ (failed|passed)" "$out.txt" || tail -1 "$out.txt"
