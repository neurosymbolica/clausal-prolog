# Phase 15 — Statistics and Selection

Statistical reductions and selection/sorting. Mirrors PyTorch Phase 14.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1.

---

## Predicates

### Statistics

| Name | Arity | Modes | Description |
|---|---|---|---|
| `median` | `/2, /3` | `(+A, -R)`, `(+A, +AXIS, -R)` | |
| `std` | `/2, /3` | | |
| `var` | `/2, /3` | | |
| `percentile` | `/3, /4` | `(+A, +Q, -R)`, `(+A, +Q, +AXIS, -R)` | |
| `quantile` | `/3, /4` | | |
| `cov` | `/2` | `(+A, -R)` | Covariance matrix |
| `corrcoef` | `/2` | `(+A, -R)` | Correlation coefficient |

### Selection and sorting

| Name | Arity | Modes | Description |
|---|---|---|---|
| `argmin` | `/2, /3` | `(+A, -I)`, `(+A, +AXIS, -I)` | |
| `argmax` | `/2, /3` | | |
| `sort` | `/2, /3` | `(+A, -R)`, `(+A, +AXIS, -R)` | Returns sorted array only (values) |
| `argsort` | `/2, /3` | | |
| `topk` | `/3, /4` | `(+A, +K, -RES)`, `(+A, +K, +AXIS, -RES)` | `jax.lax.top_k` — returns `(values, indices)` tuple |
| `nonzero` | `/2` | `(+A, -IS)` | Indices of nonzero elements |
| `unique` | `/2` | `(+A, -R)` | Unique elements (sorted) |
| `argpartition` | `/3` | `(+A, +KTH, -R)` | |

---

## Context

All `_pure()`:

```python
median = _pred("median",
    (2, _pure(lambda a: _jnp_mod().median(a))),
    (3, _pure(lambda a, axis: _jnp_mod().median(a, axis=int(axis)))),
)

argmax = _pred("argmax",
    (2, _pure(lambda a: _jnp_mod().argmax(a))),
    (3, _pure(lambda a, axis: _jnp_mod().argmax(a, axis=int(axis)))),
)
```

### `topk` — uses `jax.lax.top_k`

```python
def _lax():
    _ensure_jax()
    import jax.lax as _m
    return _m

topk = _pred("topk",
    (3, _pure(lambda a, k: tuple(_lax().top_k(a, int(k))))),
    # No axis variant — lax.top_k only supports last axis.
    # Users transpose if needed.
)
```

### `unique` caveat

`jnp.unique` returns variable-shaped output, not jit-safe. Document.

---

## Example Usage

```clausal
-import_from(py.jax, [array, array_list, shape,
                       median, std, var, argmin, argmax,
                       sort, argsort, topk, nonzero, unique])

Test("median") <- (
    array([1.0, 2.0, 3.0, 4.0, 5.0], A),
    median(A, M),
    array_list(M, 3.0)
)

Test("argmax") <- (
    array([1, 3, 2, 5, 4], A),
    argmax(A, I),
    array_list(I, 3)
)

Test("sort") <- (
    array([3, 1, 2], A),
    sort(A, R),
    array_list(R, [1, 2, 3])
)

Test("argsort") <- (
    array([3, 1, 2], A),
    argsort(A, I),
    array_list(I, [1, 2, 0])
)

Test("topk") <- (
    array([1.0, 5.0, 3.0, 2.0, 4.0], A),
    topk(A, 2, RES),
    RES is (VS, IS),
    array_list(VS, [5.0, 4.0]),
    array_list(IS, [1, 4])
)

Test("unique") <- (
    array([1, 2, 1, 3, 2, 3], A),
    unique(A, U),
    array_list(U, [1, 2, 3])
)

Test("nonzero") <- (
    array([0, 1, 0, 2, 3], A),
    nonzero(A, NZ),
    NZ is (I,),
    array_list(I, [1, 3, 4])
)
```

---

## Tests

`tests/fixtures/jax_stats_tests.clausal`:
- Each statistical reduction with known values
- `argmin`/`argmax` with and without axis
- `sort`/`argsort` consistency: `sort(A, R), argsort(A, I), take_along_axis(A, I) == R`
- `topk` tuple decomposition
- `unique` and `nonzero` basic cases

---

## Docs

Update `docs/jax.md`.

---

## Issues

_To be populated during implementation._

1. **`nonzero` return type.** `jnp.nonzero(a)` returns a tuple of
   index arrays (one per dim). Even for 1-d input it's a 1-tuple — tests
   decompose with `NZ is (I,)`.
2. **`sort` only returns values.** For values+indices, use
   `argsort` then `take`.
3. **`topk` axis limitation.** Only last axis supported natively.
