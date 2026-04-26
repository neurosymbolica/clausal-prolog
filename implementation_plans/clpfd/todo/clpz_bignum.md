# CLP(Z) bignum domain bounds — fix the C-extension int64 cap

## Context

`clpz_upgrade.md` lifted CLP(FD) to CLP(Z) at the **Python layer**: domain bounds
default to `(float('-inf'), float('inf'))`, and `_domain_add` / `_domain_sub`
/ `_domain_mult` / `_domain_negate` use Python `int` arithmetic which is
already bignum-safe.  All 54 `tests/test_clpz.py` tests pass.

**What was missed:** the C accelerators in `clausal/logic/_clpfd_core.c` and
`clausal/logic/_clpfd_propagate.c` shadow the Python implementations
(see `clpfd.py:236-247` and `:2516-2536`) and store bounds as `int64_t`.
`unpack_interval` in `_clpfd_domain_ops.h:28-63` calls `PyLong_AsLongLong`;
once a bound exceeds ±2⁶³ the call raises `OverflowError`.

### Reproduction (current state, 2026-04-26)

```
$ python -c 'from clausal.testing import load_clausal_module; ...'  # see investigation
Fib(92) = 7540113804746346429        # largest fitting in int64
Fib(93) → OverflowError: int too big to convert
Fib(95) → silently "no solution"     # worse: wrong-not-error
```

### Why this distorts benchmarks

`benchmarks/workloads.py:198-202` already documents the workaround:
`bench_wrap_fib` is capped at n=92 because the wrapped tabled `Fib/2` uses
`==` (CLP(Z)).  Sister benchmark `bench_tabling` runs at n=5000 because
`tabled_fib.clausal` uses `:=` (eval-and-unify, plain Python int) which
bypasses CLP(Z) entirely.

This makes `bench_wrap_fib` vs `bench_tabling` an apples-to-oranges
comparison for the SUB_CALL_SUSPENDABLE → tabled-callee path that Phase 5e
delivered.  `tests/test_backend_parity.py` and `wrap_tabled_fib.clausal`
have working-tree edits papering over the same hole.

### Solver correctness (independent of benchmarks)

For every clausal program using `==` / `<` / `>` / `+` / `-` / `*` arithmetic
on values that can grow past 2⁶³, the solver:
1. Raises a confusing `OverflowError` from inside C with no clausal-level
   stack frame, OR
2. Silently returns "no solution" when the bound is clamped to `INT64_MAX`
   and intersection produces `()`.

Both are bugs.  The fix is independent of the benchmark cleanup.

## Approach

Three options:

### Option A — Native bignum in C (`PyObject *` everywhere)

Replace `int64_t` storage in `_clpfd_*.c` with `PyObject *` (Python ints,
refcounted).  Comparisons go through `PyObject_RichCompareBool`, arithmetic
through `PyNumber_Add` etc.

- Pros: fast for any value.
- Cons: ~1500-line rewrite across two .c files; loses `__builtin_*_overflow`
  fast paths; reintroduces refcount complexity in every loop.

### Option B — Disable C accelerators

Set `_USE_C_DOMAINS = False` and `_USE_C_PROPAGATE = False` in `clpfd.py`.
The Python implementations are already correct for bignum.

- Pros: trivial; one-line + delete-imports.
- Cons: measured slowdown — `bench_fib_idiomatic(25)` 3.06 s → 4.04 s
  (~25 % regression) on this branch.  `bench_nqueens(8)` is unaffected
  (already dominated by labeling, not propagation).

### Option C — Hybrid: int64 fast path with bignum fallback (**recommended**)

Mirror the design already used by native arith stencils
(`runtime/stencils/templates/arith_add_var_var.c:55-94`):
detect overflow at the C entry point, fall back to a Python implementation
of the same operation, return the bignum result.

Concretely:
1. Replace `PyLong_AsLongLong(x)` in `unpack_interval` / `parse_bound` with
   `PyLong_AsLongLongAndOverflow(x, &ov)`; on `ov != 0` return a sentinel
   that propagates up.
2. Each C wrapper (`py_domain_intersection`, `py_domain_remove`, etc.)
   catches the bignum-bound sentinel and tail-calls the Python reference
   implementation.  The Python implementations are already in `clpfd.py`
   (lines 154-232) — they were **kept as the reference** specifically for
   this kind of fallback.
3. For propagators that compute sums in `double` (`sum_propagate`,
   `scalar_propagate`), defer to a Python helper when any input bound is
   bignum.  The Python `SumConstraint.propagate` / `ScalarProductConstraint
   .propagate` are still in `clpfd.py` and bignum-safe.

- Pros: keeps the int64 fast path for the common case (which today benches
  3.06 s on fib_idiomatic); slow path only for actual bignum data.
- Cons: requires touching 51 int64 sites in `_clpfd_propagate.c` plus
  `_clpfd_domain_ops.h`.  But each touch is mechanical.

**Recommendation: Option C.**  The fast-path/slow-path discipline matches
the rest of the codebase (`PyLong_AsLongAndOverflow` is already the pattern
in arith stencils).  Option B leaves a measurable regression we'd then
have to recover.  Option A is a 5-7 day rewrite for the same end-state
performance Option C reaches with ~1 day of mechanical edits.

## Sub-slices

Per `feedback_incremental_slicing.md` — split into independently-landable
sub-slices, each with tests and a commit.

### Slice 1 — bignum-safe `unpack_interval` / `parse_bound`

**Files:** `clausal/logic/_clpfd_domain_ops.h`.

Replace `PyLong_AsLongLong(...)` with `PyLong_AsLongLongAndOverflow(..., &ov)`
in `unpack_interval` and `parse_bound`.  On `ov != 0`, set a Python
`OverflowError`-equivalent sentinel and return -1.  Callers will already
treat -1 as "fall back to Python".

Add a public C function `int has_bignum_bound(PyObject *domain)` that scans
a domain tuple and returns 1 if any bound is bignum.  Callers use this to
short-circuit straight to the Python path, avoiding mid-loop bailout.

**Test:** unit test in a new `tests/test_clpz_bignum.py` that constructs a
domain `((2**70, 2**70),)` and verifies `domain_min`/`domain_max`/
`domain_size` return correct bignum values without raising.

**Commit gate:** `pytest tests/test_clpz_bignum.py tests/test_clpz.py
tests/test_clpfd.py -x -q` green.

### Slice 2 — bignum fallback in `_clpfd_core.c` wrappers

**Files:** `clausal/logic/_clpfd_core.c`; possibly `_clpfd_domain_ops.h`.

For each `py_domain_*` wrapper (`py_domain_intersection`, `py_domain_remove`,
`py_domain_remove_above`, `py_domain_remove_below`, `py_domain_from_range`,
`py_domain_size`, `py_domain_singleton`, `py_domain_min`, `py_domain_max`,
`py_domain_contains`, `py_domain_values`):

- Pre-check `has_bignum_bound` on inputs.
- If any input is bignum, tail-call the reference Python `domain_*` from
  `clpfd.py` via `PyObject_CallFunctionObjArgs`.  Cache the function refs
  in module-init the same way `fn_expr_domain` is cached
  (`_clpfd_propagate.c:25`).
- Otherwise proceed with the existing int64 path.

**Test:** extend `tests/test_clpz_bignum.py` with `domain_intersection`,
`domain_remove`, `domain_remove_above/below` against bignum domains.
Verify results match Python reference (which the test imports from
`clpfd.py` directly).

**Commit gate:** ditto.

### Slice 3 — bignum fallback in `eq_propagate` / `lt_propagate` /
            `le_propagate` ✅ **done**

**Files:** `clausal/logic/_clpfd_propagate.c`, `clausal/logic/clpfd.py`.

Done as part of the same `fix(clpz)` commit (amended).  The actual scope
went slightly beyond the plan because `c_narrow`'s CLP(R) sync and
`_fd_hook`'s int-unify path also unpack bounds via int64 — those needed
the same bignum-detect-and-fall-back treatment.  Concretely:

- Added Python helpers `_eq_propagate_bignum` / `_ne_propagate_bignum`
  / `_lt_propagate_bignum` / `_le_propagate_bignum` in `clpfd.py`,
  mirroring the corresponding `class.propagate` methods but using the
  public bignum-safe domain ops.
- C propagators `eq_propagate` / `ne_propagate` / `lt_propagate` /
  `le_propagate` now check `has_bignum_bound` on operand domains
  (or `is_bignum_int` on ground sides for `ne`) and tail-call the
  Python helper when bignum.  `ne_propagate` previously called
  `PyLong_AsLongLong(lhs)` and `domain_remove_c(domain, val)`
  directly — both overflow on bignum.
- `expr_domain_with_trail` and `expr_domain_fast` build a bignum
  singleton domain via `PyTuple_Pack` instead of overflowing on
  `PyLong_AsLongLong`.
- `c_narrow`'s CLP(R) sync uses `PyFloat_AsDouble` (handles bignum
  ints natively) instead of `domain_min_i64` / `domain_max_i64`.
- `_fd_hook` int-unify path detects bignum bound or value and uses
  `PyObject_RichCompareBool` against domain bounds instead of the
  int64 `domain_contains_i64`.

**Tests:** `tests/test_clpz_bignum.py::TestBignumPropagation`
(10 cases: eq/lt/le/gt/ge narrowing on bignum, bignum chain
propagation, eq compound bignum via linearise, eq inconsistency
wipe-out, ne excludes bignum value, ne+eq consistent / inconsistent)
and `TestBignumIntegration` (Fib(92), Fib(93), Fib(100), Fib(200)
end-to-end through `wrap_tabled_fib.clausal`).
Pre-existing failure `tests/conformity/iso_type_checking.clausal::
number: large int (via eval)` (`X == 10**100, number(X)`) now passes.
Two pre-existing tests in `tests/test_native_arith_stencils.py` had
to be updated — they checked `deref(out)` after the iteration ended
(when backtracking unbinds), which only worked under the
pre-bignum "0 solutions" regime; they now capture the binding
mid-iteration instead.

### Slice 4 — bignum fallback in `sum_propagate` / `scalar_propagate` ✅ **done**

**Files:** `clausal/logic/_clpfd_propagate.c`, `clausal/logic/clpfd.py`.

The C ``sum_propagate`` / ``scalar_propagate`` accumulate bounds in
``double``, which loses integer precision past 2⁵³, well below the
int64 ceiling.  Both bignum bounds AND large-but-int64 sums need the
bignum-safe Python path — this slice fixes that latent precision bug
in addition to the int64 cap.

- Added Python helpers `_sum_propagate_bignum` /
  `_scalar_propagate_bignum` in `clpfd.py`, mirroring the
  corresponding `class.propagate` methods using bignum-safe ops.
- C `sum_propagate` checks each operand domain via
  `has_bignum_bound` during the bound-collection loop, also checks
  the total domain after fetching it, and falls back to the Python
  helper if any are bignum or if the running double sum has exceeded
  `DOUBLE_PRECISE_INT_LIMIT` (2⁵³).
- C `scalar_propagate` mirrors the same pattern, with the
  additional check that no coefficient is bignum (`is_bignum_int`).

**Tests:** `tests/test_clpz_bignum.py::TestSumScalarBignum` (7 cases:
sum of bignum-domain vars, sum past 2⁵³ but in int64, sum with bignum
total domain, scalar product with bignum coefficient, scalar product
past 2⁵³, scalar product with negative bignum coefficient, int64
fast-path regression guard).  Verified zero new failures vs the
pre-Slice-4 baseline (57 vs 57 pre-existing failures in the broader
suite, all unrelated to CLP).

### Slice 5 — bench parity restoration  *(N/A in this branch)*

The original Slice 5 targeted phase-5f workloads (`bench_wrap_fib` cap
at n=92, `tests/test_backend_parity.py` workarounds, `wrap_tabled_fib.
clausal` modifications).  Those workloads don't exist in this branch —
they live in the `clausal-copy_patch` worktree.  No work to do here.

## Out of scope

- Native bignum **storage** in C (Option A).  If perf measurements after
  Slice 4 show the bignum-fallback path is hot for some workload, that
  becomes a follow-up plan.  For the workloads in `benchmarks/workloads.py`
  the fast path stays on int64 for everything except the wrap-fib bignum
  region above n≈92.
- `clpz_upgrade.md` Step 7 (`in_fd/3` predicate) and Step 8 (module
  rename).  Those are independent of the bignum cap and tracked separately.
- CLP(Q) and CLP(R) — they already use `Fraction`/`float` and are not
  affected.

## How to verify (full suite)

```bash
python -m pytest tests/ --ignore=tests/test_trealla_backend.py -x -q
python -m pytest tests/test_clpz.py tests/test_clpz_bignum.py
                  tests/test_clpfd.py tests/test_backend_parity.py -x -v
python benchmarks/workloads.py
```

Expected: all tests green; `bench_wrap_fib` runs at n=5000 in similar
wall-time to `bench_tabling` (within 2-3× — both do ~5000 tabled calls).
