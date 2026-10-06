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

- The workloads load SEAM fixtures (`tests/fixtures/*.seam`); a temp file of
  seam source must take the seam suffix (`_suffixes.CLAUSAL_SUFFIXES`), since
  a `.clausal` file is read as Clausal Prolog.
- `tests/test_clpz.py` imports `bench_nqueens` from here, so changing its
  signature or default can break the engine suite.
