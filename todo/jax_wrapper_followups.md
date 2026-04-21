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

## 2. `logsumexp` placement vs. Phase 11

**Current state:** `logsumexp/3` is in `py.jax` (Phase 7), backed by
`jax.scipy.special.logsumexp` via a lazy `_jss()` accessor.

**Plan assumption:** Phase 11 (`jax.scipy` wrapper — `phase11_scipy.md`)
is supposed to cover `jax.scipy.special` and `jax.scipy.stats`.
`logsumexp` is the natural flagship entry for `py.jax_scipy`.

### Risk

When Phase 11 lands, the obvious thing is to re-implement `logsumexp`
in `clausal/modules/py/jax_scipy.py`. If that re-implementation drifts
from the Phase 7 version (different kwargs, different arity), we end up
with two predicates named `logsumexp` that behave differently depending
on which module the user imports from.

### What to do in Phase 11

Pick **one** of:

- **Re-export.** `py.jax_scipy` imports `logsumexp` from `py.jax` and
  re-exports. Single implementation; users can import from either
  module. Simplest.
- **Move and re-export the other direction.** Move the implementation to
  `py.jax_scipy`, have `py.jax` import from it. Slightly more natural
  ordering (scipy lives in its own module) but means `py.jax` depends
  on `py.jax_scipy`.
- **Delete from `py.jax`.** Keep only the `py.jax_scipy` version. A
  breaking change for anyone who imported it from `py.jax` — which
  right now is only the Phase 7 test fixture, so easy to update.

### Recommendation

Re-export from `py.jax_scipy` (`py.jax_scipy.logsumexp is
py.jax.logsumexp`). Matches how dtype constants are re-exported from
`py.jax`.

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

## 4. Python-builtin shadowing list is growing

**Current shadowed names** at the `py.jax` module level (via
`-import_from`):

- `sum`, `mean`, `max`, `min`, `abs`, `clip` — Phase 1
- `any`, `all` — Phase 6
- `round`, `pow` — Phase 7

These only shadow inside Clausal code that imports them. Python code
using `py.jax` as a module (`from clausal.modules.py import jax`)
is unaffected — `jax.sum` is a `ModulePredicate`, not the builtin.

### When it bites

Clausal user writes, in a `.clausal` file:

```
-import_from(py.jax, [sum, round])
Test("range sum") <- (
    sum([1, 2, 3], S),          # py.jax.sum — array reducer, not Python's!
    round(3.7, R)               # py.jax.round — array rounder
)
```

`sum([1, 2, 3], _)` will actually work because JAX happily arrays-ifies
Python lists. But the semantics is "reduce this array", not "add these
numbers" — a subtle semantic trap when users think they're calling
Python's `sum`.

### Disposition

**Not a bug.** The shadowing is the whole point of `-import_from`.
Worth a docs bullet in `docs/jax.md` listing the full shadow set so
users know what they're importing. Deferred until the list stabilizes
at the end of the phase rollout.

---

## Summary

| # | Item | Severity | Action |
|---|---|---|---|
| 1 | `_bidir_2` float check fragility | Low | Docs note this quarter; revisit if a caller hits it |
| 2 | `logsumexp` placement for Phase 11 | Low | Decide at Phase 11 start; re-export preferred |
| 3 | Partial-bijection NaN silence | Low | Add regression tests next time we touch Phase 7 predicates |
| 4 | Shadowed-builtin docs bullet | Low | Write at end of phase rollout (Phases 14/15) |
