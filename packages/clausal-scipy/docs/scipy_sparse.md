# scipy.sparse — Sparse Matrices and Sparse Linear Algebra

Provides sparse matrix construction, conversion, inspection, and linear algebra
from `scipy.sparse` and `scipy.sparse.linalg` as [importable](import.md) Clausal Prolog predicates.

## Import

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:import"
```

or via the canonical `py.*` path:

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:import_ex2"
```

---

## Tiers

| Tier | Predicates | Notes |
|------|-----------|-------|
| 3 — handle | `make_csr`, `make_csc`, `make_coo`, `make_diagonals`, `make_eye` | Sparse matrix construction |
| 3 — handle | `to_dense`, `from_dense` | Dense/sparse conversions |
| 3 — handle | `shape`, `nonzero_count` | Inspection |
| linalg | `solve`, `eigen_decompose_hermitian`, `singular_value_decompose` | Sparse linear algebra |
| lifecycle | `free` | Release any handle |

---

## Tier 3 — Construction

All construction predicates allocate a sparse matrix and return an opaque integer
HANDLE.  Pass the HANDLE to conversion, inspection, or linalg predicates.

### make_csr

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makecsr"
```

Build a CSR (Compressed Sparse Row) matrix.
Wraps `scipy.sparse.csr_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)`.

- `DATA`: 1-D array of non-zero values
- `INDICES`: 1-D array of column indices for each stored value
- `INDPTR`: 1-D array of row pointers (length = rows + 1)
- `SHAPE`: `(rows, cols)` tuple (optional; inferred when omitted)
- `DTYPE`: NumPy dtype string, e.g. `'float64'` (optional)
- `RESULT`: integer HANDLE

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makecsr_ex2"
```

### make_csc

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makecsc"
```

Build a CSC (Compressed Sparse Column) matrix.
Wraps `scipy.sparse.csc_matrix(...)`.  Arguments have the same meaning as
`make_csr` but `INDICES` contains row indices and `INDPTR` contains column
pointers.

### make_coo

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makecoo"
```

Build a COO (Coordinate) sparse matrix.
Wraps `scipy.sparse.coo_matrix((data, (row, col)), shape=SHAPE)`.

- `DATA`: 1-D array of non-zero values
- `ROW`, `COL`: 1-D arrays of row and column indices for each value
- `SHAPE`: `(rows, cols)` tuple (optional)
- `RESULT`: integer HANDLE

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makecoo_ex2"
```

### make_diagonals

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makediagonals"
```

Build a sparse diagonal matrix.
Wraps `scipy.sparse.diags(diagonals, offsets=OFFSETS, shape=SHAPE)`.

- `DIAGONALS`: a single 1-D array (main diagonal) or a list of arrays
- `OFFSETS`: integer (0 = main diagonal, +k = k-th superdiagonal,
  -k = k-th subdiagonal) or a list matching `DIAGONALS`
- `SHAPE`: `(rows, cols)` tuple (optional)
- `RESULT`: integer HANDLE

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makediagonals_ex2"
```

### make_eye

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makeeye"
```

Build a sparse identity or shifted-diagonal matrix.
Wraps `scipy.sparse.eye(N, M=M, k=K)`.

- `N`: number of rows
- `M`: number of columns (default = N)
- `K`: diagonal offset (0 = main diagonal, default = 0)
- `RESULT`: integer HANDLE

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:makeeye_ex2"
```

---

## Tier 3 — Conversions

### to_dense

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:todense"
```

Convert a sparse matrix to a dense NumPy array.
Wraps `handle.toarray(order=ORDER)`.

- `HANDLE`: integer handle to a sparse matrix
- `ORDER`: `'C'` (row-major) or `'F'` (column-major); default → row-major
- `RESULT`: 2-D NumPy array

### from_dense

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:fromdense"
```

Convert a dense array to a sparse matrix handle.

- `DENSE`: 2-D NumPy array (or nested lists)
- `FORMAT`: sparse format string: `'csr'`, `'csc'`, `'coo'`, etc.
  Default (arity 2) is `'csr'`.
- `RESULT`: integer HANDLE

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:fromdense_ex2"
```

---

## Tier 3 — Inspection

### shape

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:shape"
```

Return the shape of the sparse matrix as a `(rows, cols)` tuple.

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:shape_ex2"
```

### nonzero_count

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:nonzerocount"
```

Return the number of stored (non-zero) elements (`handle.nnz`).

---

## scipy.sparse.linalg

### solve

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:solve"
```

solve the sparse linear system `A @ X = B`.
Wraps `scipy.sparse.linalg.spsolve(a, b, permc_spec=..., use_umfpack=...)`.

- `A`: HANDLE to a square sparse matrix
- `B`: 1-D (or 2-D) right-hand-side array
- `PERMC_SPEC`: column permutation strategy: `'NATURAL'`, `'MMD_ATA'`,
  `'MMD_AT_PLUS_A'`, `'COLAMD'`, or `None` (default)
- `USE_UMFPACK`: boolean, use UMFPACK if available (default `True`)
- `RESULT`: dense solution array X

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:solve_ex2"
```

### eigen_decompose_hermitian

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:eigendecomposehermitian"
```

Compute K eigenvalues and eigenvectors of a real-symmetric or complex-Hermitian
sparse matrix.  Wraps `scipy.sparse.linalg.eigsh(a, k=K)`.

- `A`: HANDLE to a sparse symmetric/Hermitian matrix
- `K`: number of eigenvalues to compute (default = `min(6, n-1)`)
- `RESULT`: dict with keys `'eigenvalues'` (1-D array) and
  `'eigenvectors'` (n × K array)

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:eigendecomposehermitian_ex2"
```

### singular_value_decompose

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:singularvaluedecompose"
```

Compute K largest singular values and vectors via ARPACK.
Wraps `scipy.sparse.linalg.svds(a, k=K)`.

- `A`: HANDLE to a sparse matrix
- `K`: number of singular values to compute (default = `min(6, min(shape)-1)`)
- `RESULT`: dict with keys `'u'` (left singular vectors, n × K),
  `'s'` (singular values, length K), `'vt'` (right singular vectors, K × m)

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:singularvaluedecompose_ex2"
```

---

## Lifecycle

### free

```seam
--8<-- "tests/fixtures/docs/scipy_sparse_sigs.txt:free"
```

Release the sparse matrix registered under HANDLE.  Always succeeds.
Call `free` when the handle is no longer needed to avoid memory leaks.

---

## Usage example

```seam
-import_from(scipy_sparse, [make_csr, solve, nonzero_count, free])

solve_sparse(DATA, IDX, PTR, SHAPE, B, X) <- (
    make_csr(DATA, IDX, PTR, SHAPE, A),
    solve(A, B, X),
    free(A)
)

sparsity(DATA, IDX, PTR, SPARSITY) <- (
    make_csr(DATA, IDX, PTR, A),
    shape(A, S),
    nonzero_count(A, NNZ),
    TOTAL is ++(S[0] * S[1]),
    SPARSITY is ++(1.0 - NNZ / TOTAL),
    free(A)
)
```

---

*See also: [scipy.linalg](scipy_linalg.md) — dense linear algebra · [scipy.spatial](scipy_spatial.md) — sparse distance matrices.*
