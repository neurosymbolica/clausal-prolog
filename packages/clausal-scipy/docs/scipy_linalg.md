# scipy.linalg — Linear Algebra

The `scipy_linalg` module wraps [`scipy.linalg`](https://docs.scipy.org/doc/scipy/reference/linalg.html) as Clausal predicates. Inputs and outputs are NumPy arrays (or Python scalars where appropriate).

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:import_ex2"
```

---

## Tiers

Predicates fall into two tiers depending on whether the result is a single array or a named collection of arrays:

**Tier 1 — single result**: RESULT is unified with the output array (or scalar).

**Tier 2 — result dict**: RESULT is unified with a Python dict. Use `ResultGet(RESULT, FIELD, VALUE)` to extract individual fields by name.

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:tiers"
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
| `scipy.linalg.expm` | `MatrixExpLog` forward |
| `scipy.linalg.logm` | `MatrixExpLog` backward |
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

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:linear_system_solvers"
```

Example:

```clausal
SolveSystem(A, B, X) <- (
    Solve(A, B, X),
    ++print(f"Solution: {X}")
)
```

---

### Matrix decompositions

All decomposition predicates are **bidirectional**: the forward direction decomposes `A` into factor dict `R`; the backward direction recomposes `A` from `R` using plain numpy.

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:matrix_decompositions"
```

Example — extract singular values:

```clausal
LargestSingularValue(A, S1) <- (
    SingularValueDecompose(A, DECOMP),
    ResultGet(DECOMP, 's', S),
    S1 is ++S[0]
)
```

---

### Matrix functions

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:matrix_functions"
```

Example — check positive definiteness via eigenvalues:

```clausal
IsPositiveDefinite(A) <- (
    EigenDecomposeHermitian(A, D),
    ResultGet(D, 'eigenvalues', VALS),
    ++all(v > 0 for v in VALS)
)
```

---

### Two-step factorisations

when solving multiple systems with the same matrix, factorising once and reusing is more efficient than calling `Solve` repeatedly.

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:two_step_factorisations"
```

Example — solve multiple right-hand sides efficiently:

```clausal
SolveMultiple(A, RHS_LIST, SOLUTIONS) <- (
    LuFactor(A, LU),
    maplist([B]>>(LuSolve(LU, B, X), X), RHS_LIST, SOLUTIONS)
)
```

---

### ResultGet

```clausal
--8<-- "tests/fixtures/docs/scipy_linalg_sigs.txt:resultget"
```

---

## Complete example — principal component analysis

```clausal
-import_from(scipy_linalg, [SingularValueDecompose, ResultGet])

# Compute the top-K principal components of a data matrix X
# (rows = observations, columns = features; X should be mean-centred)
PrincipalComponents(X, K, COMPONENTS) <- (
    SingularValueDecompose(X, SVD),
    ResultGet(SVD, 'vh', VH),
    COMPONENTS is ++VH[:K]
)

ExplainedVariance(X, K, RATIO) <- (
    SingularValueDecompose(X, SVD),
    ResultGet(SVD, 's', S),
    TOTAL is ++float((S ** 2).sum()),
    TOP_K is ++float((S[:K] ** 2).sum()),
    RATIO is TOP_K / TOTAL
)
```

---

## Notes

- All array inputs are passed to scipy without copying; avoid mutating them after the call.
- Tier 2 result dicts are plain Python dicts — they can be passed to [`++` escapes](python_integration.md) for further NumPy processing.
- `EigenDecompose` may return complex eigenvalues for non-symmetric matrices; use `++(vals.real)` to extract real parts when appropriate.
- `MatrixExpLog` (logm direction) and `MatrixSquareRoot` may return complex results even for real inputs; wrap with `++(result.real)` if only the real part is needed.
- Predicates fail (no solution) when `ResultGet` cannot find the field, or when a bound `RESULT` does not unify with the computed value; scipy exceptions propagate as Python exceptions.

---

*See also: [scipy.sparse](scipy_sparse.md) — sparse matrix solvers.*
