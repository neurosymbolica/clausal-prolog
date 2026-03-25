"""clausal.modules.py.scipy_sparse — scipy.sparse predicates for Clausal.

Provides sparse matrix construction, conversion, inspection, and linear algebra
from ``scipy.sparse`` and ``scipy.sparse.linalg`` as importable predicate objects
for use in .clausal files via::

    -import_from(scipy_sparse, [MakeCSR, MakeCSC, MakeCOO, MakeDiagonals, MakeEye, ...])

Or via the canonical ``py.*`` path::

    -import_from(py.scipy_sparse, [MakeCSR, ...])

Tiers
-----
**Tier 3 — handle-based sparse matrices** (construction):
    MakeCSR, MakeCSC, MakeCOO, MakeDiagonals, MakeEye

**Tier 3 — conversions**:
    ToDense, FromDense

**Tier 3 — inspection**:
    Shape, NonzeroCount

**scipy.sparse.linalg** (sparse linear algebra):
    Solve, EigenDecomposeHermitian, SingularValueDecompose

**Lifecycle**:
    Free

Predicate catalogue
-------------------

Construction (Tier 3):
    MakeCSR(DATA, INDICES, INDPTR, RESULT)
    MakeCSR(DATA, INDICES, INDPTR, SHAPE, RESULT)
    MakeCSR(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
        → scipy.sparse.csr_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)
        Build a CSR (Compressed Sparse Row) matrix.
        RESULT: integer HANDLE.

    MakeCSC(DATA, INDICES, INDPTR, RESULT)
    MakeCSC(DATA, INDICES, INDPTR, SHAPE, RESULT)
    MakeCSC(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT)
        → scipy.sparse.csc_matrix((data, indices, indptr), shape=SHAPE, dtype=DTYPE)
        Build a CSC (Compressed Sparse Column) matrix.
        RESULT: integer HANDLE.

    MakeCOO(DATA, ROW, COL, RESULT)
    MakeCOO(DATA, ROW, COL, SHAPE, RESULT)
        → scipy.sparse.coo_matrix((data, (row, col)), shape=SHAPE)
        Build a COO (Coordinate) sparse matrix.
        RESULT: integer HANDLE.

    MakeDiagonals(DIAGONALS, RESULT)
    MakeDiagonals(DIAGONALS, OFFSETS, RESULT)
    MakeDiagonals(DIAGONALS, OFFSETS, SHAPE, RESULT)
        → scipy.sparse.diags(diagonals, offsets=OFFSETS, shape=SHAPE)
        Build a sparse diagonal matrix.
        DIAGONALS: sequence of diagonal arrays (or single array for main diagonal).
        OFFSETS: integer offset (0=main) or list matching DIAGONALS.
        RESULT: integer HANDLE.

    MakeEye(N, RESULT)
    MakeEye(N, M, RESULT)
    MakeEye(N, M, K, RESULT)
        → scipy.sparse.eye(N, M=M, k=K)
        Build a sparse identity (or shifted-diagonal) matrix.
        RESULT: integer HANDLE.

Conversions (Tier 3):
    ToDense(HANDLE, RESULT)
    ToDense(HANDLE, ORDER, RESULT)
        → handle.toarray(order=ORDER)
        Convert a sparse matrix to a dense numpy array.
        ORDER: 'C' (row-major) or 'F' (column-major); default None → row-major.

    FromDense(DENSE, RESULT)
    FromDense(DENSE, FORMAT, RESULT)
        → scipy.sparse.csr_matrix(DENSE) or format-specific constructor
        Convert a dense array to a sparse matrix handle.
        FORMAT: 'csr', 'csc', 'coo', etc.  Default is 'csr'.

Inspection (Tier 3):
    Shape(HANDLE, RESULT)
        → handle.shape
        Return the (rows, cols) shape tuple of the sparse matrix.

    NonzeroCount(HANDLE, RESULT)
        → handle.nnz
        Return the number of stored (non-zero) elements.

scipy.sparse.linalg:
    Solve(A, B, RESULT)
    Solve(A, B, PERMC_SPEC, RESULT)
    Solve(A, B, PERMC_SPEC, USE_UMFPACK, RESULT)
        → scipy.sparse.linalg.spsolve(a, b, permc_spec=PERMC_SPEC,
                                       use_umfpack=USE_UMFPACK)
        Solve the sparse linear system A @ X = B.
        A: HANDLE to a square sparse matrix.
        RESULT: dense solution array X.

    EigenDecomposeHermitian(A, RESULT)
    EigenDecomposeHermitian(A, K, RESULT)
        → scipy.sparse.linalg.eigsh(a, k=K)
        Compute K eigenvalues/eigenvectors of a real-symmetric or complex-Hermitian
        sparse matrix.  Default K=6.
        A: HANDLE to a sparse matrix.
        RESULT: dict with keys 'eigenvalues' and 'eigenvectors'.

    SingularValueDecompose(A, RESULT)
    SingularValueDecompose(A, K, RESULT)
        → scipy.sparse.linalg.svds(a, k=K)
        Compute K largest singular values/vectors via ARPACK.  Default K=6.
        A: HANDLE to a sparse matrix.
        RESULT: dict with keys 'u', 's', 'vt'.

Lifecycle:
    Free(HANDLE)
        Release the object registered under HANDLE.  Always succeeds.

Usage example::

    -import_from(scipy_sparse, [MakeCSR, ToDense, Solve, Free])

    solve_system(DATA, INDICES, INDPTR, SHAPE, B, X) <- (
        MakeCSR(DATA, INDICES, INDPTR, SHAPE, A),
        Solve(A, B, X),
        Free(A)
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
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            obj = constructor(*inputs)
            handle = _alloc_handle(obj)
        except Exception:
            yield (parent, DONE)
            return
        if unify(result_var, handle, trail):
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _query(evaluator: Callable) -> Callable:
    """Deref inputs, look up handle from first input, call evaluator, unify."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        raw = [deref(x) for x in args[:-2]]
        try:
            obj = _lookup_handle(raw[0])
            out = evaluator(obj, *raw[1:])
        except Exception:
            yield (parent, DONE)
            return
        if unify(result_var, out, trail):
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _linalg_op(evaluator: Callable) -> Callable:
    """Like _query but first arg is a HANDLE to sparse matrix; rest are plain values."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        raw = [deref(x) for x in args[:-2]]
        try:
            sparse_mat = _lookup_handle(raw[0])
            out = evaluator(sparse_mat, *raw[1:])
        except Exception:
            yield (parent, DONE)
            return
        if unify(result_var, out, trail):
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (parent, DONE)
            return
        if unify(result_var, out, trail):
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Construction
# ═══════════════════════════════════════════════════════════════════════════

# ── MakeCSR ────────────────────────────────────────────────────────────────
# MakeCSR(DATA, INDICES, INDPTR, RESULT) → arity 4
# MakeCSR(DATA, INDICES, INDPTR, SHAPE, RESULT) → arity 5
# MakeCSR(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT) → arity 6

MakeCSR = _pred("MakeCSR",
    (4, _make(lambda data, indices, indptr:
        _sp().csr_matrix((data, indices, indptr)))),
    (5, _make(lambda data, indices, indptr, shape:
        _sp().csr_matrix((data, indices, indptr), shape=tuple(shape)))),
    (6, _make(lambda data, indices, indptr, shape, dtype:
        _sp().csr_matrix((data, indices, indptr), shape=tuple(shape), dtype=dtype))),
)

# ── MakeCSC ────────────────────────────────────────────────────────────────
# MakeCSC(DATA, INDICES, INDPTR, RESULT) → arity 4
# MakeCSC(DATA, INDICES, INDPTR, SHAPE, RESULT) → arity 5
# MakeCSC(DATA, INDICES, INDPTR, SHAPE, DTYPE, RESULT) → arity 6

MakeCSC = _pred("MakeCSC",
    (4, _make(lambda data, indices, indptr:
        _sp().csc_matrix((data, indices, indptr)))),
    (5, _make(lambda data, indices, indptr, shape:
        _sp().csc_matrix((data, indices, indptr), shape=tuple(shape)))),
    (6, _make(lambda data, indices, indptr, shape, dtype:
        _sp().csc_matrix((data, indices, indptr), shape=tuple(shape), dtype=dtype))),
)

# ── MakeCOO ────────────────────────────────────────────────────────────────
# MakeCOO(DATA, ROW, COL, RESULT) → arity 4
# MakeCOO(DATA, ROW, COL, SHAPE, RESULT) → arity 5

MakeCOO = _pred("MakeCOO",
    (4, _make(lambda data, row, col:
        _sp().coo_matrix((data, (row, col))))),
    (5, _make(lambda data, row, col, shape:
        _sp().coo_matrix((data, (row, col)), shape=tuple(shape)))),
)

# ── MakeDiagonals ──────────────────────────────────────────────────────────────
# MakeDiagonals(DIAGONALS, RESULT) → arity 2
# MakeDiagonals(DIAGONALS, OFFSETS, RESULT) → arity 3
# MakeDiagonals(DIAGONALS, OFFSETS, SHAPE, RESULT) → arity 4

MakeDiagonals = _pred("MakeDiagonals",
    (2, _make(lambda diagonals:
        _sp().diags(diagonals))),
    (3, _make(lambda diagonals, offsets:
        _sp().diags(diagonals, offsets=offsets))),
    (4, _make(lambda diagonals, offsets, shape:
        _sp().diags(diagonals, offsets=offsets, shape=tuple(shape)))),
)

# ── MakeEye ────────────────────────────────────────────────────────────────
# MakeEye(N, RESULT) → arity 2
# MakeEye(N, M, RESULT) → arity 3
# MakeEye(N, M, K, RESULT) → arity 4

MakeEye = _pred("MakeEye",
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

# ── ToDense ────────────────────────────────────────────────────────────────
# ToDense(HANDLE, RESULT) → arity 2
# ToDense(HANDLE, ORDER, RESULT) → arity 3

ToDense = _pred("ToDense",
    (2, _query(lambda obj:
        obj.toarray())),
    (3, _query(lambda obj, order:
        obj.toarray(order=str(order)))),
)

# ── FromDense ──────────────────────────────────────────────────────────────
# FromDense(DENSE, RESULT) → arity 2
# FromDense(DENSE, FORMAT, RESULT) → arity 3

def _from_dense_fmt(dense, fmt):
    constructor = getattr(_sp(), f"{str(fmt)}_matrix", None)
    if constructor is None:
        raise ValueError(f"Unknown sparse format: {fmt!r}")
    return constructor(dense)

FromDense = _pred("FromDense",
    (2, _make(lambda dense:
        _sp().csr_matrix(dense))),
    (3, _make(lambda dense, fmt:
        _from_dense_fmt(dense, fmt))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Tier 3 — Inspection
# ═══════════════════════════════════════════════════════════════════════════

# ── Shape ──────────────────────────────────────────────────────────────────
# Shape(HANDLE, RESULT) → arity 2

Shape = _pred("Shape",
    (2, _query(lambda obj: obj.shape)),
)

# ── NonzeroCount ───────────────────────────────────────────────────────────
# NonzeroCount(HANDLE, RESULT) → arity 2

NonzeroCount = _pred("NonzeroCount",
    (2, _query(lambda obj: obj.nnz)),
)


# ═══════════════════════════════════════════════════════════════════════════
# scipy.sparse.linalg
# ═══════════════════════════════════════════════════════════════════════════

# ── Solve ──────────────────────────────────────────────────────────────────
# Solve(A, B, RESULT) → arity 3
# Solve(A, B, PERMC_SPEC, RESULT) → arity 4
# Solve(A, B, PERMC_SPEC, USE_UMFPACK, RESULT) → arity 5

def _sparse_solve_3(mat, b):
    return _la().spsolve(mat, b, permc_spec=None, use_umfpack=True)

def _sparse_solve_4(mat, b, permc_spec):
    return _la().spsolve(mat, b, permc_spec=permc_spec)

def _sparse_solve_5(mat, b, permc_spec, use_umfpack):
    return _la().spsolve(mat, b, permc_spec=permc_spec, use_umfpack=bool(use_umfpack))

Solve = _pred("Solve",
    (3, _linalg_op(_sparse_solve_3)),
    (4, _linalg_op(_sparse_solve_4)),
    (5, _linalg_op(_sparse_solve_5)),
)

# ── EigenDecomposeHermitian ────────────────────────────────────────────────
# EigenDecomposeHermitian(A, RESULT) → arity 2  (default k=6)
# EigenDecomposeHermitian(A, K, RESULT) → arity 3

def _eigsh_default(mat):
    w, v = _la().eigsh(mat, k=min(6, mat.shape[0] - 1))
    return {"eigenvalues": w, "eigenvectors": v}

def _eigsh_k(mat, k):
    w, v = _la().eigsh(mat, k=int(k))
    return {"eigenvalues": w, "eigenvectors": v}

EigenDecomposeHermitian = _pred("EigenDecomposeHermitian",
    (2, _linalg_op(_eigsh_default)),
    (3, _linalg_op(_eigsh_k)),
)

# ── SingularValueDecompose ────────────────────────────────────────────────
# SingularValueDecompose(A, RESULT) → arity 2  (default k=6)
# SingularValueDecompose(A, K, RESULT) → arity 3

def _svds_default(mat):
    k = min(6, min(mat.shape) - 1)
    u, s, vt = _la().svds(mat, k=k)
    return {"u": u, "s": s, "vt": vt}

def _svds_k(mat, k):
    u, s, vt = _la().svds(mat, k=int(k))
    return {"u": u, "s": s, "vt": vt}

SingularValueDecompose = _pred("SingularValueDecompose",
    (2, _linalg_op(_svds_default)),
    (3, _linalg_op(_svds_k)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle — Free
# ═══════════════════════════════════════════════════════════════════════════

def _free_dispatch(this_generator, parent, handle, trail):
    try:
        with _registry_lock:
            _SPARSE_REGISTRY.pop(int(deref(handle)), None)
    except Exception:
        pass
    yield (parent, None)
    yield (parent, DONE)

Free = _pred("Free",
    (1, _free_dispatch),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    "MakeCSR",
    "MakeCSC",
    "MakeCOO",
    "MakeDiagonals",
    "MakeEye",
    "ToDense",
    "FromDense",
    "Shape",
    "NonzeroCount",
    "Solve",
    "EigenDecomposeHermitian",
    "SingularValueDecompose",
    "Free",
    "_SPARSE_REGISTRY",
]
