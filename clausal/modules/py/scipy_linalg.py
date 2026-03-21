"""clausal.modules.py.scipy_linalg — scipy.linalg predicates for Clausal.

Provides linear algebra routines from scipy.linalg as importable predicate
objects for use in .clausal files via::

    -import_from(py.scipy_linalg, [Solve, SingularValueDecompose, Inverse, ...])

Tiers
-----
- **Tier 1** (array inputs → array result):
    Solve, SolveTriangular, Cholesky,
    Inverse, PseudoInverse, Determinant, Norm,
    MatrixExponential, MatrixLogarithm, MatrixSquareRoot,
    MatrixFunction, LuSolve, CholeskySolve

- **Tier 2** (returns result dict; use ResultGet to access fields):
    LeastSquares           → dict {x, residuals, rank, s}
    LuDecompose            → dict {p, l, u}
    QrDecompose            → dict {q, r}
    SingularValueDecompose → dict {u, s, vh}
    EigenDecompose         → dict {eigenvalues, eigenvectors}
    EigenDecomposeHermitian→ dict {eigenvalues, eigenvectors}
    Schur                  → dict {t, z}
    LuFactor               → opaque (lu, piv) tuple  (passed to LuSolve)
    CholeskyFactor         → opaque (c, lower) tuple (passed to CholeskySolve)

Helper:
    ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE

Predicate catalogue
-------------------
Linear system solvers:
    Solve(A, B, RESULT)
    Solve(A, B, ASSUME_A, RESULT)              # ASSUME_A: 'gen'/'sym'/'her'/'pos'
    LeastSquares(A, B, RESULT)
    SolveTriangular(A, B, RESULT)
    SolveTriangular(A, B, LOWER, RESULT)       # LOWER: bool (default False → upper)

Matrix decompositions:
    LuDecompose(A, RESULT)                     # RESULT: dict {p, l, u}
    QrDecompose(A, RESULT)                     # RESULT: dict {q, r}
    SingularValueDecompose(A, RESULT)          # RESULT: dict {u, s, vh}
    Cholesky(A, RESULT)                        # default LOWER=False (upper factor)
    Cholesky(A, LOWER, RESULT)
    EigenDecompose(A, RESULT)                  # RESULT: dict {eigenvalues, eigenvectors}
    EigenDecomposeHermitian(A, RESULT)         # symmetric/Hermitian specialisation
    Schur(A, RESULT)                           # RESULT: dict {t, z}
    Schur(A, OUTPUT, RESULT)                   # OUTPUT: 'real' or 'complex'

Matrix functions:
    Inverse(A, RESULT)
    PseudoInverse(A, RESULT)
    Determinant(A, RESULT)
    Norm(A, RESULT)
    Norm(A, ORD, RESULT)
    MatrixExponential(A, RESULT)
    MatrixLogarithm(A, RESULT)
    MatrixSquareRoot(A, RESULT)
    MatrixFunction(A, FUNC, RESULT)            # FUNC: Python callable

Two-step factorisations:
    LuFactor(A, RESULT)
    LuSolve(LU_PIV, B, RESULT)
    CholeskyFactor(A, RESULT)
    CholeskySolve(C_LOWER, B, RESULT)
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


# ── Lazy scipy.linalg import ──────────────────────────────────────────────

_scipy_linalg = None
_la_lock = _threading.Lock()


def _ensure_la():
    global _scipy_linalg
    if _scipy_linalg is not None:
        return
    with _la_lock:
        if _scipy_linalg is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_linalg = _import_stdlib("scipy.linalg")


def _la():
    _ensure_la()
    return _scipy_linalg


# ── Predicate adapter ─────────────────────────────────────────────────────

class _ScipyLinalgPredicate:
    """Dispatch adapter for a scipy.linalg predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_ScipyLinalgPredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        # args layout: (input_0, ..., input_{n-1}, result, trail)
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.linalg.{self._name}/{arities}"


# ── Dispatch function factories ───────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch for a predicate: inputs → scalar/array → unify RESULT."""
    def dispatch(this_generator, parent, *args):
        # args: (input_0, ..., input_{n-1}, result, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        out = call(*inputs)
        try:
            ok = bool(unify(result_var, out, trail))
        except (ValueError, TypeError):
            # numpy array comparison returns an array; treat as failed unification
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _la_fn(attr: str) -> Callable:
    """Return a callable that lazily calls ``scipy.linalg.<attr>(*args)``."""
    def call(*args):
        return getattr(_la(), attr)(*args)
    return call


def _la_kw(attr: str, **fixed_kwargs) -> Callable:
    """Return a callable that calls ``scipy.linalg.<attr>`` with fixed keyword args."""
    def call(*args):
        return getattr(_la(), attr)(*args, **fixed_kwargs)
    return call


def _pred(name: str, *arity_fns) -> _ScipyLinalgPredicate:
    """Create a ``_ScipyLinalgPredicate`` from (arity, dispatch_fn) pairs."""
    p = _ScipyLinalgPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── Linear system solvers ─────────────────────────────────────────────────

Solve = _pred("Solve",
    (3, _dispatch_fn(_la_fn("solve"))),
    (4, _dispatch_fn(lambda a, b, assume_a:
        _la().solve(a, b, assume_a=assume_a))),
)

LeastSquares = _pred("LeastSquares",
    (3, _dispatch_fn(lambda a, b: dict(
        zip(("x", "residuals", "rank", "s"), _la().lstsq(a, b))))),
)

SolveTriangular = _pred("SolveTriangular",
    (3, _dispatch_fn(_la_fn("solve_triangular"))),
    (4, _dispatch_fn(lambda a, b, lower:
        _la().solve_triangular(a, b, lower=lower))),
)


# ── Matrix decompositions ─────────────────────────────────────────────────

LuDecompose = _pred("LuDecompose",
    (2, _dispatch_fn(lambda a: dict(
        zip(("p", "l", "u"), _la().lu(a))))),
)

QrDecompose = _pred("QrDecompose",
    (2, _dispatch_fn(lambda a: dict(
        zip(("q", "r"), _la().qr(a))))),
)

SingularValueDecompose = _pred("SingularValueDecompose",
    (2, _dispatch_fn(lambda a: dict(
        zip(("u", "s", "vh"), _la().svd(a))))),
)

Cholesky = _pred("Cholesky",
    (2, _dispatch_fn(_la_kw("cholesky", lower=False))),
    (3, _dispatch_fn(lambda a, lower: _la().cholesky(a, lower=lower))),
)

EigenDecompose = _pred("EigenDecompose",
    (2, _dispatch_fn(lambda a: dict(
        zip(("eigenvalues", "eigenvectors"), _la().eig(a))))),
)

EigenDecomposeHermitian = _pred("EigenDecomposeHermitian",
    (2, _dispatch_fn(lambda a: dict(
        zip(("eigenvalues", "eigenvectors"), _la().eigh(a))))),
)

Schur = _pred("Schur",
    (2, _dispatch_fn(lambda a: dict(
        zip(("t", "z"), _la().schur(a))))),
    (3, _dispatch_fn(lambda a, output: dict(
        zip(("t", "z"), _la().schur(a, output=output))))),
)


# ── Matrix functions ──────────────────────────────────────────────────────

Inverse = _pred("Inverse",
    (2, _dispatch_fn(_la_fn("inv"))),
)

PseudoInverse = _pred("PseudoInverse",
    (2, _dispatch_fn(_la_fn("pinv"))),
)

Determinant = _pred("Determinant",
    (2, _dispatch_fn(_la_fn("det"))),
)

Norm = _pred("Norm",
    (2, _dispatch_fn(_la_fn("norm"))),
    (3, _dispatch_fn(lambda a, ord: _la().norm(a, ord=ord))),
)

MatrixExponential = _pred("MatrixExponential",
    (2, _dispatch_fn(_la_fn("expm"))),
)

MatrixLogarithm = _pred("MatrixLogarithm",
    (2, _dispatch_fn(_la_fn("logm"))),
)

MatrixSquareRoot = _pred("MatrixSquareRoot",
    (2, _dispatch_fn(_la_fn("sqrtm"))),
)

MatrixFunction = _pred("MatrixFunction",
    (3, _dispatch_fn(lambda a, func: _la().funm(a, func))),
)


# ── Two-step factorisation helpers ────────────────────────────────────────

LuFactor = _pred("LuFactor",
    (2, _dispatch_fn(_la_fn("lu_factor"))),
)

LuSolve = _pred("LuSolve",
    (3, _dispatch_fn(lambda lu_piv, b: _la().lu_solve(lu_piv, b))),
)

CholeskyFactor = _pred("CholeskyFactor",
    (2, _dispatch_fn(_la_fn("cho_factor"))),
)

CholeskySolve = _pred("CholeskySolve",
    (3, _dispatch_fn(lambda c_lower, b: _la().cho_solve(c_lower, b))),
)


# ── Helper: ResultGet ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """ResultGet(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (as produced by Tier 2 predicates).
    FIELD must be a ground string key.
    VALUE is unified with the retrieved value.
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, parent, result, field, value, trail):
        result = deref(result)
        field = deref(field)
        if not isinstance(result, dict) or not isinstance(field, str):
            yield (parent, DONE)
            return
        if field not in result:
            yield (parent, DONE)
            return
        try:
            ok = bool(unify(value, result[field], trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (parent, None)
        yield (parent, DONE)

    def __repr__(self) -> str:
        return "ResultGet/3"


ResultGet = _ResultGetPredicate()
