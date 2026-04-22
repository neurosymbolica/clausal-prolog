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

### 1. `empty` returns zeros, not uninitialised memory — NOTED

`jnp.empty(shape)` allocates zeros because JAX cannot expose
uninitialised accelerator memory safely. Documented in both `jax.py`
and `docs/jax.md`; users who care about the distinction should prefer
`zeros`. Kept for NumPy/PyTorch API symmetry.

### 2. `meshgrid` indexing mode via opts — RESOLVED

`indexing` ("xy" default vs "ij" for matrix layout) is passed through
the `/3` opts dict: `meshgrid(ARRS, {"indexing": "ij"}, MESH)`.
Predicate returns a plain Python list so `[XX, YY]` pattern-matching
works.

### 3. `diag` is input-polymorphic, not bijective — NOTED

Mirrors the PyTorch Phase 13 finding: with a 1-D input `diag` creates
a 2-D diagonal matrix; with a 2-D input it extracts the diagonal.
Wrapped with `_pure` — forward-only. Users bind the input and read the
output; they can't recover the input from the output. The plan's
"multi-mode" wording refers to this input polymorphism, not to
Clausal's bidirectional mode dispatch.

### 4. `logspace` / `geomspace` are float32 by default — NOTED

Like every other JAX creation op, these produce float32 unless x64 is
enabled. Tests use `allclose/4` with an explicit tolerance (≈1e-3) to
accommodate drift in `geomspace(1, 1000, 4)` (middle samples land at
10.000003 / 100.00005 on float32). Callers who need exact log-spaced
integers should enable x64 first.

### 5. `div` always true-divides — NOTED

Matches `jnp.divide`. Integer operands promote to float32, so
`div([7, 5], [2, 2], C)` gives `[3.5, 2.5]`. Use `floor_div` for the
integer truncation behaviour.
