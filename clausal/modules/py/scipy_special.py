"""clausal.modules.py.scipy_special — scipy.special predicates for Clausal.

Provides mathematical special functions from scipy.special as importable
predicate objects for use in .clausal files via::

    -import_from(py.scipy_special, [Gamma, Erf, BesselJ, EllipticK, ...])

All predicates are **Tier 1 — pure functions**: accept scalar or NumPy array
inputs (broadcasting handled by scipy) and unify the last argument with the
result.

Predicate catalogue
-------------------
Gamma/related:
    Gamma(X, RESULT)
    GammaLog(X, RESULT)              # log Γ(x), more numerically stable
    GammaSign(X, RESULT)             # sign of Γ(x)
    BetaLog(A, B, RESULT)            # log B(a,b)
    Digamma(X, RESULT)               # ψ(x) = Γ'(x)/Γ(x)
    Polygamma(N, X, RESULT)          # ψ^(n)(x)
    Factorial(N, RESULT)  /  Factorial(N, EXACT, RESULT)
    Comb(N, K, RESULT)  /  Comb(N, K, EXACT, RESULT)  /  Comb(N, K, EXACT, REPETITION, RESULT)
    Perm(N, K, RESULT)  /  Perm(N, K, EXACT, RESULT)

Error functions:
    Erf(X, RESULT)
    ErfComplement(X, RESULT)         # 1 - erf(x)
    ErfInverse(Y, RESULT)            # inverse of erf
    ErfComplementInverse(Y, RESULT)  # inverse of erfc
    NormalCdf(X, RESULT)             # Φ(x), area under standard normal
    NormalCdfInverse(P, RESULT)      # Φ^{-1}(p), probit / quantile function

Bessel functions:
    BesselJ(N, X, RESULT)            # J_n(x), integer order
    BesselY(N, X, RESULT)            # Y_n(x), integer order
    BesselJReal(V, Z, RESULT)        # J_v(z), real order
    BesselYReal(V, Z, RESULT)        # Y_v(z), real order
    BesselK(N, X, RESULT)            # K_n(x), modified Bessel of 2nd kind
    BesselI(V, X, RESULT)            # I_v(x), modified Bessel of 1st kind
    BesselJZeros(N, NT, RESULT)      # first NT zeros of J_n
    SphericalBesselJ(N, Z, RESULT)  /  SphericalBesselJ(N, Z, DERIVATIVE, RESULT)

Elliptic integrals:
    EllipticK(M, RESULT)             # complete elliptic integral K(m)
    EllipticE(M, RESULT)             # complete elliptic integral E(m)
    EllipticKIncomplete(PHI, M, RESULT)
    EllipticEIncomplete(PHI, M, RESULT)

Hypergeometric:
    Hypergeometric1F1(A, B, X, RESULT)    # confluent hypergeometric ₁F₁
    Hypergeometric2F1(A, B, C, Z, RESULT) # Gauss hypergeometric ₂F₁
    Hypergeometric0F1(B, X, RESULT)       # ₀F₁

Information theory:
    Entr(X, RESULT)                  # -x·log(x); entropy element-wise
    KlDivergence(X, Y, RESULT)       # Kullback-Leibler divergence element
    LogSumExp(A, RESULT)  /  LogSumExp(A, AXIS, B, KEEPDIMS, RESULT)

Orthogonal polynomials:
    AssocLegendre(M, V, X, RESULT)   # associated Legendre P_m^v(x)
    LegendrePoly(N, X, RESULT)       # Legendre polynomial P_n(x)
    ChebyshevT(N, X, RESULT)         # Chebyshev polynomial of 1st kind T_n(x)
    ChebyshevU(N, X, RESULT)         # Chebyshev polynomial of 2nd kind U_n(x)
    HermiteH(N, X, RESULT)           # Hermite polynomial H_n(x)
    GeneralizedLaguerre(N, ALPHA, X, RESULT)  # generalised Laguerre L_n^α(x)

Convenience / misc:
    CubeRoot(X, RESULT)              # x^(1/3), works for negative x
    Exp10(X, RESULT)                 # 10^x
    Exp2(X, RESULT)                  # 2^x
    Sigmoid(X, RESULT)               # 1/(1+exp(-x)), logistic function
    Logit(X, RESULT)                 # log(x/(1-x))
    LambertW(Z, RESULT)  /  LambertW(Z, K, TOL, RESULT)
    XLogY(X, Y, RESULT)              # x·log(y), safe at x=0
    XLog1pY(X, Y, RESULT)            # x·log(1+y), safe at x=0, y=-1
"""

from __future__ import annotations

import threading as _threading
from typing import Any, Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
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


# ── Predicate adapter ────────────────────────────────────────────────────

class _ScipySpecialPredicate:
    """Dispatch adapter for a scipy.special predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "self":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # args includes trail as last element
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.special.{self._name}/{arities}"


# ── Dispatch function factory ────────────────────────────────────────────

def _dispatch_fn(call: Callable) -> Callable:
    """Build a trampoline dispatch function.

    ``call`` receives the dereffed positional inputs (all args except RESULT
    and trail) and should return the scalar/array result.
    """
    def dispatch(this_generator, parent, *args):
        # args layout: (input_0, ..., input_{n-1}, result_var, trail)
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        out = call(*inputs)
        if unify(result_var, out, trail):
            yield (parent, None)
        yield (parent, DONE)
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


def _pred_bidir(name: str, *arity_dispatches) -> _ScipySpecialPredicate:
    """Create a ``_ScipySpecialPredicate`` from (arity, dispatch_fn) pairs.

    ``dispatch_fn`` is an already-constructed trampoline function (the output
    of ``_bidir_dispatch(...)``), not a raw callable.
    """
    p = _ScipySpecialPredicate(name)
    for arity, dispatch_fn in arity_dispatches:
        p._dispatch_fns[arity] = dispatch_fn
    return p


def _pred(name: str, *arity_calls) -> _ScipySpecialPredicate:
    """Create a ``_ScipySpecialPredicate`` from (arity, callable) pairs.

    ``arity`` is the total number of predicate arguments including RESULT
    but NOT trail.  ``callable`` receives just the *input* arguments
    (i.e. all args except RESULT) and returns the scipy result.

    All callables are wrapped with :func:`make_quantity_aware` using the
    :data:`~clausal.modules.py._scipy_units.REQUIRE_DIMENSIONLESS` propagator:
    special functions require dimensionless arguments.
    """
    p = _ScipySpecialPredicate(name)
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


# ── Gamma and related ────────────────────────────────────────────────────

Gamma = _pred("Gamma",
    (2, _sp_fn("gamma")),
)

GammaLog = _pred("GammaLog",
    (2, _sp_fn("gammaln")),
)

GammaSign = _pred("GammaSign",
    (2, _sp_fn("gammasgn")),
)

BetaLog = _pred("BetaLog",
    (3, _sp_fn("betaln")),
)

Digamma = _pred("Digamma",
    (2, _sp_fn("digamma")),
)

Polygamma = _pred("Polygamma",
    (3, _sp_fn("polygamma")),
)

Factorial = _pred("Factorial",
    (2, _sp_kw("factorial", exact=False)),
    (3, lambda n, exact: _sp().factorial(n, exact=exact)),
)

Comb = _pred("Comb",
    (3, _sp_kw("comb", exact=False, repetition=False)),
    (4, lambda n, k, exact: _sp().comb(n, k, exact=exact, repetition=False)),
    (5, lambda n, k, exact, rep: _sp().comb(n, k, exact=exact, repetition=rep)),
)

Perm = _pred("Perm",
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

# Backward-compatibility aliases — kept unidirectional:
ErfInverse = _pred("ErfInverse",
    (2, _sp_fn("erfinv")),
)

ErfComplementInverse = _pred("ErfComplementInverse",
    (2, _sp_fn("erfcinv")),
)

NormalCdf = _pred_bidir("NormalCdf",
    (2, _bidir_q(_sp_fn("ndtr"), _sp_fn("ndtri"))),
)

# Backward-compatibility alias — kept unidirectional:
NormalCdfInverse = _pred("NormalCdfInverse",
    (2, _sp_fn("ndtri")),
)


# ── Bessel functions ──────────────────────────────────────────────────────

BesselJ = _pred("BesselJ",
    (3, _sp_fn("jn")),
)

BesselY = _pred("BesselY",
    (3, _sp_fn("yn")),
)

BesselJReal = _pred("BesselJReal",
    (3, _sp_fn("jv")),
)

BesselYReal = _pred("BesselYReal",
    (3, _sp_fn("yv")),
)

BesselK = _pred("BesselK",
    (3, _sp_fn("kn")),
)

# scipy uses iv (not in) for modified Bessel I; BesselI is the readable name
BesselI = _pred("BesselI",
    (3, _sp_fn("iv")),
)

BesselJZeros = _pred("BesselJZeros",
    (3, _sp_fn("jn_zeros")),
)

SphericalBesselJ = _pred("SphericalBesselJ",
    (3, _sp_kw("spherical_jn", derivative=False)),
    (4, lambda n, z, deriv: _sp().spherical_jn(n, z, derivative=deriv)),
)


# ── Elliptic integrals ────────────────────────────────────────────────────

EllipticK = _pred("EllipticK",
    (2, _sp_fn("ellipk")),
)

EllipticE = _pred("EllipticE",
    (2, _sp_fn("ellipe")),
)

EllipticKIncomplete = _pred("EllipticKIncomplete",
    (3, _sp_fn("ellipkinc")),
)

EllipticEIncomplete = _pred("EllipticEIncomplete",
    (3, _sp_fn("ellipeinc")),
)


# ── Hypergeometric ────────────────────────────────────────────────────────

Hypergeometric1F1 = _pred("Hypergeometric1F1",
    (4, _sp_fn("hyp1f1")),
)

Hypergeometric2F1 = _pred("Hypergeometric2F1",
    (5, _sp_fn("hyp2f1")),
)

Hypergeometric0F1 = _pred("Hypergeometric0F1",
    (3, _sp_fn("hyp0f1")),
)


# ── Information theory ────────────────────────────────────────────────────

Entr = _pred("Entr",
    (2, _sp_fn("entr")),
)

KlDivergence = _pred("KlDivergence",
    (3, _sp_fn("kl_div")),
)

LogSumExp = _pred("LogSumExp",
    (2, _sp_fn("logsumexp")),
    (5, lambda a, axis, b, keepdims:
        _sp().logsumexp(a, axis=axis, b=b, keepdims=keepdims)),
)


# ── Orthogonal polynomials ────────────────────────────────────────────────

AssocLegendre = _pred("AssocLegendre",
    (4, _sp_fn("lpmv")),
)

LegendrePoly = _pred("LegendrePoly",
    (3, _sp_fn("eval_legendre")),
)

ChebyshevT = _pred("ChebyshevT",
    (3, _sp_fn("eval_chebyt")),
)

ChebyshevU = _pred("ChebyshevU",
    (3, _sp_fn("eval_chebyu")),
)

HermiteH = _pred("HermiteH",
    (3, _sp_fn("eval_hermite")),
)

GeneralizedLaguerre = _pred("GeneralizedLaguerre",
    (4, _sp_fn("eval_genlaguerre")),
)


# ── Convenience / misc ────────────────────────────────────────────────────

CubeRoot = _pred("CubeRoot",
    (2, _sp_fn("cbrt")),
)

Exp10 = _pred("Exp10",
    (2, _sp_fn("exp10")),
)

Exp2 = _pred("Exp2",
    (2, _sp_fn("exp2")),
)

Sigmoid = _pred("Sigmoid",
    (2, _sp_fn("expit")),
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

LambertW = _pred("LambertW",
    (2, _sp_kw("lambertw", k=0, tol=1e-8)),
    (4, lambda z, k, tol: _sp().lambertw(z, k=k, tol=tol)),
)

XLogY = _pred("XLogY",
    (3, _sp_fn("xlogy")),
)

XLog1pY = _pred("XLog1pY",
    (3, _sp_fn("xlog1py")),
)
