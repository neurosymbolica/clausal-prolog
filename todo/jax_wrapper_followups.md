# JAX wrapper — cross-phase follow-ups

Known issues and open questions from Phases 1–7 of the `py.jax`
wrapper (`clausal/modules/py/jax.py`). None block shipping the phases
they came from; collected here so they're not lost.

---

## 1. `_bidir_2` check mode is fragile for floats

**Affects:** every bijective predicate in the wrapper —
`logarithm`, `sine`, `cosine`, `tangent` (Phase 7); `fft_transform`,
`real_fft`, `fft_transform_2d`, `fft_transform_nd`, `fft_shift`
(Phase 5); `jax_numpy`, `array_list` (Phase 1); likely `tree_flatten`
when Phase 9 lands.

**Helper:** `clausal/modules/py/_helpers.py:_bidir_2` (and
`_bidir_3_mid`).

### What happens

When both arguments are bound, `_bidir_2` runs `forward(x)`, then:

1. Tries `unify(y_raw, out, trail)`.
2. On exception (e.g. JAX's elementwise `==` returning a bool array),
   falls back to `_values_equal(out, y)` which does
   `bool((out == y).all())`.

For floating-point round-trips, bit-exact equality almost never
holds — `arcsin(sin(0.5))` ≠ `0.5` at the last-ULP level, `ifft(fft(x))`
has imaginary noise, etc. So `sine(0.5, 0.479426)` or
`fft_transform(X, Y)` with numerically-correct `Y` will *fail* the
check.

### What's OK right now

- Forward-only (`sine(ANGLE, -VALUE)`) and backward-only modes work.
- Integer / exact round-trips (e.g. `logarithm(1.0, 0.0)` in tests)
  happen to land on zero, so they pass.
- `allclose/2,/4` (Phase 6) exists and works correctly.

### Options

1. **Document and move on.** Add a note to `docs/jax.md` and each
   phase's implementation plan: "for float check mode on bijective
   predicates, use `allclose/2` explicitly." Lowest effort.

2. **Make `_bidir_2` tolerance-aware.** Accept an optional `atol`/`rtol`
   kwarg at construction time and use `jnp.allclose` in the check
   fallback. More invasive; requires deciding sensible defaults.

3. **Split check mode off.** Drop the `(+X, +Y)` check mode from
   `_bidir_2` entirely; require callers to use `allclose`. Breaking
   change for whatever already relies on it (likely nothing —
   integer-only check-mode tests are rare).

### Recommendation

Option 1 (docs) for now. Revisit with option 2 if a concrete caller
hits it. No code change required to ship Phases 8+.

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

## 3. Partial-bijection domain is silent

**Affects:** `sine`, `cosine`, `tangent` (Phase 7) backward mode;
`logarithm` (Phase 7) forward mode.

`arcsin(2.0)` returns `nan`; `log(-1.0)` returns `nan`. Neither raises.
The predicate succeeds and `nan` propagates through the rest of the
clause until something else fails (or silently doesn't).

### What's documented

`docs/jax.md` "Advanced Math → Caveats" has a bullet: "Out-of-domain
NaN." Good enough for now.

### What's missing

A regression test that locks in the NaN-silence behavior. If someone
later wraps these with explicit domain checks, existing callers who
(wrongly) relied on NaN propagation would break without warning.

### Cost

One test per predicate per direction. Cheap. Bundle with whatever phase
next touches these predicates, or with a general "numeric edge cases"
sweep.

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

## 5. `*_like` predicates don't accept opts

**Affects:** `zeros_like/2`, `ones_like/2`, `full_like/3` (Phase 14).

**Current state:** each wraps the corresponding `jnp.*_like` with no opts
arity, mirroring the PyTorch Phase 13 shape of the plan.

**Gap:** JAX's `jnp.zeros_like(a, dtype=None, shape=None, device=None)`
accepts kwargs that let a caller reuse the template array's shape while
overriding its dtype (or vice versa). Clausal users who want "same
shape as A but float64" currently have to escape to `++()`.

### Fix when it matters

Add a higher-arity variant with opts, same pattern as `zeros/3` and
`ones/3`:

```python
zeros_like = _pred("zeros_like",
    (2, _pure(lambda a: _jnp_mod().zeros_like(a))),
    (3, _pure(lambda a, opts: _jnp_mod().zeros_like(a, **opts))),
)
```

`full_like` would gain a `/4` variant `(+A, +VALUE, +OPTS, -R)`.

Tiny, non-breaking. Wait for the first caller who asks — the opts path
is a nice-to-have, not a gap the typical "build a zeroed params tree"
user runs into.

---

## Summary

| # | Item | Severity | Action |
|---|---|---|---|
| 1 | `_bidir_2` float check fragility | Low | Docs note this quarter; revisit if a caller hits it |
| 2 | `logsumexp` placement for Phase 11 | Resolved | ✅ Aliased: `py.jax_scipy.logsumexp is py.jax.logsumexp` (2026-04-21) |
| 3 | Partial-bijection NaN silence | Low | Add regression tests next time we touch Phase 7 predicates |
| 4 | Shadowed-builtin docs bullet | Resolved | ✅ Docs section added post-Phase-15 (2026-04-21) |
| 5 | `*_like` predicates lack opts arity | Low | Add when a caller wants dtype override without `++()` |
