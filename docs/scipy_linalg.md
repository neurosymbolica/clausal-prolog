# scipy.linalg — Linear Algebra

The `scipy_linalg` module wraps [`scipy.linalg`](https://docs.scipy.org/doc/scipy/reference/linalg.html) as Clausal predicates. Inputs and outputs are NumPy arrays (or Python scalars where appropriate).

---

## Import

```
-import_from(scipy_linalg, [Solve, SingularValueDecompose, Inverse, ...])
```

Or via the canonical `py.*` path:

```
-import_from(py.scipy_linalg, [Solve, SingularValueDecompose, ...])
```

---

## Tiers

Predicates fall into two tiers depending on whether the result is a single array or a named collection of arrays:

**Tier 1 — single result**: RESULT is unified with the output array (or scalar).

**Tier 2 — result dict**: RESULT is unified with a Python dict. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields by name.

```
SingularValueDecompose(A, RESULT),
ResultGet(RESULT, 'u', U),
ResultGet(RESULT, 's', S),
ResultGet(RESULT, 'vh', Vh).
```

---

## Naming conventions

Predicate names use full English words; scipy's terse abbreviations are expanded:

| scipy function | Clausal predicate |
|---|---|
| `scipy.linalg.solve` | `Solve` |
| `scipy.linalg.lstsq` | `LeastSquares` |
| `scipy.linalg.solve_triangular` | `SolveTriangular` |
| `scipy.linalg.lu` | `LuDecompose` |
| `scipy.linalg.qr` | `QrDecompose` |
| `scipy.linalg.svd` | `SingularValueDecompose` |
| `scipy.linalg.cholesky` | `Cholesky` |
| `scipy.linalg.eig` | `EigenDecompose` |
| `scipy.linalg.eigh` | `EigenDecomposeHermitian` |
| `scipy.linalg.schur` | `Schur` |
| `scipy.linalg.inv` | `Inverse` |
| `scipy.linalg.pinv` | `PseudoInverse` |
| `scipy.linalg.det` | `Determinant` |
| `scipy.linalg.norm` | `Norm` |
| `scipy.linalg.expm` | `MatrixExponential` |
| `scipy.linalg.logm` | `MatrixLogarithm` |
| `scipy.linalg.sqrtm` | `MatrixSquareRoot` |
| `scipy.linalg.funm` | `MatrixFunction` |
| `scipy.linalg.lu_factor` | `LuFactor` |
| `scipy.linalg.lu_solve` | `LuSolve` |
| `scipy.linalg.cho_factor` | `CholeskyFactor` |
| `scipy.linalg.cho_solve` | `CholeskySolve` |

LU and QR are kept as-is — they are the standard letter names for the matrix factors, not abbreviations of words.

---

## Predicate catalogue

### Linear system solvers

```
Solve(A, B, RESULT)
    RESULT = X such that A @ X = B

Solve(A, B, ASSUME_A, RESULT)
    ASSUME_A: 'gen' (default), 'sym', 'her', or 'pos'
    Allows faster solvers when the matrix structure is known

LeastSquares(A, B, RESULT)
    RESULT: dict {x, residuals, rank, s}
    Minimises ||A @ x − b||₂; use ResultGet to extract fields

SolveTriangular(A, B, RESULT)
    A must be upper triangular (default)

SolveTriangular(A, B, LOWER, RESULT)
    LOWER=True: treat A as lower triangular
```

Example:

```
SolveSystem(A_, B_, X_) <- (
    Solve(A_, B_, X_) and
    ++print(f"Solution: {X_}")
)
```

---

### Matrix decompositions

```
LuDecompose(A, RESULT)
    RESULT: dict {p, l, u}   — A = P @ L @ U

QrDecompose(A, RESULT)
    RESULT: dict {q, r}      — A = Q @ R

SingularValueDecompose(A, RESULT)
    RESULT: dict {u, s, vh}  — A = U @ diag(s) @ Vh

Cholesky(A, RESULT)
    RESULT: upper triangular factor U such that U.T @ U = A
    A must be symmetric positive definite

Cholesky(A, LOWER, RESULT)
    LOWER=True: returns lower triangular L such that L @ L.T = A

EigenDecompose(A, RESULT)
    RESULT: dict {eigenvalues, eigenvectors}
    General (non-symmetric) matrix; eigenvalues may be complex

EigenDecomposeHermitian(A, RESULT)
    RESULT: dict {eigenvalues, eigenvectors}
    Symmetric/Hermitian A; eigenvalues are real, eigenvectors orthonormal

Schur(A, RESULT)
    RESULT: dict {t, z}      — A = Z @ T @ Z.T (real Schur form)

Schur(A, OUTPUT, RESULT)
    OUTPUT: 'real' (default) or 'complex'
```

Example — extract singular values:

```
LargestSingularValue(A_, S1_) <- (
    SingularValueDecompose(A_, DECOMP_) and
    ResultGet(DECOMP_, 's', S_) and
    S1_ is ++S_[0]
)
```

---

### Matrix functions

```
Inverse(A, RESULT)
    RESULT = A⁻¹

PseudoInverse(A, RESULT)
    RESULT = A⁺   # Moore-Penrose pseudoinverse; works for non-square A

Determinant(A, RESULT)
    RESULT = det(A)

Norm(A, RESULT)
    RESULT = ||A||   # Frobenius norm for matrices, Euclidean for vectors

Norm(A, ORD, RESULT)
    ORD: None (default), 'fro', 'nuc', 1, -1, 2, -2, inf, -inf

MatrixExponential(A, RESULT)
    RESULT = e^A   # matrix exponential (not element-wise)

MatrixLogarithm(A, RESULT)
    RESULT = log(A)   # matrix logarithm; inverse of MatrixExponential

MatrixSquareRoot(A, RESULT)
    RESULT = A^{1/2}   # matrix square root; RESULT @ RESULT ≈ A

MatrixFunction(A, FUNC, RESULT)
    RESULT = f(A) where FUNC is a Python callable applied via eigendecomposition
    Example: MatrixFunction(A, np.exp, RESULT) is equivalent to MatrixExponential(A, RESULT)
```

Example — check positive definiteness via eigenvalues:

```
IsPositiveDefinite(A_) <- (
    EigenDecomposeHermitian(A_, D_) and
    ResultGet(D_, 'eigenvalues', VALS_) and
    ++all(v > 0 for v in VALS_)
)
```

---

### Two-step factorisations

When solving multiple systems with the same matrix, factorising once and reusing is more efficient than calling `Solve` repeatedly.

```
LuFactor(A, RESULT)
    RESULT: opaque factorisation record (passed to LuSolve)

LuSolve(LU_PIV, B, RESULT)
    LU_PIV: result from LuFactor
    RESULT = X such that A @ X = B

CholeskyFactor(A, RESULT)
    RESULT: opaque factorisation record (passed to CholeskySolve)
    A must be symmetric positive definite

CholeskySolve(C_LOWER, B, RESULT)
    C_LOWER: result from CholeskyFactor
    RESULT = X such that A @ X = B
```

Example — solve multiple right-hand sides efficiently:

```
SolveMultiple(A_, RHS_LIST_, SOLUTIONS_) <- (
    LuFactor(A_, LU_) and
    MapList([B_]>>(LuSolve(LU_, B_, X_), X_), RHS_LIST_, SOLUTIONS_)
)
```

---

### ResultGet

```
ResultGet(RESULT, FIELD, VALUE)
    Extract a named field from a Tier 2 result dict.
    RESULT: a dict returned by a Tier 2 predicate
    FIELD:  a ground string key (e.g. 'x', 'eigenvalues', 'u')
    VALUE:  unified with RESULT[FIELD]
    Fails if RESULT is not a dict, FIELD is not a string, or the key is absent.
```

---

## Complete example — principal component analysis

```
-import_from(scipy_linalg, [SingularValueDecompose, ResultGet])

# Compute the top-K principal components of a data matrix X
# (rows = observations, columns = features; X should be mean-centred)
PrincipalComponents(X_, K_, COMPONENTS_) <- (
    SingularValueDecompose(X_, SVD_) and
    ResultGet(SVD_, 'vh', Vh_) and
    COMPONENTS_ is ++Vh_[:K_]
)

ExplainedVariance(X_, K_, RATIO_) <- (
    SingularValueDecompose(X_, SVD_) and
    ResultGet(SVD_, 's', S_) and
    TOTAL_ is ++float((S_ ** 2).sum()) and
    TOP_K_ is ++float((S_[:K_] ** 2).sum()) and
    RATIO_ is TOP_K_ / TOTAL_
)
```

---

## Notes

- All array inputs are passed to scipy without copying; avoid mutating them after the call.
- Tier 2 result dicts are plain Python dicts — they can be passed to `++` escapes for further NumPy processing.
- `EigenDecompose` may return complex eigenvalues for non-symmetric matrices; use `++(vals.real)` to extract real parts when appropriate.
- `MatrixLogarithm` and `MatrixSquareRoot` may return complex results even for real inputs; wrap with `++(result.real)` if only the real part is needed.
- Predicates fail (no solution) when `ResultGet` cannot find the field, or when a bound `RESULT` does not unify with the computed value; scipy exceptions propagate as Python exceptions.
