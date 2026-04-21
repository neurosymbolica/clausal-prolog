# Phase 6 — Comparisons, Logic, and Selection

Element-wise comparison, logical operations, and conditional selection.
Follows PyTorch Phase 6 closely — JAX's API is nearly identical (both
are NumPy-shaped), so predicate names and semantics port directly.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1.

---

## Predicates

### Comparisons

| Name | Arity | Modes | Description |
|---|---|---|---|
| `eq` | `/3` | `(+A, +B, -C)` | Element-wise `==` → bool array |
| `ne` | `/3` | | `!=` |
| `gt` | `/3` | | `>` |
| `lt` | `/3` | | `<` |
| `ge` | `/3` | | `>=` |
| `le` | `/3` | | `<=` |
| `equal` | `/2` | `(+A, +B)` | Check: all elements equal |
| `allclose` | `/2, /4` | `(+A, +B)`, `(+A, +B, +ATOL, +RTOL)` | Check: approximately equal |
| `array_equal` | `/2` | `(+A, +B)` | Check: same shape and values |

### Logic

| Name | Arity | Modes | Description |
|---|---|---|---|
| `logical_and` | `/3` | `(+A, +B, -C)` | |
| `logical_or` | `/3` | | |
| `logical_not` | `/2` | `(+A, -B)` | |
| `logical_xor` | `/3` | | |
| `any` | `/1, /2` | `(+A)`, `(+A, +AXIS)` | Check: any element true |
| `all` | `/1, /2` | | Check: all elements true |

### Selection

| Name | Arity | Modes | Description |
|---|---|---|---|
| `where` | `/4` | `(+COND, +X, +Y, -R)` | Element-wise `jnp.where(cond, x, y)` |
| `masked_select` | `/3` | `(+A, +MASK, -R)` | Select elements where mask is true; returns 1-d |
| `take` | `/4` | `(+A, +INDICES, +AXIS, -R)` | Gather along an axis |
| `put_along_axis` | `/5` | `(+A, +INDICES, +VALUES, +AXIS, -R)` | Scatter along an axis (functional) |

---

## Context and Reference Patterns

All predicates are Tier 1 pure. Use `_pure()`.

### Comparison predicates return bool arrays

```python
eq = _pred("eq",
    (3, _pure(lambda a, b: _jnp_mod().equal(a, b))),
)
gt = _pred("gt",
    (3, _pure(lambda a, b: _jnp_mod().greater(a, b))),
)
```

### Check-style predicates (`equal/2`, `allclose/2`, `any/1`, `all/1`)

These return Python bools, so they're wrapped as `_check_2` /
`_check_bool` dispatchers — the exact helpers `torch.py` already has
at lines 421-477. Reuse:

```python
equal = _pred("equal",
    (2, _check_2(lambda a, b: bool(_jnp_mod().array_equal(a, b)))),
)

allclose = _pred("allclose",
    (2, _check_2(lambda a, b: bool(_jnp_mod().allclose(a, b)))),
    (4, _check_4(lambda a, b, atol, rtol: bool(_jnp_mod().allclose(a, b, atol=atol, rtol=rtol)))),
)
```

### `where` and `masked_select`

```python
where = _pred("where",
    (4, _pure(lambda cond, x, y: _jnp_mod().where(cond, x, y))),
)
```

`masked_select` in JAX is `arr[mask]`, which isn't jit-safe because
output size is dynamic. Wrap the eager form:

```python
masked_select = _pred("masked_select",
    (3, _pure(lambda a, mask: a[mask])),
)
```

Document that this can't be JITted. Users who need a jit-safe version
should use `jnp.where(mask, a, 0.0)` directly.

---

## Example Usage

```clausal
-import_from(py.jax, [array, ones, zeros, shape, array_list,
                      eq, ne, gt, lt, where, masked_select,
                      logical_and, logical_or, logical_not,
                      any, all, allclose, array_equal])

Test("eq elementwise") <- (
    array([1, 2, 3], A),
    array([1, 5, 3], B),
    eq(A, B, C),
    array_list(C, [True, False, True])
)

Test("gt") <- (
    array([1.0, 2.0, 3.0], A),
    array([2.0, 2.0, 2.0], B),
    gt(A, B, C),
    array_list(C, [False, False, True])
)

Test("allclose within tolerance") <- (
    array([1.0, 2.0], A),
    array([1.0000001, 2.0], B),
    allclose(A, B)
)

Test("allclose fails outside tolerance") <- (
    array([1.0, 2.0], A),
    array([1.1, 2.0], B),
    not(allclose(A, B))
)

Test("logical_and") <- (
    array([True, True, False], A),
    array([True, False, True], B),
    logical_and(A, B, C),
    array_list(C, [True, False, False])
)

Test("any true") <- (
    array([False, False, True], A),
    any(A)
)

Test("all fails with false") <- (
    array([True, False, True], A),
    not(all(A))
)

Test("where selects") <- (
    array([True, False, True], COND),
    array([10, 20, 30], X),
    array([1, 2, 3], Y),
    where(COND, X, Y, R),
    array_list(R, [10, 2, 30])
)

Test("masked_select") <- (
    array([1, 2, 3, 4, 5], A),
    array([True, False, True, False, True], MASK),
    masked_select(A, MASK, R),
    array_list(R, [1, 3, 5])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_comparison_tests.clausal`):
- Every comparison with mixed true/false outcomes
- Check predicates with success and failure via `not(...)`
- `where` with scalar and array branches
- `masked_select` with non-contiguous masks
- `any`/`all` with and without axis

---

## Docs

Update `docs/jax.md` with Comparisons and Selection section. Mirror
PyTorch's docs. Note `masked_select` jit-safety caveat.

---

## Issues

_To be populated during implementation._

1. **`masked_select` under `jit`.** Not jit-safe. Document in Phase 12
   or here.
2. **Bool array decomposition via `array_list`.** JAX bool arrays
   tolist to Python bools. Test.
3. **Broadcasting semantics in `where`.** Conditions, X, and Y must
   broadcast. JAX raises on mismatch; we translate to predicate
   failure via `_pure`.
