# Phase 4 — Linear Algebra

Pure linear algebra via `jax.numpy.linalg`. Largely the same shape as
`torch` Phase 4 and `scipy_linalg.py` — different array type.

**File to modify:** `clausal/modules/py/jax.py`

**Depends on:** Phase 1 — `_pure()`, `_pred()`, `_jnp_mod()`.

**Overlap:** `scipy_linalg.py` (numpy arrays, TitleCase predicates),
`py.torch` linalg (tensors, lowercase). The JAX versions use lowercase
following JAX's own naming.

---

## Predicates

| Name | Arity | Modes | Bijective? | Description |
|---|---|---|---|---|
| `det` | `/2` | `(+A, -D)` | no | Determinant |
| `slogdet` | `/2` | `(+A, -SIGN_LOGDET)` | no | `(sign, log\|det\|)` tuple |
| `inv` | `/2` | `(+A, -B)` | self-inverse: `inv(inv(A)) ≈ A` | Matrix inverse |
| `solve` | `/3` | `(+A, +B, -X)` | partial | Solve `A @ X == B` |
| `svd` | `/2` | `(+A, -USV)` | yes — `U @ diag(S) @ Vh` | Singular value decomposition; returns `(U, S, Vh)` |
| `eig` | `/2` | `(+A, -LV)` | partial | Eigendecomposition; `(eigenvalues, eigenvectors)` |
| `eigh` | `/2` | `(+A, -LV)` | yes for Hermitian | Symmetric/Hermitian eig |
| `eigvals` | `/2` | `(+A, -L)` | no | Eigenvalues only |
| `eigvalsh` | `/2` | `(+A, -L)` | no | Hermitian eigenvalues only |
| `cholesky` | `/2` | `(+A, -L)` | yes — `A = L @ L.T` | Cholesky |
| `qr` | `/2` | `(+A, -QR)` | yes — `A = Q @ R` | QR decomposition |
| `lstsq` | `/3` | `(+A, +B, -RES)` | no | Least squares; result tuple |
| `norm` | `/2, /3` | `(+A, -N)`, `(+A, +ORD, -N)` | no | Matrix/vector norm |
| `matrix_rank` | `/2` | `(+A, -R)` | no | Rank |
| `pinv` | `/2` | `(+A, -B)` | pseudo-inverse | Moore-Penrose pseudoinverse |
| `matrix_power` | `/3` | `(+A, +N, -B)` | partial | `A ** N` |
| `cross` | `/3` | `(+A, +B, -C)` | no | Cross product |

`dot/3` is intentionally **not** in this phase — JAX exposes it as
`jnp.dot` (top-level), not `jnp.linalg.dot`, and Phase 1 already wraps
it under Array Math.

Decomposition results are tuples decomposed with `is`:

```clausal
svd(A, RESULT),
RESULT is (U, S, VH)
```

---

## Context and Reference Patterns

All operations live in `jax.numpy.linalg`. Follow the PyTorch Phase 4
pattern — `_pure()` + `_pred()`:

```python
def _jla():
    return _jnp_mod().linalg

det = _pred("det",
    (2, _pure(lambda a: _jla().det(a))),
)

inv = _pred("inv",
    (2, _pure(lambda a: _jla().inv(a))),
)
```

### Decompositions returning tuples

JAX's `linalg.svd` returns a `NamedTuple` `SVDResult(U, S, Vh)`. Convert
to a plain tuple for Clausal:

```python
svd = _pred("svd",
    (2, _pure(lambda a: tuple(_jla().svd(a)))),
)

qr = _pred("qr",
    (2, _pure(lambda a: tuple(_jla().qr(a)))),
)

eig = _pred("eig",
    (2, _pure(lambda a: tuple(_jla().eig(a)))),
)
```

Same as PyTorch Phase 4 Issue 2 (`NamedTuple` -> plain `tuple`).

### `norm` with optional `ord`

```python
norm = _pred("norm",
    (2, _pure(lambda a: _jla().norm(a))),
    (3, _pure(lambda a, ord: _jla().norm(a, ord=ord))),
)
```

### `slogdet` returns a tuple

Sign and log-abs-det. Return as a 2-tuple.

### `solve` batching

`jnp.linalg.solve(A, B)` supports batched inputs. The wrapper is
transparent — if `A` is `(..., N, N)` and `B` is `(..., N)`, it works.

---

## Example Usage

```clausal
-import_from(py.jax, [array, zeros, eye, shape, array_list,
                      matmul, add,
                      det, inv, solve, svd, eig, eigh, cholesky,
                      qr, norm, pinv])

Test("determinant of 2x2") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    det(A, D),
    array_list(D, V),
    V > -2.1,
    V < -1.9
)

Test("inv is self-inverse") <- (
    array([[2.0, 1.0], [1.0, 3.0]], A),
    inv(A, B),
    inv(B, C),
    # C should be close to A; compare via matmul
    matmul(A, B, I),
    # I should be close to eye(2)
    shape(I, [2, 2])
)

Test("solve linear system") <- (
    eye(2, A),
    array([3.0, 4.0], B),
    solve(A, B, X),
    array_list(X, [3.0, 4.0])
)

Test("svd decomposition shapes") <- (
    array([[1.0, 2.0], [3.0, 4.0]], A),
    svd(A, RESULT),
    RESULT is (U, S, VH),
    shape(U, [2, 2]),
    shape(S, [2]),
    shape(VH, [2, 2])
)

Test("qr decomposition") <- (
    array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], A),
    qr(A, RESULT),
    RESULT is (Q, R),
    shape(Q, [3, 2]),
    shape(R, [2, 2])
)

Test("cholesky and reconstruct") <- (
    array([[4.0, 2.0], [2.0, 3.0]], A),
    cholesky(A, L),
    shape(L, [2, 2])
)

Test("norm default (frobenius)") <- (
    array([[3.0, 4.0]], A),
    norm(A, N),
    array_list(N, V),
    V > 4.9,
    V < 5.1
)

Test("eigh on symmetric") <- (
    array([[2.0, 1.0], [1.0, 2.0]], A),
    eigh(A, RESULT),
    RESULT is (EIGVALS, EIGVECS),
    shape(EIGVALS, [2]),
    shape(EIGVECS, [2, 2])
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_linalg_tests.clausal`):
- Each predicate with shape verification
- `inv(inv(A)) ≈ A` round-trip
- SVD shape check (both `full_matrices=True` and rectangular)
- `cholesky` reconstruct: `L @ L.T ≈ A`
- `qr` reconstruct: `Q @ R ≈ A`
- `solve` with identity produces B
- `eigh` on symmetric matrix (real eigenvalues)
- Singular matrix handling — `inv` fails gracefully (predicate failure,
  not crash)
- `norm` with various `ord` values: `2`, `'fro'`, `inf`, `-1`

**Python unit tests:** None beyond shape/type checks.

---

## Docs

Update `docs/jax.md` with a Linear Algebra section. Mirror the PyTorch
docs structure (`docs/torch.md` linalg section). All examples backed by
`.clausal` tests.

---

## Issues

Implementation completed — 38 integration tests green. Notes from the pass:

- **`jnp.linalg.dot` does not exist.** JAX keeps `dot` at `jnp.dot`,
  wrapped by Phase 1's Array Math. The predicate catalogue above now
  calls this out explicitly.
- **`matrix_rank` wraps its result in `int(...)`** so callers can use
  `R == 3` directly instead of `array_list(R, V), V == 3`. Shapeless
  scalars work better as Python ints at the Clausal surface.
- **`lstsq` passes `rcond=None`** explicitly. Without it JAX emits a
  `FutureWarning` about changing default behaviour; pinning it here
  gives deterministic output.
- **`abs` import collision in test fixtures.** Importing `abs` from
  `py.jax` shadows Python's builtin inside `++()` escapes. The fixture
  avoids the issue entirely by using explicit `DIFF > -TOL, DIFF < TOL`
  bounds rather than `++(abs(...))`, and by not importing `abs` in the
  linalg fixture at all.
- **`eig` / `eigvals` return complex.** Even for real-eigenvalue
  inputs, dtype is `complex64`. Tests extract the real part with
  `++(E.real)` before numeric comparison. Documented in `docs/jax.md`
  with a concrete pull-`.real` example.
- **Singular-matrix handling.** `inv` of a singular matrix returns an
  array full of `inf`/`nan` rather than raising. Fixture test
  `inv of singular matrix succeeds with non-finite values` verifies
  the first cell is non-finite via `math.isfinite` in a `++()` escape.
  Callers needing a hard pre-check should use `matrix_rank/2`.
- **`norm` with non-integer `ord`.** Works for `'fro'` and `inf` —
  implementation passes `ord=ord_` through unchanged (no `int(...)`
  coercion). Fixture pins both.

Known items to validate:

1. **`svd` `full_matrices` default.** Same concern as PyTorch Phase 4
   Issue 1 — JAX defaults to `full_matrices=True`. For an `(m, n)` matrix
   with `m < n`, `Vh` is `(n, n)`. Tests must match.

2. **`eig` returns complex.** Even for real inputs with real
   eigenvalues, `eig` returns complex arrays. Use `eigh` for real
   symmetric matrices.

3. **`matrix_power/3` for negative N.** Requires invertibility; fail
   gracefully if singular.

4. **`dot/3` location.** JAX has both `jnp.dot` (top-level) and
   `jnp.linalg` (no `dot`). Place `dot/3` in Phase 1 math. `cross/3`
   follows PyTorch's precedent — `jnp.cross` is top-level.

5. **Numerical tolerance in tests.** JAX default precision is `float32`.
   Roundtrip tests (`inv(inv(A)) ≈ A`) must use a loose tolerance or
   explicit `float64` via `{"dtype": float64}`. Consider enabling x64
   mode only for tests that need it, via `jax.config.update("jax_enable_x64", True)`
   at test setup time — but this is global state, so better to pass
   `dtype=float64` in creation.
