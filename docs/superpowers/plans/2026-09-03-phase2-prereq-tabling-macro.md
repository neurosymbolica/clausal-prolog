# Phase 2 prerequisite: fix bench_tabling's two bugs, establish the walker-heavy macro

Spec: implementation_plans/tagged-tuple-term-representation.md §3c closing note ("the repo
currently has NO working walker-heavy macro workload") + todo/bench-tabling-overflow-on-display-2026-09-03.md.
User un-parked Phase 2 on 2026-09-03; this stage is its measurement prerequisite and is
independently mergeable (both fixes are real bugs regardless of Phase 2's fate). CLONE ONLY.

## Global Constraints

- Work ONLY in /workspace/clausal-bug-fix/.claude/worktrees/phase2-prereq (branch feat/phase2-prereq-tabling-macro); all commands from there with /workspace/clausal/venv/bin/python.
- NEVER `git add -A`; NEVER `git stash`. Explicit paths. Commit trailer (two lines):
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01G7xiWqatWtL6zNQDc7nspk
- Full-suite runs: exactly `/workspace/clausal/venv/bin/python -m pytest tests/ -q --tb=no --continue-on-collection-errors`; failure-set NAME-diff vs baseline_failures.txt (worktree root) must be empty per task.
- The five walkers and their sync contract, eval_harness (GATE_CORE), and `_get_dispatch` are untouchable.
- `tests/test_funnel_lint.py` must stay green (it will fail if a fix reintroduces a bypassed probe).

## Task 1: fix clpfd `_narrow()`'s unconditional float() on bignum bounds

Files: `clausal/logic/clpfd.py` (the `_narrow` function), tests in `tests/` (find the clpfd suite by grepping; extend it).

Diagnosed (verified in measurement-report.md of the phase1 SDD, both pre- and post-Phase-0):
`_narrow()` converts domain bounds via `float()` unconditionally; once values exceed float range
(Fib growth passes it near fib(1475)), `OverflowError: int too large to convert to float` is
raised from inside constraint propagation. Python ints are arbitrary precision — the float
conversion is at most a fast-path/comparison convenience.

- Read `_narrow` and its callers first; determine WHY the float() exists (comparison speed?
  interop with a C core? rounding of rational bounds?). If it guards a genuine float-domain
  feature, make the conversion conditional (try/except OverflowError → integer path, or a
  bit_length pre-check), keeping float behavior byte-identical for in-range values. If it is
  incidental, use integer comparisons outright. State the determination with evidence.
- Check the C side: `clausal/logic/_clpfd_core.c` / `_clpfd_propagate.c` may have a twin of
  this conversion — if the Python fix just moves the crash into C, fix the pair consistently
  (same determination discipline); if C is unaffected (different code path), demonstrate that.
- TDD: a test constructing a clpfd domain/constraint with bounds > float-max that previously
  raised OverflowError and now propagates correctly (assert a real narrowing result, not just
  "no crash").

Run: clpfd-focused suites + full suite once, empty name-diff.

## Task 2: diagnose, then fix, bench_tabling's non-termination at n=5000

Files: TBD by diagnosis — `benchmarks/workloads.py` (if benchmark construction) or engine
tabling files (if a real bug). Tests per determination.

Symptom (verified both pre/post Phase 0): `bench_tabling()` at n=5000 yields the first answer,
then backtracking goes exponential as if the predicate were not tabled at all.

THIS IS A DIAGNOSIS-FIRST TASK. Follow systematic debugging: reproduce at the smallest n that
shows super-linear growth (time n=50,100,200,400 — geometric blowup will show long before
5000); form hypotheses and TEST them before fixing. Candidate hypotheses to check (not
exhaustive):
  a. The benchmark constructs its tabled predicate wrongly (e.g. re-declares/tables per call,
     queries through a path that bypasses the tabled entry, or forces full enumeration where
     one answer suffices).
  b. Tabling re-entry/variant-miss: the second and later calls miss the table (subgoal key
     instability — e.g. keys involving big ints or the recently-changed normalize path) and
     re-execute.
  c. Answer-set explosion: tabling works but the driver iterates ALL answers of a
     multi-solution formulation.
Instrument cheaply (table hit/miss counters exist? grep tabling.py for stats; else add
temporary prints in a scratch copy — NOT committed).
- If (a): fix the benchmark; commit with a comment explaining the wrong shape.
- If (b) or another ENGINE bug: STOP after diagnosis if the fix looks nontrivial (>~40 lines
  or touches the C tabling core) — report BLOCKED with the full diagnosis; the controller
  will re-scope. A small, clearly-correct engine fix (with TDD + failure-set parity) may
  proceed.
- Either way the report must contain the measured n-vs-time table proving termination is now
  ~linear-ish in n, and bench_tabling(5000) completing with a sensible time.
- Also fix the original display line if it is still float-converting the bignum result
  (print digit count) — trivial, include it.

Run: tabling-focused suites (tests/test_tabling*.py etc.) + full suite once, empty name-diff.

## Task 3: the walker-heavy macro measurement (report-only, no commits beyond benchmarks/ tweaks already made)

With bench_tabling working: interleaved A/B, A = pre-Phase-0 f0db3fb0 + the SAME Task-1/2
fixes cherry-picked/patched in (the fixes must be applied identically to both sides or the
comparison is invalid — patch A's worktree files directly, uncommitted), B = this branch HEAD.
- Throwaway A worktree (git worktree add + build_ext + verify import resolution + apply
  patches; diff the patched files between sides to prove byte-identity of the fix).
- bench_tabling at the largest n that runs in ~5-30s per iteration, 5 rounds/side interleaved,
  fresh subprocess each. Also run bench_fib once per side as a control (expected ~1.0).
- Report: medians, min-max, B/A. This is THE walker-heavy macro number for Phase 0 — whatever
  it is, report it straight (the op-level prediction is 1.4-2.2× on the walk-dominated
  fraction; the workload's compute fraction dilutes it — estimate the walk fraction with one
  cProfile run per side and include the top-10 cumulative functions).
- Cleanup the throwaway worktree (--force sanctioned). Nothing committed by this task.
