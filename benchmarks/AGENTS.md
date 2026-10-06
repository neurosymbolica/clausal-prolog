# benchmarks/ — profiling workloads and micro-benchmarks

Standalone scripts that time the engine; not part of the package and not run in
CI. `workloads.py` holds the shared workloads; the other scripts profile them or
time one compiler fast path. Background and the optimisation work items they
fed: [../implementation_plans/benchmarking/BENCHMARKING.md](../implementation_plans/benchmarking/BENCHMARKING.md).

Up: [../AGENTS.md](../AGENTS.md)

## Map

| File | What |
|---|---|
| `workloads.py` | `bench_fib`, `bench_nqueens`, `bench_qsort`, `bench_graph`, `bench_tabling`, `bench_struct_tabling[_tagged]`, `bench_naf_ite`, `bench_thunk_atoms`; `python benchmarks/workloads.py` smoke-runs them all |
| `run_cprofile.py` | cProfile over fib/nqueens/qsort/graph/tabling -> `profiles/<name>.prof` |
| `run_pyspy.py` | py-spy flamegraphs -> `flamegraphs/<name>.svg` (needs `pip install py-spy`) |
| `microbench.py` | ns/op for deref, unify, trail mark/undo, trampoline dispatch |
| `bench_*.py` | One fast path each: bytes / str head-literal dispatch (`bench_bytes_dispatch`, `bench_f046_head_dispatch`), constant-list membership, term construction |
| `profiles/*.prof` | Committed cProfile output from an earlier run (not regenerated automatically) |

## Running

Run from the repo root with the engine built (`pip install -e .`).
`run_cprofile.py` and `run_pyspy.py` import `benchmarks.workloads`, so run them
as modules: `python -m benchmarks.run_cprofile`. The scripts in `bench_*.py`
and `microbench.py` run directly (`python benchmarks/microbench.py`).

## Gotchas

- **`workloads.py` is half-broken since the extension flip (2026-10-02).**
  Verified 2026-10-06: `bench_tabling`, `bench_struct_tabling`,
  `bench_struct_tabling_tagged` and `bench_naf_ite` open fixtures under their
  pre-flip names (`tests/fixtures/tabled_fib.clausal`, `struct_tabling.clausal`,
  `struct_tabling_tagged.clausal`, `bench_naf_ite.clausal`) and raise
  `FileNotFoundError` — the files are now `.seam`. `bench_thunk_atoms` writes
  seam source to a temp file with suffix `.clausal`, which is now read as ISO
  Clausal Prolog and fails with a `SyntaxError`. fib/nqueens/qsort/graph work.
  Known, unfixed; `run_cprofile.py` hits the tabling one.
- `tests/test_clpz.py` imports `bench_nqueens` from here, so changing its
  signature or default can break the engine suite.
