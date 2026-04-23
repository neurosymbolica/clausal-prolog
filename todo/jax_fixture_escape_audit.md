# Audit — `++()` usage in JAX test fixtures

Sweep of 251 `++()` occurrences across 12 `tests/fixtures/jax_*.clausal`
files. `++()` drops out of backtracking / relational semantics into a
raw Python expression, so each occurrence is a candidate for "we
should have a predicate for that" — unless the escape is semantically
necessary (passing a Python callable to a JAX transform, reading a
Python class for a registry, etc.).

This doc categorises the uses and proposes which should turn into
predicates. It's a design discussion, not a task list.

**Update (2026-04-23):** Rank 1 applied — 104 array-literal escapes
across 4 fixtures rewritten to `array/2`, `ones/2`, `zeros/2`,
`arange/2`. Zero wrapper changes; the predicates already accepted
scalar/int shapes and list literals. Count now 147 across 12 files.
Ranks 2–7 are still open work.

---

## File distribution

| Fixture | Count |
|---|---|
| `jax_transforms_tests.clausal` | 57 |
| `jax_optax_tests.clausal` | 57 |
| `jax_equinox_tests.clausal` | 46 |
| `jax_tree_tests.clausal` | 32 |
| `jax_flax_tests.clausal` | 23 |
| `jax_fft_tests.clausal` | 9 |
| `jax_sharding_tests.clausal` | 7 |
| `jax_nn_tree_integration.clausal` | 6 |
| `jax_linalg_tests.clausal` | 6 |
| `jax_nn_tests.clausal` | 5 |
| `jax_scipy_tests.clausal` | 2 |
| `jax_random_tests.clausal` | 1 |

Transforms + optax + equinox + tree account for ~75% — unsurprisingly
the higher-order surfaces.

---

## Categories

### A. Array literal construction (~104 occurrences, ~41%)

`++(jax.numpy.array(3.0))`, `++(jax.numpy.array([1.0, 2.0]))`,
`++(jax.numpy.ones(4))`, `++(jax.numpy.zeros((3, 3)))`, etc.

Examples:
- `jax_transforms_tests.clausal:15` — `X is ++(jax.numpy.array(3.0))`
- `jax_equinox_tests.clausal:30` — `X is ++(jax.numpy.ones(4))`
- `jax_flax_tests.clausal:24` — `EXAMPLE is ++(jax.numpy.ones(4))`
- `jax_optax_tests.clausal:34` — `X is ++(jax.numpy.zeros((3, 2)))`

**Why the escape:** `py.jax` already exports `array/2`, `ones/2`,
`zeros/2`, `arange/2`. The escape is usually terser:
- `array/2` requires a list; `++(jnp.array(3.0))` creates a **0-D**
  array, which our `array(3.0, X)` would not — it would fail or wrap
  `3.0` as `[3.0]`.
- `ones/2` / `zeros/2` require a list shape; `++(jnp.ones(4))` is
  cheaper than `ones([4], X)` for 1-D shapes.
- `dtype` kwargs need the opts-dict arity, which is awkward for a
  throwaway literal.

**Fixability: HIGH.** Concrete changes that would eliminate most:
1. `array/2`: accept scalar input → produce 0-D array (matches `jnp`).
2. `ones/2`, `zeros/2`, `full/3`, `arange/N`: accept int as shape
   shorthand for 1-D, not just list.
3. Add a `scalar/2` convenience: `scalar(3.0, X)` → 0-D array. (Or
   fold into `array/2` above.)

Expected reduction: ~80/104 uses. The remaining ~20 are multi-dim
literals like `jnp.array([[1.0, 2.0], [3.0, 4.0]])` where the list
path already works — just not yet used.

### B. Lambda construction for transforms (~41 occurrences, ~16%)

`F is ++(lambda x: x ** 2)`, `F is ++(lambda m: jnp.sum(m(X) ** 2))`,
`FN is ++(lambda b: b * 0)` (for `tree_at_apply`), etc.

Examples:
- `jax_transforms_tests.clausal:14` — `F is ++(lambda x: x ** 2)`
  passed to `grad_value`
- `jax_tree_tests.clausal:173` — `F is ++(lambda acc, x: acc + x)`
  passed to `tree_reduce`
- `jax_equinox_tests.clausal:198` — `WHERE is ++(lambda m: m.bias)`
  passed to `tree_at_set`

**Why the escape:** JAX transforms consume Python callables; a lambda
is the natural carrier. The escape is semantically correct.

**Fixability: LOW.** Options considered:
- An expression-to-lambda meta-predicate (`lambda_expr(Expr, Lambda)`)
  would need to capture free variables, name them, and compile. Large
  surface, ambiguous semantics (what's a free var vs a literal?).
- Passing Clausal predicates as functions via a
  `predicate_as_callable/2` bridge exists in principle but is niche
  — performance is poor under `jit` and the semantics-of-non-
  determinism-under-trace is a minefield.

**Verdict:** Escape-is-right. Document the pattern; don't try to
replace it. The `tree_at_set`/`tree_at_apply` "where" lambda is a
well-known Equinox idiom (Phase 17 plan Issue 5 already accepts
this).

### C. Attribute / field access on opaque objects (~23 occurrences, ~9%)

`++(BN.inference)`, `++(NEW_MODEL.bias)`, `++(V.real)`, `++(arr.T)`,
`++(model.weight)`.

Examples:
- `jax_equinox_tests.clausal:323` — `++(BN.inference) == False`
  (reading BatchNorm's mode field)
- `jax_fft_tests.clausal:23` — `V_REAL is ++(V.real)` (complex split)
- `jax_equinox_tests.clausal:198` — `NB is ++(NEW_MODEL.bias)`

**Why the escape:** No predicate for attribute read. `tree_at_set/4`
covers write; there's no `tree_at_get`.

**Fixability: MEDIUM.**
1. `tree_at_get(WHERE, TREE, VALUE)` — mirror of `tree_at_set`. Low
   cost, natural symmetry. Covers `++(M.bias)` → `tree_at_get(++(lambda
   m: m.bias), M, BIAS)`. Still requires the lambda but at least the
   read-access shape is relational.
2. `field_value(OBJ, "name", V)` — generic attribute read. Loses the
   type-safety of the lambda form but removes the second `++()`.
3. For complex `real`/`imag`: `complex_split/3` — split complex array
   into (real, imag) or the bidirectional pair.
4. For `arr.T`: already covered by `transpose/2`. The `++()` is
   laziness — document/fix in place.

Expected reduction: ~18/23 with `tree_at_get` + `complex_split` +
switching the `arr.T` cases to `transpose/2`.

### D. Tuple/list indexing of returns (~7 occurrences, ~3%)

`H is ++(R[0])`, `NW is ++(NEW["w"])`, `G is ++(VJP_RESULT[0])`.

Examples:
- `jax_equinox_tests.clausal:135-136` — LSTM cell returns `(h, (h,
  c))`; test uses `R is ++(M(X, (H0, C0)))` then `H is ++(R[0])`
- `jax_transforms_tests.clausal:95` — `G is ++(VJP_RESULT[0])`

**Why the escape:** Most of these patterns *already work* without
`++()` via pattern unification — `R is (H, _)`. The tests are just
written the Python way.

**Fixability: HIGH but nearly free.** Just rewrite the call sites
to use `R is (H, _)` / `(V, G) is VJP_RESULT`. No new predicates
needed. Dict access (`NEW["w"]`) needs a `dict_get/3` or similar
unless `DictTerm` unification already covers it (worth checking).

### E. Higher-order JAX calls we haven't wrapped (~8 occurrences, ~3%)

`++(jax.grad(F))`, `++(jax.vmap(BN, axis_name="batch", in_axes=(0,
None), out_axes=(0, None)))`, `++(jax.jit(F))`.

Examples:
- `jax_equinox_tests.clausal:303-306` — vmap with named axis +
  in_axes/out_axes spec (stateful-BatchNorm pattern from Phase 17b)
- `jax_transforms_tests.clausal:163` — `GRAD is ++(jax.grad(F))`
  wrapping grad for further use

**Why the escape:**
- Plain `++(jax.grad(F))` — already have `grad_value/3` for the
  one-shot case; these sites want the transformed function itself,
  which is a design gap.
- vmap with axis_name + in_axes: no Clausal predicate constructs this
  shape. `filter_vmap_apply/3,/4` (Phase 17) takes an opts dict but
  users reach for the escape form because typing `{"axis_name":
  "batch", "in_axes": [0, ++(None)], "out_axes": [0, ++(None)]}` is
  more typing than `++(jax.vmap(...))`.

**Fixability: MEDIUM.**
1. Add `grad_fn/2` and `jit_fn/2` (return the transformed function,
   not just the one-shot result). Both are two-line predicates.
2. For vmap-with-axis-name: add a dedicated
   `vmap_axis(+M, +AXIS_NAME, +IN_AXES, +OUT_AXES, -VMAPPED)`
   predicate. Ugly signature but it's ugly in JAX too. Probably not
   worth it for the 1–2 sites that use it.

### F. Type coercion to Python scalars (~10 occurrences, ~4%)

`++(float(V))`, `++(str(P))`, `++(int(L))`.

Examples:
- `jax_optax_tests.clausal:155` — `V0_F is ++(float(V0))`
- `jax_sharding_tests.clausal:118` — `S is ++(str(P))`

**Why the escape:** No predicate for scalar extraction. `array_list`
works for arrays but not for 0-D → Python float.

**Fixability: HIGH, trivial.** Add:
- `to_float(X, F)`, `to_int(X, I)`, `to_string(X, S)` — straight
  `float(x)` / `int(x)` / `str(x)` wrappers.
- `scalar_value(X, V)` — extract Python scalar from 0-D array.

~10 sites eliminated for ~30 lines of wrapper code.

### G. Python-None literal inside term constructors (~2 occurrences, ~1%)

`partition_spec(["x", ++(None)], P)` — passing Python `None` as an
element of a list.

Examples:
- `jax_sharding_tests.clausal:123` — sharding a dim with `None`

**Why the escape:** Clausal has no atomic `None`. `++(None)` is the
idiomatic bridge.

**Fixability: LOW.** Worth an atom export from `py.jax_sharding` —
`null` or `no_partition` — pointing at Python `None`. Small.

### H. Misc (~56 occurrences, ~22%)

Everything else — passing `equinox.is_array` as a filter callable,
referencing `equinox.nn.BatchNorm` for `make_with_state/4`, test
assertions like `array_list(Y, FV)` where `FV is ++(float(V))`
chain, arithmetic on previously-escape-derived values.

Most of these are **genuinely right** — importing a Python class to
use as a registry key, passing a library function as a filter spec,
etc. Each `++()` in this bucket is a one-off that doesn't merit a
predicate.

---

## Priority ranking (ROI on predicate work)

| Rank | Change | Uses fixed | Cost |
|---|---|---|---|
| 1 | Accept scalar/int shorthand in `array/2`, `ones/2`, `zeros/2`, `full/3`, `arange/N` | ~80 | Low — update existing dispatches |
| 2 | Rewrite tuple-indexing sites to use pattern unification (`R is (H, _)`) | ~5 | Trivial — fixture edits only |
| 3 | Add `to_float/2`, `to_int/2`, `to_string/2` | ~10 | Low — new module, maybe `py.jax` itself |
| 4 | Add `tree_at_get/3` (mirror of `tree_at_set/4`) | ~8 | Low — mirrors existing pattern |
| 5 | Add `complex_split/3` (real/imag bidirectional) | ~3 | Low |
| 6 | Add `grad_fn/2`, `jit_fn/2` (return-the-function forms) | ~3 | Low |
| 7 | Export `null` atom from `py.jax_sharding` for Python `None` | ~2 | Trivial |

Ranks 1–3 together eliminate ~95 escapes for ~day of work. Ranks 4–7
are cleanup but lower ROI.

**Not worth doing:** lambda-construction replacement (category B),
vmap-axis-name wrapper (part of category E), generic field-access
predicate (category C alt 2). All are semantically-right escapes or
have very few sites.

---

## Open questions

1. **Should `array/2` be bidirectional scalar-wise?** — `array(3.0,
   X)` forward is obvious; `array(S, X)` with bound `X` (0-D array)
   could unify `S` with the Python scalar. That overlaps with
   `to_float/2`. Decide: one predicate or two? Leaning: two, because
   `array/2` already means "construct", and overloading it with
   extraction invites mode-confusion.

2. **`tree_at_get` vs `field_value`?** — `tree_at_get` follows an
   Equinox idiom (path-by-callable) and composes with `tree_at_set`.
   `field_value` is simpler but string-based (fragile to refactors).
   Leaning: `tree_at_get` — consistent with the existing write path.

3. **Where do the new `to_*` predicates live?** — `py.jax` exports
   are already large. A new `py.jax_convert` module (paralleling
   `py.jax_tree`) vs. folding into `py.jax`. Leaning: `py.jax` since
   there are only three and they concern `jax.Array`.

4. **Should we touch `py.torch` for consistency?** — PyTorch has
   similar `++()` patterns; any pattern we normalise in JAX should
   probably land equivalently in PyTorch. Scope for a follow-up audit.

---

## Cross-references

- [`todo/jax_registries_discussion.md`](jax_registries_discussion.md)
  — companion audit (when to add a registry)
- `implementation_plans/jax/phase14_creation_arith.md` — the creation
  predicates that need the int-shape shorthand
- `clausal/modules/py/jax.py` — where most rank-1 changes land
