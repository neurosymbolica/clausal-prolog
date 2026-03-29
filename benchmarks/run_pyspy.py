"""Generate SVG flamegraphs for each workload using py-spy.

Usage (from project root):
    python benchmarks/run_pyspy.py

Requirements:
    pip install py-spy

Output:
    benchmarks/flamegraphs/<name>.svg   -- open in any web browser

py-spy runs as a subprocess profiler, so it captures both Python and C frames,
giving a complete picture of where time is spent including _variables.c and
_trampoline.c hotspots.
"""

from __future__ import annotations

import subprocess
import sys
import pathlib

WORKLOADS = ["fib", "nqueens", "qsort", "graph", "tabling"]

out_dir = pathlib.Path("benchmarks/flamegraphs")
out_dir.mkdir(parents=True, exist_ok=True)

for name in WORKLOADS:
    svg = out_dir / f"{name}.svg"
    cmd = [
        "py-spy", "record",
        "--output", str(svg),
        "--format", "flamegraph",
        "--",
        sys.executable, "-c",
        f"from benchmarks.workloads import bench_{name}; bench_{name}()",
    ]
    print(f"Profiling {name} → {svg} ...")
    try:
        subprocess.run(cmd, check=True)
        print(f"  OK: {svg}")
    except subprocess.CalledProcessError as e:
        print(f"  FAILED ({e.returncode}): {e}")
    except FileNotFoundError:
        print("  ERROR: py-spy not found. Install with: pip install py-spy")
        break
