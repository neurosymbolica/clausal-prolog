#!/bin/sh
# Trace bv.pl's decisions while a solved chain X1 =< ... =< Xn is bound to
# 0..n-1, in the port and in an instrumented copy of Scryer's clpq.pl, and
# print the first divergence.  See
# implementation_plans/clpq/2026-11-03-chain-binding-divergence.md.
#
#   sh benchmarks/clpq_chain_binding_trace/run.sh OUTDIR [N] [forward|backward|all]
#
# The installed Scryer library is not touched: the instrumented copy is
# written to OUTDIR and loaded from there.
set -e
out=$1; n=${2:-6}; mode=${3:-all}
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
scryer=${CLAUSAL_SCRYER:-/workspace/scryer-prolog-clpq/target/release/scryer-prolog}
lib=${SCRYER_CLPQ_PL:-/workspace/scryer-prolog-clpq/src/lib/clpq.pl}
python=${PYTHON:-python}
mkdir -p "$out"
python3 "$here/instrument_scryer_clpq.py" "$lib" "$out/clpq_tr.pl"
cp "$here/scryer_trace.pl" "$out/scryer_trace.pl"
(cd "$out" && "$scryer" scryer_trace.pl -g "run($n, $mode)" -g halt) > "$out/scryer_${n}_$mode.txt" 2>&1
PYTHONPATH=$root CLAUSAL_CLPQ=holzbaur "$python" "$here/port_trace.py" "$n" "$mode" > "$out/port_${n}_$mode.txt"
python3 "$here/compare_traces.py" "$out/port_${n}_$mode.txt" "$out/scryer_${n}_$mode.txt"
