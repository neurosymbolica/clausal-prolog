"""clausal.modules.py.scipy_special — scipy.special predicates for Clausal.

Provides mathematical special functions from scipy.special as importable
predicate objects for use in .clausal files via::

    -import_from(py.scipy_special, [gamma, Erf, bessel_j, elliptic_k, ...])

All predicates are **Tier 1 — pure functions**: accept scalar or NumPy array
inputs (broadcasting handled by scipy) and unify the last argument with the
result.

Predicate catalogue
-------------------
gamma/related:
    gamma(X, RESULT)
    gamma_log(X, RESULT)              # log Γ(x), more numerically stable
    gamma_sign(X, RESULT)             # sign of Γ(x)
    beta_log(A, B, RESULT)            # log B(a,b)
    digamma(X, RESULT)               # ψ(x) = Γ'(x)/Γ(x)
    polygamma(N, X, RESULT)          # ψ^(n)(x)
    factorial(N, RESULT)  /  factorial(N, EXACT, RESULT)
    comb(N, K, RESULT)  /  comb(N, K, EXACT, RESULT)  /  comb(N, K, EXACT, REPETITION, RESULT)
    perm(N, K, RESULT)  /  perm(N, K, EXACT, RESULT)

Error functions (bidirectional):
    Erf(X, Y)                        # forward: erf(x); backward: erfinv(y)
    ErfComplement(X, Y)              # forward: erfc(x); backward: erfcinv(y)
    NormalCdf(X, P)                  # forward: Φ(x); backward: Φ⁻¹(p) (probit)

bessel functions:
    bessel_j(N, X, RESULT)            # J_n(x), integer order
    bessel_y(N, X, RESULT)            # Y_n(x), integer order
    bessel_j_real(V, Z, RESULT)        # J_v(z), real order
    bessel_y_real(V, Z, RESULT)        # Y_v(z), real order
    bessel_k(N, X, RESULT)            # K_n(x), modified bessel of 2nd kind
    bessel_i(V, X, RESULT)            # I_v(x), modified bessel of 1st kind
    bessel_j_zeros(N, NT, RESULT)      # first NT zeros of J_n
    spherical_bessel_j(N, Z, RESULT)  /  spherical_bessel_j(N, Z, DERIVATIVE, RESULT)

elliptic integrals:
    elliptic_k(M, RESULT)             # complete elliptic integral K(m)
    elliptic_e(M, RESULT)             # complete elliptic integral E(m)
    elliptic_k_incomplete(PHI, M, RESULT)
    elliptic_e_incomplete(PHI, M, RESULT)

Hypergeometric:
    hypergeometric_1f1(A, B, X, RESULT)    # confluent hypergeometric ₁F₁
    hypergeometric_2f1(A, B, C, Z, RESULT) # Gauss hypergeometric ₂F₁
    hypergeometric_0f1(B, X, RESULT)       # ₀F₁

Information theory:
    entr(X, RESULT)                  # -x·log(x); entropy element-wise
    kl_divergence(X, Y, RESULT)       # Kullback-Leibler divergence element
    log_sum_exp(A, RESULT)  /  log_sum_exp(A, AXIS, B, KEEPDIMS, RESULT)

Orthogonal polynomials:
    assoc_legendre(M, V, X, RESULT)   # associated Legendre P_m^v(x)
    legendre_poly(N, X, RESULT)       # Legendre polynomial P_n(x)
    chebyshev_t(N, X, RESULT)         # Chebyshev polynomial of 1st kind T_n(x)
    chebyshev_u(N, X, RESULT)         # Chebyshev polynomial of 2nd kind U_n(x)
    hermite_h(N, X, RESULT)           # Hermite polynomial H_n(x)
    generalized_laguerre(N, ALPHA, X, RESULT)  # generalised Laguerre L_n^α(x)

Convenience / misc:
    cube_root(X, RESULT)              # x^(1/3), works for negative x
    exp10(X, RESULT)                 # 10^x
    exp2(X, RESULT)                  # 2^x
    Logit(X, Y)                      # bidirectional: logit(x) / expit(y) (sigmoid)
    lambert_w(Z, RESULT)  /  lambert_w(Z, K, TOL, RESULT)
    x_log_y(X, Y, RESULT)              # x·log(y), safe at x=0
    x_log1p_y(X, Y, RESULT)            # x·log(1+y), safe at x=0, y=-1
"""

from __future__ import annotations

import threading as _threading
from typing import Any, Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate
from clausal.modules.py._scipy_relations import _bidir_dispatch
from clausal.modules.py._scipy_units import make_quantity_aware, REQUIRE_DIMENSIONLESS


# ── Lazy scipy.special import ─────────────────────────────────────────────

_scipy_special = None
_sp_lock = _threading.Lock()


def _ensure_sp():
    global _scipy_special
    if _scipy_special is not None:
        return
    with _sp_lock:
        if _scipy_special is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_special = _import_stdlib("scipy.special")


def _sp():
    _ensure_sp()
    return _scipy_special


# ── Dispatch function factory ────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Build a trampoline dispatch function.

    ``call`` receives the dereffed positional inputs (all args except RESULT
    and trail) and should return the scalar/array result.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        # args layout: (input_0, ..., input_{n-1}, result_var, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        out = call(*inputs)
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _sp_fn(attr: str) -> Callable:
    """Return a callable that lazily calls ``scipy.special.<attr>(*args)``."""
    def call(*args):
        return getattr(_sp(), attr)(*args)
    return call


def _sp_kw(attr: str, **fixed_kwargs) -> Callable:
    """Return a callable that calls ``scipy.special.<attr>`` with fixed keyword args."""
    def call(*args):
        return getattr(_sp(), attr)(*args, **fixed_kwargs)
    return call


def _pred_bidir(name: str, *arity_dispatches) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, dispatch_fn) pairs.

    ``dispatch_fn`` is an already-constructed trampoline function (the output
    of ``_bidir_dispatch(...)``), not a raw callable.
    """
    p = ModulePredicate(name)
    for arity, dispatch_fn in arity_dispatches:
        p._dispatch_fns[arity] = dispatch_fn
    return p


def _pred(name: str, *arity_calls) -> ModulePredicate:
    """Create a ``ModulePredicate`` from (arity, callable) pairs.

    ``arity`` is the total number of predicate arguments including RESULT
    but NOT trail.  ``callable`` receives just the *input* arguments
    (i.e. all args except RESULT) and returns the scipy result.

    All callables are wrapped with :func:`make_quantity_aware` using the
    :data:`~clausal.modules._scipy_units.REQUIRE_DIMENSIONLESS` propagator:
    special functions require dimensionless arguments.
    """
    p = ModulePredicate(name)
    for arity, call in arity_calls:
        p._register(arity, _dispatch_fn(make_quantity_aware(call, REQUIRE_DIMENSIONLESS)))
    return p


def _bidir_q(fwd, bwd, n_fixed=0):
    """Like :func:`_bidir_dispatch` but wraps both callables with REQUIRE_DIMENSIONLESS."""
    return _bidir_dispatch(
        make_quantity_aware(fwd, REQUIRE_DIMENSIONLESS),
        make_quantity_aware(bwd, REQUIRE_DIMENSIONLESS),
        n_fixed=n_fixed,
    )


# ── gamma and related ────────────────────────────────────────────────────

gamma = _pred("gamma",
    (2, _sp_fn("gamma")),
)

gamma_log = _pred("gamma_log",
    (2, _sp_fn("gammaln")),
)

gamma_sign = _pred("gamma_sign",
    (2, _sp_fn("gammasgn")),
)

beta_log = _pred("beta_log",
    (3, _sp_fn("betaln")),
)

digamma = _pred("digamma",
    (2, _sp_fn("digamma")),
)

polygamma = _pred("polygamma",
    (3, _sp_fn("polygamma")),
)

factorial = _pred("factorial",
    (2, _sp_kw("factorial", exact=False)),
    (3, lambda n, exact: _sp().factorial(n, exact=exact)),
)

comb = _pred("comb",
    (3, _sp_kw("comb", exact=False, repetition=False)),
    (4, lambda n, k, exact: _sp().comb(n, k, exact=exact, repetition=False)),
    (5, lambda n, k, exact, rep: _sp().comb(n, k, exact=exact, repetition=rep)),
)

perm = _pred("perm",
    (3, _sp_kw("perm", exact=False)),
    (4, lambda n, k, exact: _sp().perm(n, k, exact=exact)),
)


# ── Error functions ───────────────────────────────────────────────────────

Erf = _pred_bidir("Erf",
    (2, _bidir_q(_sp_fn("erf"), _sp_fn("erfinv"))),
)

ErfComplement = _pred_bidir("ErfComplement",
    (2, _bidir_q(_sp_fn("erfc"), _sp_fn("erfcinv"))),
)

NormalCdf = _pred_bidir("NormalCdf",
    (2, _bidir_q(_sp_fn("ndtr"), _sp_fn("ndtri"))),
)



# ── bessel functions ──────────────────────────────────────────────────────

bessel_j = _pred("bessel_j",
    (3, _sp_fn("jn")),
)

bessel_y = _pred("bessel_y",
    (3, _sp_fn("yn")),
)

bessel_j_real = _pred("bessel_j_real",
    (3, _sp_fn("jv")),
)

bessel_y_real = _pred("bessel_y_real",
    (3, _sp_fn("yv")),
)

bessel_k = _pred("bessel_k",
    (3, _sp_fn("kn")),
)

# scipy uses iv (not in) for modified bessel I; bessel_i is the readable name
bessel_i = _pred("bessel_i",
    (3, _sp_fn("iv")),
)

bessel_j_zeros = _pred("bessel_j_zeros",
    (3, _sp_fn("jn_zeros")),
)

spherical_bessel_j = _pred("spherical_bessel_j",
    (3, _sp_kw("spherical_jn", derivative=False)),
    (4, lambda n, z, deriv: _sp().spherical_jn(n, z, derivative=deriv)),
)


# ── elliptic integrals ────────────────────────────────────────────────────

elliptic_k = _pred("elliptic_k",
    (2, _sp_fn("ellipk")),
)

elliptic_e = _pred("elliptic_e",
    (2, _sp_fn("ellipe")),
)

elliptic_k_incomplete = _pred("elliptic_k_incomplete",
    (3, _sp_fn("ellipkinc")),
)

elliptic_e_incomplete = _pred("elliptic_e_incomplete",
    (3, _sp_fn("ellipeinc")),
)


# ── Hypergeometric ────────────────────────────────────────────────────────

hypergeometric_1f1 = _pred("hypergeometric_1f1",
    (4, _sp_fn("hyp1f1")),
)

hypergeometric_2f1 = _pred("hypergeometric_2f1",
    (5, _sp_fn("hyp2f1")),
)

hypergeometric_0f1 = _pred("hypergeometric_0f1",
    (3, _sp_fn("hyp0f1")),
)


# ── Information theory ────────────────────────────────────────────────────

entr = _pred("entr",
    (2, _sp_fn("entr")),
)

kl_divergence = _pred("kl_divergence",
    (3, _sp_fn("kl_div")),
)

log_sum_exp = _pred("log_sum_exp",
    (2, _sp_fn("logsumexp")),
    (5, lambda a, axis, b, keepdims:
        _sp().logsumexp(a, axis=axis, b=b, keepdims=keepdims)),
)


# ── Orthogonal polynomials ────────────────────────────────────────────────

assoc_legendre = _pred("assoc_legendre",
    (4, _sp_fn("lpmv")),
)

legendre_poly = _pred("legendre_poly",
    (3, _sp_fn("eval_legendre")),
)

chebyshev_t = _pred("chebyshev_t",
    (3, _sp_fn("eval_chebyt")),
)

chebyshev_u = _pred("chebyshev_u",
    (3, _sp_fn("eval_chebyu")),
)

hermite_h = _pred("hermite_h",
    (3, _sp_fn("eval_hermite")),
)

generalized_laguerre = _pred("generalized_laguerre",
    (4, _sp_fn("eval_genlaguerre")),
)


# ── Convenience / misc ────────────────────────────────────────────────────

cube_root = _pred("cube_root",
    (2, _sp_fn("cbrt")),
)

exp10 = _pred("exp10",
    (2, _sp_fn("exp10")),
)

exp2 = _pred("exp2",
    (2, _sp_fn("exp2")),
)

Logit = _pred_bidir("Logit",
    (2, _bidir_q(_sp_fn("logit"), _sp_fn("expit"))),
)


# ── Incomplete gamma / beta / Box-Cox ─────────────────────────────────────

GammaInc = _pred_bidir("GammaInc",
    (3, _bidir_q(_sp_fn("gammainc"), _sp_fn("gammaincinv"), n_fixed=1)),
)

GammaIncComplement = _pred_bidir("GammaIncComplement",
    (3, _bidir_q(_sp_fn("gammaincc"), _sp_fn("gammainccinv"), n_fixed=1)),
)

BetaInc = _pred_bidir("BetaInc",
    (4, _bidir_q(_sp_fn("betainc"), _sp_fn("betaincinv"), n_fixed=2)),
)

Boxcox = _pred_bidir("Boxcox",
    (3, _bidir_q(
            lambda lam, x: _sp().boxcox(x, lam),
            lambda lam, y: _sp().inv_boxcox(y, lam),
            n_fixed=1)),
)

Boxcox1p = _pred_bidir("Boxcox1p",
    (3, _bidir_q(
            lambda lam, x: _sp().boxcox1p(x, lam),
            lambda lam, y: _sp().inv_boxcox1p(y, lam),
            n_fixed=1)),
)

lambert_w = _pred("lambert_w",
    (2, _sp_kw("lambertw", k=0, tol=1e-8)),
    (4, lambda z, k, tol: _sp().lambertw(z, k=k, tol=tol)),
)

x_log_y = _pred("x_log_y",
    (3, _sp_fn("xlogy")),
)

x_log1p_y = _pred("x_log1p_y",
    (3, _sp_fn("xlog1py")),
)
