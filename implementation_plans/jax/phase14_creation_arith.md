# Phase 14 — Creation Variants and Arithmetic Gaps

Fills in common creation variants and basic arithmetic ops left out of
Phase 1. Mirrors PyTorch Phase 13.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1.

---

## Predicates

### Creation variants

| Name | Arity | Modes | Description |
|---|---|---|---|
| `zeros_like` | `/2` | `(+A, -R)` | |
| `ones_like` | `/2` | | |
| `full_like` | `/3` | `(+A, +VALUE, -R)` | |
| `empty` | `/2, /3` | `(+SHAPE, -A)`, `(+SHAPE, +OPTS, -A)` | JAX's `empty` is really `zeros` — document |
| `logspace` | `/4, /5` | `(+START, +END, +STEPS, -A)` | |
| `geomspace` | `/4, /5` | | |
| `meshgrid` | `/2, /3` | `(+ARRS, -MESH)` | |
| `diag` | `/2, /3` | `(+A, -R)`, `(+A, +K, -R)` | Create diag or extract |
| `identity` | `/2, /3` | `(+N, -A)` | Alias for `eye` |

### Arithmetic gaps

| Name | Arity | Modes | Description |
|---|---|---|---|
| `sub` | `/3` | `(+A, +B, -C)` | Subtract |
| `div` | `/3` | | True divide |
| `floor_div` | `/3` | | |
| `mod` | `/3` | | Remainder |
| `neg` | `/2` | `(+A, -R)` | Negate |
| `reciprocal` | `/2` | | |

---

## Context

Mostly `_pure()` one-liners:

```python
zeros_like = _pred("zeros_like",
    (2, _pure(lambda a: _jnp_mod().zeros_like(a))),
)

sub = _pred("sub",
    (3, _pure(lambda a, b: _jnp_mod().subtract(a, b))),
)
```

### `empty` caveat

`jnp.empty(shape)` actually returns zeros (JAX doesn't expose
uninitialised memory). Note in docs; keep the predicate for API
symmetry with NumPy/PyTorch.

---

## Example Usage

```clausal
-import_from(py.jax, [array, ones, zeros_like, ones_like, full_like,
                      logspace, meshgrid, diag,
                      sub, div, neg, shape, array_list])

Test("zeros_like") <- (
    ones([3, 4], A),
    zeros_like(A, B),
    shape(B, [3, 4]),
    array_list(B, [[0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]])
)

Test("sub") <- (
    array([10, 20, 30], A),
    array([1, 2, 3], B),
    sub(A, B, C),
    array_list(C, [9, 18, 27])
)

Test("neg") <- (
    array([1, -2, 3], A),
    neg(A, R),
    array_list(R, [-1, 2, -3])
)

Test("logspace") <- (
    logspace(0.0, 2.0, 3, A),
    array_list(A, [1.0, 10.0, 100.0])
)

Test("diag create") <- (
    array([1, 2, 3], A),
    diag(A, R),
    shape(R, [3, 3])
)

Test("diag extract") <- (
    array([[1, 2], [3, 4]], A),
    diag(A, R),
    array_list(R, [1, 4])
)
```

---

## Tests

`tests/fixtures/jax_creation2_tests.clausal`:
- Every predicate with value or shape spot-check
- `diag` in both modes (create and extract)

---

## Docs

Extend `docs/jax.md` creation section.

---

## Issues

_To be populated during implementation._

1. `empty` doesn't return uninitialised memory — document.
2. `meshgrid` indexing mode (`'xy'` vs `'ij'`) — pass via opts.
