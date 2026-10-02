"""clausal.modules.py.scipy_sparse — scipy.sparse predicates for Clausal.

Provides sparse matrix construction, conversion, inspection, and linear algebra
from ``scipy.sparse`` and ``scipy.sparse.linalg`` as importable predicate objects
for use in .clausal files via::

    -import_from(scipy_sparse, [make_csr, make_csc, make_coo, make_diagonals, make_eye, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_sparse, [make_csr, ...])

Tiers
-----
**Tier 3 — handle-based sparse matrices** (construction):
    make_csr, make_csc, make_coo, make_diagonals, make_eye

**Tier 3 — conversions**:
    to_dense, from_dense

**Tier 3 — inspection**:
    shape, nonzero_count

**scipy.sparse.linalg** (sparse linear algebra):
    solve, eigen_decompose_hermitian, singular_value_decompose

**Lifecycle**:
    free

Predicate catalogue
-------------------

Construction (Tier 3):
    make_csr(DATA, INDICES, INDPTR, RESULT)
    make_csr(DATA, INDICES, INDPTR, SHAPE, RESULT)
    make_csr(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
        → scipy.sparse.csr_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)
        Build a CSR (Compressed Sparse Row) matrix.
        RESULT: integer HANDLE.

    make_csc(DATA, INDICES, INDPTR, RESULT)
    make_csc(DATA, INDICES, INDPTR, SHAPE, RESULT)
    make_csc(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
        → scipy.sparse.csc_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)
        Build a CSC (Compressed Sparse Column) matrix.
        RESULT: integer HANDLE.

    make_coo(DATA, ROW, COL, RESULT)
    make_coo(DATA, ROW, COL, SHAPE, RESULT)
        → scipy.sparse.coo_matrix((data, (row, col)), shape=SHAPE)
        Build a COO (Coordinate) sparse matrix.
        RESULT: integer HANDLE.

    make_diagonals(DIAGONALS, RESULT)
    make_diagonals(DIAGONALS, OFFSETS, RESULT)
    make_diagonals(DIAGONALS, OFFSETS, SHAPE, RESULT)
        → scipy.sparse.diags(diagonals, offsets=OFFSETS, shape=SHAPE)
        Build a sparse diagonal matrix.
        DIAGONALS: sequence of diagonal arrays (or single array for main diagonal).
        OFFSETS: integer offset (0=main) or list matching DIAGONALS.
        RESULT: integer HANDLE.

    make_eye(N, RESULT)
    make_eye(N, M, RESULT)
    make_eye(N, M, K, RESULT)
        → scipy.sparse.eye(N, M=M, k=K)
        Build a sparse identity (or shifted-diagonal) matrix.
        RESULT: integer HANDLE.

Conversions (Tier 3):
    to_dense(HANDLE, RESULT)
    to_dense(HANDLE, ORDER, RESULT)
        → handle.toarray(order=ORDER)
        Convert a sparse matrix to a dense numpy array.
        ORDER: 'C' (row-major) or 'F' (column-major); default None → row-major.

    from_dense(DENSE, RESULT)
    from_dense(DENSE, FORMAT, RESULT)
        → scipy.sparse.csr_matrix(DENSE) or format-specific constructor
        Convert a dense array to a sparse matrix handle.
        FORMAT: 'csr', 'csc', 'coo', etc.  Default is 'csr'.

Inspection (Tier 3):
    shape(HANDLE, RESULT)
        → handle.shape
        Return the (rows, cols) shape tuple of the sparse matrix.

    nonzero_count(HANDLE, RESULT)
        → handle.nnz
        Return the number of stored (non-zero) elements.

scipy.sparse.linalg:
    solve(A, B, RESULT)
    solve(A, B, PERMC_SPEC, RESULT)
    solve(A, B, PERMC_SPEC, USE_UMFPACK, RESULT)
        → scipy.sparse.linalg.spsolve(a, b, permc_spec=PERMC_SPEC,
                                       use_umfpack=USE_UMFPACK)
        solve the sparse linear system A @ X = B.
        A: HANDLE to a square sparse matrix.
        RESULT: dense solution array X.

    eigen_decompose_hermitian(A, RESULT)
    eigen_decompose_hermitian(A, K, RESULT)
        → scipy.sparse.linalg.eigsh(a, k=K)
        Compute K eigenvalues/eigenvectors of a real-symmetric or complex-Hermitian
        sparse matrix.  Default K=6.
        A: HANDLE to a sparse matrix.
        RESULT: dict with keys 'eigenvalues' and 'eigenvectors'.

    singular_value_decompose(A, RESULT)
    singular_value_decompose(A, K, RESULT)
        → scipy.sparse.linalg.svds(a, k=K)
        Compute K largest singular values/vectors via ARPACK.  Default K=6.
        A: HANDLE to a sparse matrix.
        RESULT: dict with keys 'u', 's', 'vt'.

Lifecycle:
    free(HANDLE)
        Release the object registered under HANDLE.  Always succeeds.

Usage example::

    -import_from(scipy_sparse, [make_csr, to_dense, solve, free])

    solve_system(DATA, INDICES, INDPTR, SHAPE, B, X) <- (
        make_csr(DATA, INDICES, INDPTR, SHAPE, A),
        solve(A, B, X),
        free(A)
    )
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Lazy scipy imports ────────────────────────────────────────────────────

_scipy_sparse = None
_scipy_sparse_linalg = None
_sparse_lock = _threading.Lock()


def _ensure_sparse():
    global _scipy_sparse, _scipy_sparse_linalg
    if _scipy_sparse is not None:
        return
    with _sparse_lock:
        if _scipy_sparse is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_sparse = _import_stdlib("scipy.sparse")
        _scipy_sparse_linalg = _import_stdlib("scipy.sparse.linalg")


def _sp():
    _ensure_sparse()
    return _scipy_sparse


def _la():
    _ensure_sparse()
    return _scipy_sparse_linalg


# ── Handle registry ───────────────────────────────────────────────────────

_SPARSE_REGISTRY: dict[int, object] = {}
_registry_lock = _threading.Lock()
_registry_counter = [0]


def _alloc_handle(obj: object) -> int:
    with _registry_lock:
        _registry_counter[0] += 1
        handle = _registry_counter[0]
        _SPARSE_REGISTRY[handle] = obj
    return handle


def _lookup_handle(handle: int) -> object:
    obj = _SPARSE_REGISTRY.get(int(handle))
    if obj is None:
        raise KeyError(f"Unknown sparse handle: {handle!r}")
    return obj


def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Tier 3 dispatch helpers ───────────────────────────────────────────────

def _make(constructor: Callable) -> Callable:
    """Deref inputs, construct sparse object, alloc handle, unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            obj = constructor(*inputs)
            handle = _alloc_handle(obj)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, handle, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _query(evaluator: Callable) -> Callable:
    """Deref inputs, look up handle from first input, call evaluator, unify."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        raw = [deref(x) for x in args[:-2]]
        try:
            obj = _lookup_handle(raw[0])
            out = evaluator(obj, *raw[1:])
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _linalg_op(evaluator: Callable) -> Callable:
    """Like _query but first arg is a HANDLE to sparse matrix; rest are plain values."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        raw = [deref(x) for x in args[:-2]]
        try:
            sparse_mat = _lookup_handle(raw[0])
            out = evaluator(sparse_mat, *raw[1:])
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Construction
# ═══════════════════════════════════════════════════════════════════════════

# ── make_csr ────────────────────────────────────────────────────────────────
# make_csr(DATA, INDICES, INDPTR, RESULT) → arity 4
# make_csr(DATA, INDICES, INDPTR, SHAPE, RESULT) → arity 5
# make_csr(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT) → arity 6

make_csr = _pred("make_csr",
    (4, _make(lambda data, indices, indptr:
        _sp().csr_matrix((data, indices, indptr)))),
    (5, _make(lambda data, indices, indptr, shape:
        _sp().csr_matrix((data, indices, indptr), shape=tuple(shape)))),
    (6, _make(lambda data, indices, indptr, shape, dtype:
        _sp().csr_matrix((data, indices, indptr), shape=tuple(shape), dtype=dtype))),
)

# ── make_csc ────────────────────────────────────────────────────────────────
# make_csc(DATA, INDICES, INDPTR, RESULT) → arity 4
# make_csc(DATA, INDICES, INDPTR, SHAPE, RESULT) → arity 5
# make_csc(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT) → arity 6

make_csc = _pred("make_csc",
    (4, _make(lambda data, indices, indptr:
        _sp().csc_matrix((data, indices, indptr)))),
    (5, _make(lambda data, indices, indptr, shape:
        _sp().csc_matrix((data, indices, indptr), shape=tuple(shape)))),
    (6, _make(lambda data, indices, indptr, shape, dtype:
        _sp().csc_matrix((data, indices, indptr), shape=tuple(shape), dtype=dtype))),
)

# ── make_coo ────────────────────────────────────────────────────────────────
# make_coo(DATA, ROW, COL, RESULT) → arity 4
# make_coo(DATA, ROW, COL, SHAPE, RESULT) → arity 5

make_coo = _pred("make_coo",
    (4, _make(lambda data, row, col:
        _sp().coo_matrix((data, (row, col))))),
    (5, _make(lambda data, row, col, shape:
        _sp().coo_matrix((data, (row, col)), shape=tuple(shape)))),
)

# ── make_diagonals ──────────────────────────────────────────────────────────────
# make_diagonals(DIAGONALS, RESULT) → arity 2
# make_diagonals(DIAGONALS, OFFSETS, RESULT) → arity 3
# make_diagonals(DIAGONALS, OFFSETS, SHAPE, RESULT) → arity 4

make_diagonals = _pred("make_diagonals",
    (2, _make(lambda diagonals:
        _sp().diags(diagonals))),
    (3, _make(lambda diagonals, offsets:
        _sp().diags(diagonals, offsets=offsets))),
    (4, _make(lambda diagonals, offsets, shape:
        _sp().diags(diagonals, offsets=offsets, shape=tuple(shape)))),
)

# ── make_eye ────────────────────────────────────────────────────────────────
# make_eye(N, RESULT) → arity 2
# make_eye(N, M, RESULT) → arity 3
# make_eye(N, M, K, RESULT) → arity 4

make_eye = _pred("make_eye",
    (2, _make(lambda n:
        _sp().eye(int(n)))),
    (3, _make(lambda n, m:
        _sp().eye(int(n), int(m)))),
    (4, _make(lambda n, m, k:
        _sp().eye(int(n), int(m), k=int(k)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Conversions
# ═══════════════════════════════════════════════════════════════════════════

# ── to_dense ────────────────────────────────────────────────────────────────
# to_dense(HANDLE, RESULT) → arity 2
# to_dense(HANDLE, ORDER, RESULT) → arity 3

to_dense = _pred("to_dense",
    (2, _query(lambda obj:
        obj.toarray())),
    (3, _query(lambda obj, order:
        obj.toarray(order=str(order)))),
)

# ── from_dense ──────────────────────────────────────────────────────────────
# from_dense(DENSE, RESULT) → arity 2
# from_dense(DENSE, FORMAT, RESULT) → arity 3

def _from_dense_fmt(dense, fmt):
    constructor = getattr(_sp(), f"{str(fmt)}_matrix", None)
    if constructor is None:
        raise ValueError(f"Unknown sparse format: {fmt!r}")
    return constructor(dense)

from_dense = _pred("from_dense",
    (2, _make(lambda dense:
        _sp().csr_matrix(dense))),
    (3, _make(lambda dense, fmt:
        _from_dense_fmt(dense, fmt))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Inspection
# ═══════════════════════════════════════════════════════════════════════════

# ── shape ──────────────────────────────────────────────────────────────────
# shape(HANDLE, RESULT) → arity 2

shape = _pred("shape",
    (2, _query(lambda obj: obj.shape)),
)

# ── nonzero_count ───────────────────────────────────────────────────────────
# nonzero_count(HANDLE, RESULT) → arity 2

nonzero_count = _pred("nonzero_count",
    (2, _query(lambda obj: obj.nnz)),
)


# ═══════════════════════════════════════════════════════════════════════════
# scipy.sparse.linalg
# ═══════════════════════════════════════════════════════════════════════════

# ── solve ──────────────────────────────────────────────────────────────────
# solve(A, B, RESULT) → arity 3
# solve(A, B, PERMC_SPEC, RESULT) → arity 4
# solve(A, B, PERMC_SPEC, USE_UMFPACK, RESULT) → arity 5

def _sparse_solve_3(mat, b):
    return _la().spsolve(mat, b, permc_spec=None, use_umfpack=True)

def _sparse_solve_4(mat, b, permc_spec):
    return _la().spsolve(mat, b, permc_spec=permc_spec)

def _sparse_solve_5(mat, b, permc_spec, use_umfpack):
    return _la().spsolve(mat, b, permc_spec=permc_spec, use_umfpack=bool(use_umfpack))

solve = _pred("solve",
    (3, _linalg_op(_sparse_solve_3)),
    (4, _linalg_op(_sparse_solve_4)),
    (5, _linalg_op(_sparse_solve_5)),
)

# ── eigen_decompose_hermitian ────────────────────────────────────────────────
# eigen_decompose_hermitian(A, RESULT) → arity 2  (default k=6)
# eigen_decompose_hermitian(A, K, RESULT) → arity 3

def _eigsh_default(mat):
    w, v = _la().eigsh(mat, k=min(6, mat.shape[0] - 1))
    return {"eigenvalues": w, "eigenvectors": v}

def _eigsh_k(mat, k):
    w, v = _la().eigsh(mat, k=int(k))
    return {"eigenvalues": w, "eigenvectors": v}

eigen_decompose_hermitian = _pred("eigen_decompose_hermitian",
    (2, _linalg_op(_eigsh_default)),
    (3, _linalg_op(_eigsh_k)),
)

# ── singular_value_decompose ────────────────────────────────────────────────
# singular_value_decompose(A, RESULT) → arity 2  (default k=6)
# singular_value_decompose(A, K, RESULT) → arity 3

def _svds_default(mat):
    k = min(6, min(mat.shape) - 1)
    u, s, vt = _la().svds(mat, k=k)
    return {"u": u, "s": s, "vt": vt}

def _svds_k(mat, k):
    u, s, vt = _la().svds(mat, k=int(k))
    return {"u": u, "s": s, "vt": vt}

singular_value_decompose = _pred("singular_value_decompose",
    (2, _linalg_op(_svds_default)),
    (3, _linalg_op(_svds_k)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle — free
# ═══════════════════════════════════════════════════════════════════════════

def _free_dispatch(this_generator, _proceed, _fail, _catcher, handle, trail):
    try:
        with _registry_lock:
            _SPARSE_REGISTRY.pop(int(deref(handle)), None)
    except Exception:
        pass
    yield (_proceed, None)
    yield (_fail, DONE)

free = _pred("free",
    (1, _free_dispatch),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    "make_csr",
    "make_csc",
    "make_coo",
    "make_diagonals",
    "make_eye",
    "to_dense",
    "from_dense",
    "shape",
    "nonzero_count",
    "solve",
    "eigen_decompose_hermitian",
    "singular_value_decompose",
    "free",
    "_SPARSE_REGISTRY",
]
