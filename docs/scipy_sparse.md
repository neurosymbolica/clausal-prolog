# scipy.sparse — Sparse Matrices and Sparse Linear Algebra

Provides sparse matrix construction, conversion, inspection, and linear algebra
from `scipy.sparse` and `scipy.sparse.linalg` as [importable](import.md) clausal predicates.

## Import

```clausal
# skip
-import_from(scipy_sparse, [MakeCSR, MakeCSC, MakeCOO, MakeDiagonals, MakeEye, ...])
```

or via the canonical `py.*` path:

```clausal
# skip
-import_from(py.scipy_sparse, [MakeCSR, ...])
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 3 — handle | `MakeCSR`, `MakeCSC`, `MakeCOO`, `MakeDiagonals`, `MakeEye` | Sparse matrix construction |
| 3 — handle | `ToDense`, `FromDense` | Dense/sparse conversions |
| 3 — handle | `Shape`, `NonzeroCount` | Inspection |
| linalg | `Solve`, `EigenDecomposeHermitian`, `SingularValueDecompose` | Sparse linear algebra |
| lifecycle | `Free` | Release any handle |

---

## Tier 3 — Construction

All construction predicates allocate a sparse matrix and return an opaque integer
HANDLE.  Pass the HANDLE to conversion, inspection, or linalg predicates.

### MakeCSR

```clausal
# skip
MakeCSR(DATA, INDICES, INDPTR, RESULT)
MakeCSR(DATA, INDICES, INDPTR, SHAPE, RESULT)
MakeCSR(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
```

Build a CSR (Compressed Sparse Row) matrix.
Wraps `scipy.sparse.csr_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)`.

- `DATA`: 1-D array of non-zero values
- `INDICES`: 1-D array of column indices for each stored value
- `INDPTR`: 1-D array of row pointers (length = rows + 1)
- `SHAPE`: `(rows, cols)` tuple (optional; inferred when omitted)
- `DTYPE`: NumPy dtype string, e.g. `'float64'` (optional)
- `RESULT`: integer HANDLE

```clausal
# skip
DATA is ++([1.0, 2.0, 3.0]),
IDX  is ++([0, 1, 2]),
PTR  is ++([0, 1, 2, 3]),
MakeCSR(DATA, IDX, PTR, H)
```

### MakeCSC

```clausal
# skip
MakeCSC(DATA, INDICES, INDPTR, RESULT)
MakeCSC(DATA, INDICES, INDPTR, SHAPE, RESULT)
MakeCSC(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
```

Build a CSC (Compressed Sparse Column) matrix.
Wraps `scipy.sparse.csc_matrix(...)`.  Arguments have the same meaning as
`MakeCSR` but `INDICES` contains row indices and `INDPTR` contains column
pointers.

### MakeCOO

```clausal
# skip
MakeCOO(DATA, ROW, COL, RESULT)
MakeCOO(DATA, ROW, COL, SHAPE, RESULT)
```

Build a COO (Coordinate) sparse matrix.
Wraps `scipy.sparse.coo_matrix((data, (row, col)), shape=SHAPE)`.

- `DATA`: 1-D array of non-zero values
- `ROW`, `COL`: 1-D arrays of row and column indices for each value
- `SHAPE`: `(rows, cols)` tuple (optional)
- `RESULT`: integer HANDLE

```clausal
# skip
DATA is ++([1.0, 2.0]),
ROW  is ++([0, 1]),
COL  is ++([1, 0]),
MakeCOO(DATA, ROW, COL, ++(tuple([2, 2])), H)
```

### MakeDiagonals

```clausal
# skip
MakeDiagonals(DIAGONALS, RESULT)
MakeDiagonals(DIAGONALS, OFFSETS, RESULT)
MakeDiagonals(DIAGONALS, OFFSETS, SHAPE, RESULT)
```

Build a sparse diagonal matrix.
Wraps `scipy.sparse.diags(diagonals, offsets=OFFSETS, shape=SHAPE)`.

- `DIAGONALS`: a single 1-D array (main diagonal) or a list of arrays
- `OFFSETS`: integer (0 = main diagonal, +k = k-th superdiagonal,
  -k = k-th subdiagonal) or a list matching `DIAGONALS`
- `SHAPE`: `(rows, cols)` tuple (optional)
- `RESULT`: integer HANDLE

```clausal
# skip
MakeDiagonals(++([1.0, 2.0, 3.0]), H)        % 3x3 identity-like diagonal
MakeDiagonals(++([1.0, 2.0]), 1, ++(tuple([3, 3])), H)   % superdiagonal
```

### MakeEye

```clausal
# skip
MakeEye(N, RESULT)
MakeEye(N, M, RESULT)
MakeEye(N, M, K, RESULT)
```

Build a sparse identity or shifted-diagonal matrix.
Wraps `scipy.sparse.eye(N, M=M, k=K)`.

- `N`: number of rows
- `M`: number of columns (default = N)
- `K`: diagonal offset (0 = main diagonal, default = 0)
- `RESULT`: integer HANDLE

```clausal
# skip
MakeEye(4, H),
ToDense(H, D)   % D is the 4x4 identity matrix
```

---

## Tier 3 — Conversions

### ToDense

```clausal
# skip
ToDense(HANDLE, RESULT)
ToDense(HANDLE, ORDER, RESULT)
```

Convert a sparse matrix to a dense NumPy array.
Wraps `handle.toarray(order=ORDER)`.

- `HANDLE`: integer handle to a sparse matrix
- `ORDER`: `'C'` (row-major) or `'F'` (column-major); default → row-major
- `RESULT`: 2-D NumPy array

### FromDense

```clausal
# skip
FromDense(DENSE, RESULT)
FromDense(DENSE, FORMAT, RESULT)
```

Convert a dense array to a sparse matrix handle.

- `DENSE`: 2-D NumPy array (or nested lists)
- `FORMAT`: sparse format string: `'csr'`, `'csc'`, `'coo'`, etc.
  Default (arity 2) is `'csr'`.
- `RESULT`: integer HANDLE

```clausal
# skip
A is ++([[1.0, 0.0], [0.0, 2.0]]),
FromDense(A, 'csc', H)
```

---

## Tier 3 — Inspection

### Shape

```clausal
# skip
Shape(HANDLE, RESULT)
```

Return the shape of the sparse matrix as a `(rows, cols)` tuple.

```clausal
# skip
Shape(H, S),
R is ++(S[0]),
C is ++(S[1])
```

### NonzeroCount

```clausal
# skip
NonzeroCount(HANDLE, RESULT)
```

Return the number of stored (non-zero) elements (`handle.nnz`).

---

## scipy.sparse.linalg

### Solve

```clausal
# skip
Solve(A, B, RESULT)
Solve(A, B, PERMC_SPEC, RESULT)
Solve(A, B, PERMC_SPEC, USE_UMFPACK, RESULT)
```

Solve the sparse linear system `A @ X = B`.
Wraps `scipy.sparse.linalg.spsolve(a, b, permc_spec=..., use_umfpack=...)`.

- `A`: HANDLE to a square sparse matrix
- `B`: 1-D (or 2-D) right-hand-side array
- `PERMC_SPEC`: column permutation strategy: `'NATURAL'`, `'MMD_ATA'`,
  `'MMD_AT_PLUS_A'`, `'COLAMD'`, or `None` (default)
- `USE_UMFPACK`: boolean, use UMFPACK if available (default `True`)
- `RESULT`: dense solution array X

```clausal
# skip
MakeCSR(DATA, IDX, PTR, ++(tuple([3, 3])), A),
Solve(A, B, X),
Free(A)
```

### EigenDecomposeHermitian

```clausal
# skip
EigenDecomposeHermitian(A, RESULT)
EigenDecomposeHermitian(A, K, RESULT)
```

Compute K eigenvalues and eigenvectors of a real-symmetric or complex-Hermitian
sparse matrix.  Wraps `scipy.sparse.linalg.eigsh(a, k=K)`.

- `A`: HANDLE to a sparse symmetric/Hermitian matrix
- `K`: number of eigenvalues to compute (default = `min(6, n-1)`)
- `RESULT`: dict with keys `'eigenvalues'` (1-D array) and
  `'eigenvectors'` (n × K array)

```clausal
# skip
EigenDecomposeHermitian(H, 3, R),
EV is ++(R['eigenvalues'])    % 3 smallest eigenvalues
```

### SingularValueDecompose

```clausal
# skip
SingularValueDecompose(A, RESULT)
SingularValueDecompose(A, K, RESULT)
```

Compute K largest singular values and vectors via ARPACK.
Wraps `scipy.sparse.linalg.svds(a, k=K)`.

- `A`: HANDLE to a sparse matrix
- `K`: number of singular values to compute (default = `min(6, min(shape)-1)`)
- `RESULT`: dict with keys `'u'` (left singular vectors, n × K),
  `'s'` (singular values, length K), `'vt'` (right singular vectors, K × m)

```clausal
# skip
SingularValueDecompose(H, 2, R),
S is ++(R['s'])    % 2 largest singular values
```

---

## Lifecycle

### Free

```clausal
# skip
Free(HANDLE)
```

Release the sparse matrix registered under HANDLE.  Always succeeds.
Call `Free` when the handle is no longer needed to avoid memory leaks.

---

## Usage example

```clausal
-import_from(scipy_sparse, [MakeCSR, Solve, NonzeroCount, Free])

solve_sparse(DATA, IDX, PTR, SHAPE, B, X) <- (
    MakeCSR(DATA, IDX, PTR, SHAPE, A),
    Solve(A, B, X),
    Free(A)
)

sparsity(DATA, IDX, PTR, SPARSITY) <- (
    MakeCSR(DATA, IDX, PTR, A),
    Shape(A, S),
    NonzeroCount(A, NNZ),
    TOTAL is ++(S[0] * S[1]),
    SPARSITY is ++(1.0 - NNZ / TOTAL),
    Free(A)
)
```

---

*See also: [scipy.linalg](scipy_linalg.md) — dense linear algebra · [scipy.spatial](scipy_spatial.md) — sparse distance matrices.*
