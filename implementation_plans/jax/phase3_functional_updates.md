# Phase 3 — Functional Updates (`.at`)

JAX's `.at[idx].set(v)` idiom is pure and relational — the array is not
mutated; a new array is returned. PyTorch's equivalent (`tensor[idx] =
v`) mutates, which broke backtracking. JAX's approach is the one we
wanted PyTorch to have.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1 — `_pure()`, `_pred()`, `_deep_deref()`,
`_jnp_mod()` already in place.

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `at_set` | `/4` | `(+A, +IDX, +VAL, -A2)` | partial (need original A to invert) | `A.at[IDX].set(VAL)` |
| `at_add` | `/4` | `(+A, +IDX, +VAL, -A2)` | partial | `A.at[IDX].add(VAL)` |
| `at_mul` | `/4` | `(+A, +IDX, +VAL, -A2)` | partial | `A.at[IDX].mul(VAL)` |
| `at_min` | `/4` | `(+A, +IDX, +VAL, -A2)` | partial | `A.at[IDX].min(VAL)` |
| `at_max` | `/4` | `(+A, +IDX, +VAL, -A2)` | partial | `A.at[IDX].max(VAL)` |
| `at_get` | `/3` | `(+A, +IDX, -VAL)` | partial | `A.at[IDX].get()` |

All Tier 1 (pure). Not bijective in the strict sense (inverting `at_set`
requires knowing the previous value at that index), but the forward
operation is a clean value-returning pure function.

---

## Context and Reference Patterns

### Why this matters

PyTorch required users to write `tensor[idx] = val` — an in-place
mutation that breaks Clausal's backtracking guarantee. The PyTorch
wrapper has `scatter`/`gather` as a workaround, but not `.at` because
PyTorch doesn't have it.

JAX's `.at` idiom is pure, so we can expose it directly:

```python
# JAX Python code
y = x.at[2].set(99)
# y is a new array, x is unchanged
```

### Implementation pattern

`.at[idx]` is an indexing proxy; calling `.set(val)` on it returns a new
array. Wrap with `_pure()`:

```python
at_set = _pred("at_set",
    (4, _pure(lambda a, idx, val: a.at[idx].set(val))),
)

at_add = _pred("at_add",
    (4, _pure(lambda a, idx, val: a.at[idx].add(val))),
)
# ...
```

### Index argument types

JAX indexes support:
- Integer: `a.at[2]`
- Tuple of integers: `a.at[(1, 2)]`
- Slice: `a.at[1:3]`
- Array of indices: `a.at[jnp.array([0, 2, 4])]`
- Boolean mask: `a.at[mask]`

Clausal users will pass:
- Integer: from Clausal integer literals
- List of integers: passed to `jnp.array` and used as fancy index
- A JAX array: pass-through

`_deep_deref()` handles lists already. For list indices, we want to
convert to a JAX array before calling `.at[...]`. Decision: **require
the user to pass a JAX array for fancy indexing**. Simple integer or
tuple-of-integer indices work directly. Test both:

```clausal
# Simple integer index
at_set(A, 2, 99, A2)

# Tuple index for multi-dim
at_set(A, (1, 2), 99, A2)

# Fancy index — user constructs the JAX array first
IDX is ++(jnp.array([0, 2, 4])),
at_set(A, IDX, 99, A2)
```

### Slice indexing — out of scope for Phase 3

Slices (`a.at[1:3]`) can't be expressed as Clausal terms without a slice
literal. Users who need slice updates use `lax.dynamic_update_slice`
directly via `++()`, or we defer slice support to a later phase.

### `at_get`

Returns a scalar or sub-array:

```python
at_get = _pred("at_get",
    (3, _pure(lambda a, idx: a.at[idx].get())),
)
```

Equivalent to `a[idx]` for most indices, but `.at[...].get()` composes
with JAX transforms (unlike plain `a[idx]` under some edge conditions).

---

## Example Usage

```clausal
-import_from(py.jax, [array, arange, shape, array_list,
                      at_set, at_add, at_mul, at_get,
                      reshape])
-import_module(jax)

Test("at_set scalar index") <- (
    arange(0, 6, A),
    at_set(A, 2, 99, A2),
    array_list(A2, [0, 1, 99, 3, 4, 5]),
    # A is unchanged — this is the relational guarantee
    array_list(A, [0, 1, 2, 3, 4, 5])
)

Test("at_set tuple index") <- (
    arange(0, 6, A),
    reshape(A, [2, 3], A2),
    at_set(A2, (1, 2), 99, A3),
    array_list(A3, [[0, 1, 2], [3, 4, 99]])
)

Test("at_add") <- (
    array([10, 20, 30], A),
    at_add(A, 1, 5, A2),
    array_list(A2, [10, 25, 30])
)

Test("at_mul") <- (
    array([1, 2, 3], A),
    at_mul(A, 2, 10, A2),
    array_list(A2, [1, 2, 30])
)

Test("at_get scalar") <- (
    array([10, 20, 30], A),
    at_get(A, 1, V),
    array_list(V, 20)
)

Test("fancy index via jnp.array") <- (
    array([10, 20, 30, 40, 50], A),
    IDX is ++(jax.numpy.array([0, 2, 4])),
    at_set(A, IDX, 0, A2),
    array_list(A2, [0, 20, 0, 40, 0])
)

# The relational guarantee
Test("at_set does not mutate input") <- (
    arange(0, 3, A),
    at_set(A, 0, 99, _A2),
    # A still has its original values after the update
    array_list(A, [0, 1, 2])
)
```

---

## Tests

**`.clausal` integration tests** (append to `tests/fixtures/jax_array_tests.clausal`
or create `tests/fixtures/jax_at_tests.clausal`):

- Every `at_*` predicate with scalar indices
- Tuple indices for multi-dim arrays
- Fancy indices via `jnp.array(...)` constructed in a `++()` escape
- `at_get` for scalar and multi-dim
- Non-mutation guarantee: after `at_set(A, ..., A2)`, `A` still has
  original values
- Edge cases: `at_set` at boundary indices, out-of-bounds behaviour
  (JAX's semantics: out-of-bounds clips silently — document)

---

## Docs

Update `docs/jax.md` with a "Functional Updates" section:
- Explain the `.at` idiom and why JAX is pure
- Contrast briefly with PyTorch's mutating assignment
- List each `at_*` predicate with an example
- Note that out-of-bounds indices are silently clipped by default
  (JAX's `mode='promise_in_bounds'`)

---

## Issues

Implementation completed. Notes from the pass:

- **`_deep_deref` now recurses into tuples** (in `clausal/modules/py/_helpers.py`).
  Tuple-of-ground-ints always worked; the fix makes tuple indices
  containing bound Clausal variables — e.g. `at_set(M, (ROW, COL),
  99, M2)` — resolve correctly. Tuples stay tuples (not converted to
  lists), which is required because JAX treats tuple vs list indices
  differently. Non-regressing: the full `test_jax_infra` / `test_torch`
  / `test_scipy_cluster` suite (536 tests) passes both before and after.
- **Python lists are not valid JAX indices.** Modern JAX (0.4+) raises
  `TypeError` on `arr.at[[0, 2, 4]]` and directs users to
  `jnp.array([0, 2, 4])`. The plan's Known Item #2 suggested list-as-
  fancy-index worked — it does not. `_pure`'s exception-to-failure
  conversion means list indices fail the predicate cleanly. Fixture
  test `at_set with python list index fails (not a jnp.array)`
  pins this behaviour.
- The fancy-index example in the plan used
  `IDX is ++(jax.numpy.array([0, 2, 4]))`; the test fixture uses
  `array([0, 2, 4], IDX)` instead, since `py.jax`'s `array/2` already
  constructs a `jax.Array` with no `++()` escape.
- Out-of-bounds `at_set` is silently dropped by default (`mode='promise_in_bounds'`).
  Documented in `docs/jax.md` with a fixture test pinning the
  behaviour so that any future JAX default change shows up as a
  regression.

Known items to watch:

1. **Out-of-bounds behaviour.** JAX defaults to silent clipping for
   out-of-bounds indices. Some users expect a failure. Document clearly;
   consider adding `at_set` variants with a mode kwarg in a future
   phase.

2. **Tuple vs list index.** `a.at[(1, 2)]` works; `a.at[[1, 2]]` does
   something different (fancy indexing into a 1-d array). Clausal
   terms distinguish tuples from lists by wrapper — check that
   `_deep_deref` preserves tuple vs list correctly, or convert both to
   tuples for safety.

3. **`at_get` under `jit`.** `a.at[idx].get()` composes with `jit`;
   plain `a[idx]` may not in some cases (tracing of dynamic indices).
   Phase 12 will revisit when wrapping `jit`.

4. **Slice indices deferred.** Users needing slice updates use
   `lax.dynamic_update_slice` directly. Consider a `dynamic_slice_set`
   predicate in a later phase for slice-as-a-tuple indexing.
