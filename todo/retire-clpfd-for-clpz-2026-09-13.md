# Retire `clpfd` for `clpz` — Markus Triska: clpz SUPERSEDES clpfd

**Operator, 2026-09-13, after speaking to Markus Triska: "we should only use clpz in Clausal, it
supersedes clpfd."** Asked as "can we remove clpfd?" — and measured, that is **two questions with
very different answers.** Do not treat it as one rename.

## Measured scope, 2026-09-13 on canonical `750e6ae1`

    clausal/logic     16 files, 108 mentions   + _clpfd_core.c, _clpfd_propagate.c, the .so pair
    clausal/tools      4 files,  29 mentions
    clausal/modules    2 files,   2 mentions
    docs              37 files, 235 mentions
    tests             33 files, 483 mentions

857 mentions, 92 files. But the count is the least useful number here.

## Question 1: the EXPORT spelling — small, valuable, mostly already done

`Dialect.clpfd_module` is **already a per-dialect knob**: `prolog_dialect.py:82` says `"clpfd"`,
`:104` says `"clpz"`, `:119` says `"fd"`. So the export side is parameterised and Triska's ruling
is a change of DEFAULT plus the `_CLPFD_CANONICAL` policy at `clausal_to_prolog.py:2123`.

Measured by iso-export-lane, and it settles the direction: **`library(clpfd)` raises
existence_error in BOTH Scryer and Trealla; `library(clpz)` works in both.** So the current
default emits a library neither reference system has.

**This half is iso-export-lane's and is already in motion** under the operator's `#=` ruling.
Nothing for engine-lane to do but stay out of the way, and rename the knob if it moves.

## Question 2: the ENGINE's internal module names — churn, with a real hazard

`clausal/logic/clpfd.py`, `_clpfd_core.c`, `_clpfd_propagate.c`, `_clpfd_domain_ops.h` and four
built `.so` files. **Renaming these is a C-source change**, which means:

* a rebuild everywhere, and the `.so` rename-swap hazard — never `build_ext --inplace` on a tree
  long-lived processes have imported (SIGBUS later); see the rename-swap procedure
* box, which is x86_64 and clock-skewed, needs `--force` or the rebuild silently skips
* the drift-gated forks (executor-train, clausify-tda) if any gate names these modules

**And no user sees any of it.** Measured: `clpfd` is NOT a user-facing spelling. A `.clausal` file
does not write `py.clpfd`; the one fixture named `units_clpfd.clausal` is named after the
implementation, not importing it. `clausal/modules/` mentions it only in two prose comments.

So renaming the internals buys tidiness and costs a C rebuild across three trees plus a hazard
that has already produced one SIGBUS in this repo's history.

## Recommendation

**Do question 1. Defer question 2 until something forces it**, and record here that it was
DEFERRED rather than missed — the value is in what Clausal EMITS and what its docs TEACH, not in
what its private C module is called.

Ordering within question 1:

1. `_CLPFD_CANONICAL` policy + the emitted library name (iso-export-lane, in motion)
2. **docs — 235 mentions across 37 files, and this is the half that teaches.** A user reading
   `docs/constraints.md` should see `clpz`. Larger than the code change and lower risk.
3. `Dialect.clpfd_module` -> `clp_module` or similar, once (1) settles what it holds

## A live caveat for anyone doing (1)

`#=` under CLP(Z) is **integer-only**, so `V #= 155.05` is not a clpz goal. The exporter can now
emit fractional money at a use site (an inexact minor-unit fold), so the `#=` conversion will
meet a value it cannot express. Raised with iso-export-lane 2026-09-13; unresolved. **This is the
one thing in this todo that can produce a wrong exported program rather than an untidy one.**

## Not to be confused with

`clpz3` (the Z3 backend) and `clpb`/`clpq`/`clpr` are different libraries and are not in scope.
A blind `s/clpfd/clpz/` would hit `clpz_bignum.md` references inside `clpfd.py` that already say
clpz, and prose in `_ratio_data.py` and `reflection.py` that names the FILE rather than the
library.
