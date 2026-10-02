"""clausal.modules.py.scipy_linalg — scipy.linalg predicates for Clausal.

Provides linear algebra routines from scipy.linalg as importable predicate
objects for use in .clausal files via::

    -import_from(py.scipy_linalg, [solve, singular_value_decompose, inverse, ...])

Tiers
-----
- **Tier 1** (array inputs → array result):
    solve, solve_triangular, cholesky,
    inverse, pseudo_inverse, determinant, norm,
    matrix_exp_log, matrix_square_root,
    matrix_function, lu_solve, cholesky_solve

- **Tier 2** (returns result dict; use result_get to access fields):
    least_squares           → dict {x, residuals, rank, s}
    lu_decompose            → dict {p, l, u}
    qr_decompose            → dict {q, r}
    singular_value_decompose → dict {u, s, vh}
    eigen_decompose         → dict {eigenvalues, eigenvectors}
    eigen_decompose_hermitian→ dict {eigenvalues, eigenvectors}
    schur                  → dict {t, z}
    lu_factor               → opaque (lu, piv) tuple  (passed to lu_solve)
    cholesky_factor         → opaque (c, lower) tuple (passed to cholesky_solve)

Helper:
    result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE

Predicate catalogue
-------------------
Linear system solvers:
    solve(A, B, RESULT)
    solve(A, B, ASSUME_A, RESULT)              # ASSUME_A: 'gen'/'sym'/'her'/'pos'
    least_squares(A, B, RESULT)
    solve_triangular(A, B, RESULT)
    solve_triangular(A, B, LOWER, RESULT)       # LOWER: bool (default False → upper)

Matrix decompositions:
    lu_decompose(A, RESULT)                     # RESULT: dict {p, l, u}
    qr_decompose(A, RESULT)                     # RESULT: dict {q, r}
    singular_value_decompose(A, RESULT)          # RESULT: dict {u, s, vh}
    cholesky(A, RESULT)                        # default LOWER=False (upper factor)
    cholesky(A, LOWER, RESULT)
    eigen_decompose(A, RESULT)                  # RESULT: dict {eigenvalues, eigenvectors}
    eigen_decompose_hermitian(A, RESULT)         # symmetric/Hermitian specialisation
    schur(A, RESULT)                           # RESULT: dict {t, z}
    schur(A, OUTPUT, RESULT)                   # OUTPUT: 'real' or 'complex'

Matrix functions:
    inverse(A, RESULT)
    pseudo_inverse(A, RESULT)
    determinant(A, RESULT)
    norm(A, RESULT)
    norm(A, ORD, RESULT)
    matrix_exp_log(A, B)                         # bidirectional: expm(a) / logm(b)
    matrix_square_root(A, RESULT)
    matrix_function(A, FUNC, RESULT)            # FUNC: Python callable

Two-step factorisations:
    lu_factor(A, RESULT)
    lu_solve(LU_PIV, B, RESULT)
    cholesky_factor(A, RESULT)
    cholesky_solve(C_LOWER, B, RESULT)
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

import numpy as _np

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate
from clausal.modules.py._scipy_relations import _bidir_dispatch
from clausal.terms import Quantity as _Quantity
from clausal.modules.py._scipy_units import (
    make_quantity_aware, merge_dims, wrap_result,
    REQUIRE_DIMENSIONLESS, PASS_THROUGH_FIRST, STRIP_TO_PLAIN,
)


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


# ── Dispatch function factories ───────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Trampoline dispatch for a predicate: inputs → scalar/array → unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
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
            yield (_proceed, None)
        yield (_fail, DONE)
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


def _pred(name: str, *arity_fns) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


def _pred_bidir(name: str, *arity_dispatches) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, already-wrapped dispatch_fn) pairs."""
    p = ModulePredicate(name)
    for arity, dispatch_fn in arity_dispatches:
        p._dispatch_fns[arity] = dispatch_fn
    return p


# ── unit propagators ──────────────────────────────────────────────────────

def _solve_units(dims_list, result):
    """x dims = b_dims − A_dims.  If A dimensionless, x inherits b_dims."""
    a_dims = dims_list[0] or {}
    b_dims = dims_list[1]
    if b_dims is None:
        return None
    out_dims = merge_dims(b_dims, a_dims, -1)
    return wrap_result(result, out_dims)


def _lstsq_units(dims_list, result):
    """Propagate units through least-squares result dict."""
    a_dims = dims_list[0] or {}
    b_dims = dims_list[1]
    if b_dims is None:
        return None
    out = dict(result)
    x_dims = merge_dims(b_dims, a_dims, -1)
    out['x'] = wrap_result(result['x'], x_dims)
    res_dims = merge_dims(b_dims, b_dims, +1)   # residuals: dims b²
    out['residuals'] = wrap_result(result['residuals'], res_dims)
    if a_dims:
        out['s'] = wrap_result(result['s'], a_dims)   # singular values: dims A
    return out


def _qr_units(dims_list, result):
    """Q is dimensionless; R inherits dims of A."""
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['r'] = wrap_result(result['r'], a_dims)
    return out


def _svd_units(dims_list, result):
    """U and Vh are dimensionless; singular values S inherit dims of A."""
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['s'] = wrap_result(result['s'], a_dims)
    return out


def _eigen_units(dims_list, result):
    """Eigenvalues have same dims as A; eigenvectors are dimensionless."""
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['eigenvalues'] = wrap_result(result['eigenvalues'], a_dims)
    return out


def _schur_units(dims_list, result):
    """schur form T has same dims as A; unitary factor Z is dimensionless."""
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out = dict(result)
    out['t'] = wrap_result(result['t'], a_dims)
    return out


def _inverse_units(dims_list, result):
    """inverse dims = negated A dims."""
    a_dims = dims_list[0]
    if not a_dims:
        return None
    out_dims = merge_dims({}, a_dims, -1)
    return wrap_result(result, out_dims)


def _det_call(inner_call):
    """Custom determinant wrapper: captures matrix size for unit propagation.

    Uses matrix shape (n×n) to compute output dims = n · A_dims, which
    cannot be expressed via the generic make_quantity_aware contract.
    """
    def call(*inputs):
        a = inputs[0]
        if not isinstance(a, _Quantity):
            return inner_call(a)
        a_dims = dict(a.dims)
        a_val = a.value
        result = inner_call(a_val)
        if a_dims:
            n = a_val.shape[0]   # n×n matrix
            out_dims = {k: v * n for k, v in a_dims.items()}
            return wrap_result(result, out_dims)
        return result
    return call


# ── Linear system solvers ─────────────────────────────────────────────────

def _solve_bwd(a, x):
    """Backward direction of solve(A, B, X): A ground, X ground → B = A @ X."""
    return _np.dot(a, x)


solve = _pred_bidir("solve",
    (3, _bidir_dispatch(make_quantity_aware(_la_fn("solve"), _solve_units), _solve_bwd, n_fixed=1)),
    (4, _dispatch_fn(make_quantity_aware(
        lambda a, b, assume_a: _la().solve(a, b, assume_a=assume_a), _solve_units))),
)

least_squares = _pred("least_squares",
    (3, _dispatch_fn(make_quantity_aware(
        lambda a, b: dict(zip(("x", "residuals", "rank", "s"), _la().lstsq(a, b))),
        _lstsq_units))),
)

solve_triangular = _pred("solve_triangular",
    (3, _dispatch_fn(make_quantity_aware(_la_fn("solve_triangular"), _solve_units))),
    (4, _dispatch_fn(make_quantity_aware(
        lambda a, b, lower: _la().solve_triangular(a, b, lower=lower), _solve_units))),
)


# ── Decomposition recomposition helpers ───────────────────────────────────

def _qr_bwd(result_dict):
    """A = Q @ R."""
    return _np.dot(result_dict['q'], result_dict['r'])


def _svd_bwd(result_dict):
    """A = U @ diag(s) @ Vh."""
    return _np.dot(result_dict['u'],
           _np.dot(_np.diag(result_dict['s']), result_dict['vh']))


def _lu_bwd(result_dict):
    """A = P @ L @ U."""
    return _np.dot(result_dict['p'],
           _np.dot(result_dict['l'], result_dict['u']))


def _eigen_bwd(result_dict):
    """A = V @ diag(λ) @ inv(V)."""
    v   = result_dict['eigenvectors']
    lam = result_dict['eigenvalues']
    return _np.dot(v, _np.dot(_np.diag(lam), _np.linalg.inv(v)))


def _schur_bwd(result_dict):
    """A = Z @ T @ Z.H"""
    t, z = result_dict['t'], result_dict['z']
    return _np.dot(z, _np.dot(t, z.conj().T))


def _cholesky_bwd(r):
    """A = R.T @ R  (upper triangular factor)."""
    return _np.dot(r.T, r)


# ── Matrix decompositions ─────────────────────────────────────────────────

lu_decompose = _pred_bidir("lu_decompose",
    (2, _bidir_dispatch(
            make_quantity_aware(lambda a: dict(zip(("p", "l", "u"), _la().lu(a))), STRIP_TO_PLAIN),
            _lu_bwd)),
)

qr_decompose = _pred_bidir("qr_decompose",
    (2, _bidir_dispatch(
            make_quantity_aware(lambda a: dict(zip(("q", "r"), _la().qr(a))), _qr_units),
            _qr_bwd)),
)

singular_value_decompose = _pred_bidir("singular_value_decompose",
    (2, _bidir_dispatch(
            make_quantity_aware(lambda a: dict(zip(("u", "s", "vh"), _la().svd(a))), _svd_units),
            _svd_bwd)),
)

cholesky = _pred_bidir("cholesky",
    (2, _bidir_dispatch(
            make_quantity_aware(_la_kw("cholesky", lower=False), REQUIRE_DIMENSIONLESS),
            _cholesky_bwd)),
    (3, _dispatch_fn(make_quantity_aware(
        lambda a, lower: _la().cholesky(a, lower=lower), REQUIRE_DIMENSIONLESS))),
)

eigen_decompose = _pred_bidir("eigen_decompose",
    (2, _bidir_dispatch(
            make_quantity_aware(
                lambda a: dict(zip(("eigenvalues", "eigenvectors"), _la().eig(a))),
                _eigen_units),
            _eigen_bwd)),
)

eigen_decompose_hermitian = _pred_bidir("eigen_decompose_hermitian",
    (2, _bidir_dispatch(
            make_quantity_aware(
                lambda a: dict(zip(("eigenvalues", "eigenvectors"), _la().eigh(a))),
                _eigen_units),
            _eigen_bwd)),
)

schur = _pred_bidir("schur",
    (2, _bidir_dispatch(
            make_quantity_aware(
                lambda a: dict(zip(("t", "z"), _la().schur(a))),
                _schur_units),
            _schur_bwd)),
    (3, _dispatch_fn(make_quantity_aware(
        lambda a, output: dict(zip(("t", "z"), _la().schur(a, output=output))),
        _schur_units))),
)


# ── Matrix functions ──────────────────────────────────────────────────────

inverse = _pred_bidir("inverse",
    (2, _bidir_dispatch(make_quantity_aware(_la_fn("inv"), _inverse_units), _la_fn("inv"))),
)

pseudo_inverse = _pred("pseudo_inverse",
    (2, _dispatch_fn(make_quantity_aware(_la_fn("pinv"), _inverse_units))),
)

determinant = _pred("determinant",
    (2, _dispatch_fn(_det_call(_la_fn("det")))),
)

norm = _pred("norm",
    (2, _dispatch_fn(make_quantity_aware(_la_fn("norm"), PASS_THROUGH_FIRST))),
    (3, _dispatch_fn(make_quantity_aware(lambda a, ord: _la().norm(a, ord=ord), PASS_THROUGH_FIRST))),
)

matrix_exp_log = _pred_bidir("matrix_exp_log",
    (2, _bidir_dispatch(
            make_quantity_aware(_la_fn("expm"), REQUIRE_DIMENSIONLESS),
            _la_fn("logm"))),
)

matrix_square_root = _pred("matrix_square_root",
    (2, _dispatch_fn(make_quantity_aware(_la_fn("sqrtm"), REQUIRE_DIMENSIONLESS))),
)

matrix_function = _pred("matrix_function",
    (3, _dispatch_fn(make_quantity_aware(lambda a, func: _la().funm(a, func), REQUIRE_DIMENSIONLESS))),
)


# ── Two-step factorisation helpers ────────────────────────────────────────

lu_factor = _pred("lu_factor",
    (2, _dispatch_fn(make_quantity_aware(_la_fn("lu_factor"), STRIP_TO_PLAIN))),
)

lu_solve = _pred("lu_solve",
    # lu_piv is an opaque tuple (no dims); x dims = b_dims via _solve_units
    (3, _dispatch_fn(make_quantity_aware(
        lambda lu_piv, b: _la().lu_solve(lu_piv, b), _solve_units))),
)

cholesky_factor = _pred("cholesky_factor",
    (2, _dispatch_fn(make_quantity_aware(_la_fn("cho_factor"), REQUIRE_DIMENSIONLESS))),
)

cholesky_solve = _pred("cholesky_solve",
    # c_lower is an opaque tuple (no dims); x dims = b_dims via _solve_units
    (3, _dispatch_fn(make_quantity_aware(
        lambda c_lower, b: _la().cho_solve(c_lower, b), _solve_units))),
)


# ── Helper: result_get ─────────────────────────────────────────────────────

class _ResultGetPredicate:
    """result_get(RESULT, FIELD, VALUE) — extract RESULT[FIELD] → VALUE.

    RESULT must be a dict (as produced by Tier 2 predicates).
    FIELD must be a ground string key.
    VALUE is unified with the retrieved value.
    """

    def _get_dispatch(self) -> Callable:
        return self._dispatch

    def _dispatch(self, this_generator, _proceed, _fail, _catcher, result, field, value, trail):
        result = deref(result)
        field = deref(field)
        if not isinstance(result, dict) or not isinstance(field, str):
            yield (_fail, DONE)
            return
        if field not in result:
            yield (_fail, DONE)
            return
        try:
            ok = bool(unify(value, result[field], trail))
        except (ValueError, TypeError):
            ok = False
        if ok:
            yield (_proceed, None)
        yield (_fail, DONE)

    def __repr__(self) -> str:
        return "result_get/3"


result_get = _ResultGetPredicate()
