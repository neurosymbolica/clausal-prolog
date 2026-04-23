# JAX wrapper — cross-phase follow-ups

Known issues and open questions from Phases 1–7 of the `py.jax`
wrapper (`clausal/modules/py/jax.py`). None block shipping the phases
they came from; collected here so they're not lost.

---

## 1. `_bidir_2` check mode is fragile for floats — RESOLVED (2026-04-22)

**Resolution:** Option 1 (docs). Added a dedicated gotcha section to
`docs/jax.md` — "Gotcha — bidirectional check mode is bit-exact" —
that enumerates every affected predicate, shows the failure mode, and
points users at `allclose/2` / `allclose/4` for tolerant checks. The
Phase 7 Advanced Math caveat list now links to that section.

No code change. `_bidir_2` still does bit-exact comparison when both
sides are bound; callers who need tolerance use `allclose`. If a
concrete caller ever needs tolerance inside a single predicate, revisit
Option 2 (tolerance-aware `_bidir_2`).

---

## 2. `logsumexp` placement vs. Phase 11 — RESOLVED (2026-04-21)

**Final state:** the canonical `logsumexp` lives in
`clausal/modules/py/jax.py` (Phase 7), with arities `/2` (full reduce)
and `/3` (along AXIS). `clausal/modules/py/jax_scipy.py` imports it
via `from clausal.modules.py.jax import logsumexp as _jax_logsumexp`
and assigns `logsumexp = _jax_logsumexp`, so
`py.jax.logsumexp is py.jax_scipy.logsumexp` — one implementation,
reachable from either import path. Drift is impossible without touching
both files in the same commit.

Import direction is `py.jax_scipy → py.jax`, matching the existing
`_ensure_jax` import. No cycle.

All 508 jax tests pass against the aliased version
(`tests/test_jax_infra.py`), including both the Phase 7 fixture
(imports from `py.jax`) and the Phase 11 fixture (imports from
`py.jax_scipy`).

---

## 3. Partial-bijection domain is silent — RESOLVED (2026-04-22)

**Resolution:** Added four regression tests to
`tests/fixtures/jax_math_tests.clausal` (registered in
`TestJaxMathFixture` in `tests/test_jax_infra.py`) that lock in
NaN-silence:

- `logarithm of -1 is NaN (not a raise)` — `log(-1) → NaN`
- `sine backward on 2.0 is NaN (out of [-1, 1])` — `arcsin(2) → NaN`
- `cosine backward on 2.0 is NaN (out of [-1, 1])` — `arccos(2) → NaN`
- `tangent backward on any real succeeds (arctan has no domain gap)` —
  asserts tangent backward does *not* produce NaN on large inputs

Uses `not allclose(R, R)` as the NaN detector (NaN ≠ NaN, so
`allclose(nan, nan)` is false). If someone later wraps these with
explicit domain checks, the first three tests will fail and force a
deliberate decision about the behaviour change.

---

## 4. Python-builtin shadowing list — RESOLVED (Phase 15)

**Final shadowed set** at the `py.jax` module level (enumerated against
`builtins` after the full 15-phase rollout):

`abs`, `all`, `any`, `max`, `min`, `pow`, `round`, `sum`.

Phase 14 and Phase 15 introduced no new shadows (`sub`, `div`,
`floor_div`, `mod`, `neg`, `reciprocal`, `median`, `std`, `var`,
`argmin`, `argmax`, `sort`, `argsort`, `topk`, `nonzero`, `unique`,
`argpartition` — none are Python builtins). The submodules
(`jax_random`, `jax_nn`, `jax_scipy`, `jax_tree`, `jax_transforms`,
`jax_sharding`) shadow nothing.

**Resolution:** documented in `docs/jax.md` under
"Gotcha — predicates that shadow Python builtins", including the
JAX-coerces-Python-lists trap and how to mix in Python's builtin
`sum`/`max` when needed. The Advanced Math caveat that referenced only
`round` now links to the central section.

The original preamble is kept below for historical context.

### Original preamble

These only shadow inside Clausal code that imports them. Python code
using `py.jax` as a module (`from clausal.modules.py import jax`)
is unaffected — `jax.sum` is a `ModulePredicate`, not the builtin.
The shadowing is the whole point of `-import_from`, not a bug.

---

## 5. `*_like` predicates don't accept opts — RESOLVED (2026-04-22)

**Resolution:** Added opts arities, matching the `zeros/3` / `ones/3` /
`full/4` pattern:

- `zeros_like(A, R)` → `zeros_like(A, OPTS, R)` (/2 + /3)
- `ones_like(A, R)` → `ones_like(A, OPTS, R)` (/2 + /3)
- `full_like(A, VALUE, R)` → `full_like(A, VALUE, OPTS, R)` (/3 + /4)

`OPTS` passes through to `jnp.*_like(**opts)`, so callers can override
`dtype` or `shape` while reusing the template array.

Documented in `docs/jax.md` "zeros_like, ones_like, full_like" and
covered by three new tests in
`tests/fixtures/jax_creation2_tests.clausal` (`zeros_like opts
overrides dtype`, `ones_like opts overrides dtype`, `full_like opts
overrides dtype`).

---

## Summary

| # | Item | Severity | Action |
|---|---|---|---|
| 1 | `_bidir_2` float check fragility | Resolved | ✅ Docs gotcha section added + linked from Phase 7 caveats (2026-04-22) |
| 2 | `logsumexp` placement for Phase 11 | Resolved | ✅ Aliased: `py.jax_scipy.logsumexp is py.jax.logsumexp` (2026-04-21) |
| 3 | Partial-bijection NaN silence | Resolved | ✅ 4 regression tests locking in NaN behaviour (2026-04-22) |
| 4 | Shadowed-builtin docs bullet | Resolved | ✅ Docs section added post-Phase-15 (2026-04-21) |
| 5 | `*_like` predicates lack opts arity | Resolved | ✅ `/3` (zeros_like, ones_like) and `/4` (full_like) added (2026-04-22) |

All items resolved. File can be deleted once a human reads the history.
