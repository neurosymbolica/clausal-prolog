# fix(A02-F001): indexed dispatch must fall back to all-clauses scan when a non-var arg's index key is uncomputable

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md` A02-F001
**Tests:** `tests/audit_2026_07_05/test_02_compiler_heads.py::TestF001IndexedDispatchPartialTerms` (7 xfail — flip to pass)

## Bug

`_runtime_arg_key` returns the `_INDEX_VAR` sentinel for any non-var argument
it cannot canonicalise: a partial char-list `[X,"b","c"]`, a partial code-list
`[97, X]`, an empty list (whose unify-peer heads are keyed `""`/`b""`), any
SegList, and any scalar outside `_INDEXABLE_TYPES` (`Decimal`, `Fraction`,
`complex`). Every dispatch body then does `idx_dict.get(_INDEX_VAR)` → miss →
**default bucket** (var-headed clauses only):

- `arg_index.py:785-804` `_groundness_dispatch_body_single`
- `arg_index.py:807-831` `_groundness_dispatch_body_multi`
- `arg_index.py:448-477` `_joint_dispatch_body` (both-ground branch)
- `arg_index.py:650-684` `_make_secondary_dispatch_impl` (level 0 and level 1)

Solutions from keyed buckets that the arg would happily *unify* with are
silently lost; under joint/secondary dispatch with no var-headed clauses the
default is an **always-fail** function (`compiler/predicate.py:917,958`), so
the caller gets zero solutions outright. Linear-scan twins (<4 clauses,
`_INDEX_THRESHOLD`) return the right answers — semantics currently depend on
clause count.

## Fix direction

In every dispatch body: after computing `_k = _runtime_arg_key(_a)` on a
non-var `_a`, treat `_k is _INDEX_VAR` as **"key unknown" → route to the
all-clauses fallback (`fallback_fn` / `all_fn`)**, not the default bucket.
(A TypeError from `.get` should keep meaning "not this bucket" → default is
fine there only if the key was computable; simplest is to fold TypeError into
the same fallback.) For `_groundness_dispatch_body_multi`, an `_INDEX_VAR`
key at plan k should try the NEXT plan before falling back. For the joint
body, `_INDEX_VAR` in either component of `_jk` should degrade to the
corresponding single-position dispatch (which itself needs the same guard).
For secondary, `_INDEX_VAR` at level 0 → `fallback_fn`; at level 1 →
level-1 default is *correct only when* the key was computable; otherwise the
level-0 bucket list (which is exactly `level1_default` today — verify with
the R14/`sec2("a", [X], R)` case, currently consistent).

Distinguish carefully: "computable key, no bucket" (→ defaults, correct
today) vs "uncomputable key" (→ must scan). Only the latter changes.

Note: `_static_call_key` (compile-time specialisation) already returns `None`
for unknown shapes and the call site keeps the generic dispatch — no change
needed there; add a regression test if refactoring.

Cross-type numerics (`Decimal(1)` vs bucket key `1`) are fixed by the same
fallback; whether they should instead *key into* the numeric buckets is
parked as A02-D002 (depends on A01-D001).

## Acceptance

- The 7 xfails in `TestF001IndexedDispatchPartialTerms` pass; the 5 controls
  and all `TestIndexedDispatchGuards` / joint / secondary guards stay green.
- Ordering guard `test_clause_order_preserved_in_bucket` stays green (the
  fallback preserves full clause order by construction).
- No regression in `tests/test_numeric_head_literal.py`,
  `tests/test_structural_head_output_mode.py`, and the indexing perf tests.
