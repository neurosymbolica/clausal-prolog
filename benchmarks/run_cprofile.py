"""Run all benchmark workloads under cProfile and write .prof files.

Usage (from project root):
    python benchmarks/run_cprofile.py

Output:
    benchmarks/profiles/<name>.prof   -- binary profile data
    stdout                            -- pstats summary (top 30 by cumulative time)

To explore a profile interactively afterward:
    python -m pstats benchmarks/profiles/fib.prof
"""

from __future__ import annotations

import cProfile
import io
import pathlib
import pstats

from benchmarks.workloads import (
    bench_fib,
    bench_nqueens,
    bench_qsort,
    bench_graph,
    bench_tabling,
)

WORKLOADS: dict[str, object] = {
    "fib":      bench_fib,
    "nqueens":  bench_nqueens,
    "qsort":    bench_qsort,
    "graph":    bench_graph,
    "tabling":  bench_tabling,
}

out_dir = pathlib.Path("benchmarks/profiles")
out_dir.mkdir(parents=True, exist_ok=True)

for name, fn in WORKLOADS.items():
    print(f"\n{'=' * 60}")
    print(f"  Profiling: {name}")
    print(f"{'=' * 60}")

    pr = cProfile.Profile()
    pr.enable()
    fn()
    pr.disable()

    prof_path = out_dir / f"{name}.prof"
    pr.dump_stats(prof_path)

    buf = io.StringIO()
    ps = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    ps.print_stats(30)
    print(buf.getvalue())
    print(f"  Saved: {prof_path}")
