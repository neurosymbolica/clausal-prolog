"""clausal.modules.jax_scipy — jax.scipy predicates for Clausal.

Wraps ``jax.scipy.special`` (special mathematical functions) and
``jax.scipy.stats`` (probability distribution shapes) as pure
predicates. This is the JAX-native parallel to ``py.scipy_special`` /
``py.scipy_stats``: same math, different array type —
``jax.Array`` instead of ``numpy.ndarray``.

Why duplicate scipy? Because working with jax.Array, the user gets
``jax.grad``, ``jax.jit``, and GPU/TPU execution — none of which the
numpy-backed scipy functions support. For autodiff through a
log-likelihood, ``jax.scipy.stats.norm.logpdf`` is mandatory; calling
scipy would coerce to numpy and break the tracer chain.

Import usage::

    -import_from(py.jax_scipy, [
        gamma_fn, gammaln, digamma, erf, erfc, erfinv,
        expit, logit, i0, i1, i0e, i1e,
        logsumexp, beta_fn, betainc, polygamma,
        rel_entr, xlogy, zeta, factorial, multigammaln, spence,
        distribution,
        pdf, logpdf, cdf, logcdf, sf, logsf, ppf, pmf, logpmf,
    ])

Phase 11 — jax.scipy Special and Stats
----------------------------------------
All predicates are Tier 1 pure.

Special functions (all operate on jax.Array):
    gamma_fn(X, R)          Γ(x)   (renamed to avoid py.jax_random.gamma)
    gammaln(X, R)           log Γ(x), more stable
    digamma(X, R)           ψ(x) = Γ'(x)/Γ(x)
    erf(X, R)               Error function
    erfc(X, R)              Complementary error function
    erfinv(X, R)            Inverse error function
    expit(X, R)             1 / (1 + exp(-x))    (logistic sigmoid)
    logit(X, R)             log(x / (1 - x))     (inverse of expit)
    i0(X, R)                Modified Bessel I₀
    i1(X, R)                Modified Bessel I₁
    i0e(X, R)               Exponentially-scaled I₀
    i1e(X, R)               Exponentially-scaled I₁
    logsumexp(A, R)  /  logsumexp(A, AXIS, R)
    beta_fn(A, B, R)        B(a,b) = Γ(a)Γ(b)/Γ(a+b) — renamed
    betainc(A, B, X, R)     Regularised incomplete beta
    polygamma(N, X, R)      ψ^(n)(x)
    rel_entr(P, Q, R)       Relative entropy element
    xlogy(X, Y, R)          x·log(y), safe at x=0
    zeta(X, Q, R)           Hurwitz zeta ζ(x, q)
    factorial(N, R)         n! via gamma
    multigammaln(A, D, R)   log of multivariate gamma
    spence(X, R)            Spence's function (dilogarithm)

Distribution registry (nondeterministic):
    distribution(NAME, MODULE)   Enumerate jax.scipy.stats submodules

Distribution methods (all take a name string + value + params dict):
    pdf(DIST, X, PARAMS, R)        Probability density (continuous)
    logpdf(DIST, X, PARAMS, R)     Log density
    cdf(DIST, X, PARAMS, R)        CDF
    logcdf(DIST, X, PARAMS, R)     Log CDF
    sf(DIST, X, PARAMS, R)         Survival function = 1 - CDF
    logsf(DIST, X, PARAMS, R)      Log survival
    ppf(DIST, Q, PARAMS, R)        Inverse CDF (quantile)
    pmf(DIST, X, PARAMS, R)        Probability mass (discrete)
    logpmf(DIST, X, PARAMS, R)     Log mass

Example::

    pdf("norm", 0.0, {"loc": 0.0, "scale": 1.0}, P)
    # P ≈ 0.3989 (= 1 / sqrt(2π))

Name clashes
------------
``gamma`` and ``beta`` exist in three JAX namespaces: ``jax.random``
(samplers), ``jax.scipy.special`` (functions), ``jax.scipy.stats``
(distributions). Clausal predicates are module-scoped, so the clash is
only visible when a user imports both. To keep disambiguation explicit:

* ``gamma_fn`` / ``beta_fn`` — the special functions in this module.
* ``gamma`` / ``beta`` — stay as the sampler names in
  ``py.jax_random``.
* The distribution family uses the string atom ``"gamma"`` /
  ``"beta"`` via the ``pdf`` / ``logpdf`` / ... predicates, so no
  Clausal-level predicate is defined for them.

Not every distribution has every method
----------------------------------------
JAX's ``scipy.stats`` is a subset of scipy's. For instance,
``bernoulli`` has ``pmf`` but no ``pdf``; ``t`` has ``pdf``/``logpdf``
but no ``cdf``. When a method is missing for the requested
distribution, ``_pure``'s exception handler turns the
``AttributeError`` into predicate failure.
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import _pred, _pure, _fact_table_2
from clausal.modules.jax import _ensure_jax, logsumexp as _jax_logsumexp


# ── Lazy jax.scipy.special / jax.scipy.stats imports ──────────────────────

_jss_mod = None
_jst_mod = None
_js_lock = _threading.Lock()


def _jss():
    global _jss_mod
    if _jss_mod is not None:
        return _jss_mod
    with _js_lock:
        if _jss_mod is not None:
            return _jss_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jss_mod = _import_stdlib("jax.scipy.special")
    return _jss_mod


def _jst():
    global _jst_mod
    if _jst_mod is not None:
        return _jst_mod
    with _js_lock:
        if _jst_mod is not None:
            return _jst_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jst_mod = _import_stdlib("jax.scipy.stats")
    return _jst_mod


# ═══════════════════════════════════════════════════════════════════════════
# Special functions
# ═══════════════════════════════════════════════════════════════════════════

gamma_fn = _pred("gamma_fn",
    (2, _pure(lambda x: _jss().gamma(x))),
)

gammaln = _pred("gammaln",
    (2, _pure(lambda x: _jss().gammaln(x))),
)

digamma = _pred("digamma",
    (2, _pure(lambda x: _jss().digamma(x))),
)

erf = _pred("erf",
    (2, _pure(lambda x: _jss().erf(x))),
)

erfc = _pred("erfc",
    (2, _pure(lambda x: _jss().erfc(x))),
)

erfinv = _pred("erfinv",
    (2, _pure(lambda x: _jss().erfinv(x))),
)

expit = _pred("expit",
    (2, _pure(lambda x: _jss().expit(x))),
)

logit = _pred("logit",
    (2, _pure(lambda x: _jss().logit(x))),
)

i0 = _pred("i0",
    (2, _pure(lambda x: _jss().i0(x))),
)

i1 = _pred("i1",
    (2, _pure(lambda x: _jss().i1(x))),
)

i0e = _pred("i0e",
    (2, _pure(lambda x: _jss().i0e(x))),
)

i1e = _pred("i1e",
    (2, _pure(lambda x: _jss().i1e(x))),
)

# Alias the canonical implementation in py.jax to guarantee identical
# behaviour across `-import_from(py.jax, [logsumexp])` and
# `-import_from(py.jax_scipy, [logsumexp])`. See
# implementation_plans/jax/todo/jax_wrapper_followups.md#2.
logsumexp = _jax_logsumexp

beta_fn = _pred("beta_fn",
    (3, _pure(lambda a, b: _jss().beta(a, b))),
)

betainc = _pred("betainc",
    (4, _pure(lambda a, b, x: _jss().betainc(a, b, x))),
)

polygamma = _pred("polygamma",
    (3, _pure(lambda n, x: _jss().polygamma(int(n), x))),
)

rel_entr = _pred("rel_entr",
    (3, _pure(lambda p, q: _jss().rel_entr(p, q))),
)

xlogy = _pred("xlogy",
    (3, _pure(lambda x, y: _jss().xlogy(x, y))),
)

zeta = _pred("zeta",
    (3, _pure(lambda x, q: _jss().zeta(x, q))),
)

factorial = _pred("factorial",
    (2, _pure(lambda n: _jss().factorial(n))),
)

multigammaln = _pred("multigammaln",
    (3, _pure(lambda a, d: _jss().multigammaln(a, int(d)))),
)

spence = _pred("spence",
    (2, _pure(lambda x: _jss().spence(x))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Distribution registry
# ═══════════════════════════════════════════════════════════════════════════

_DISTRIBUTION_NAMES = (
    "norm", "uniform", "bernoulli", "beta", "binom",
    "cauchy", "chi2", "dirichlet", "expon", "gamma",
    "laplace", "logistic", "multinomial",
    "multivariate_normal", "nbinom", "pareto", "poisson",
    "t", "truncnorm", "vonmises", "wrapcauchy",
    "gennorm", "geom",
)


def _build_distribution_facts():
    jst = _jst()
    facts = []
    for name in _DISTRIBUTION_NAMES:
        mod = getattr(jst, name, None)
        if mod is not None:
            facts.append((name, mod))
    return facts


distribution = _pred("distribution",
    (2, _fact_table_2(_build_distribution_facts)),
)


# ═══════════════════════════════════════════════════════════════════════════
# Distribution methods — pdf / logpdf / cdf / logcdf / sf / logsf / ppf /
#                        pmf / logpmf
# ═══════════════════════════════════════════════════════════════════════════
#
# Each method dispatches on DIST (a string like "norm"), applies to X, and
# forwards PARAMS as kwargs (`{"loc": 0.0, "scale": 1.0}` → loc=0, scale=1).
#
# When the distribution lacks the requested method (e.g. `bernoulli.pdf`),
# `_pure`'s exception handler turns the AttributeError into predicate
# failure.

def _dispatch_method(method_name):
    def inner(dist_name, x, params):
        mod = getattr(_jst(), dist_name)
        fn = getattr(mod, method_name)
        return fn(x, **params)
    return inner


pdf = _pred("pdf",
    (4, _pure(_dispatch_method("pdf"))),
)

logpdf = _pred("logpdf",
    (4, _pure(_dispatch_method("logpdf"))),
)

cdf = _pred("cdf",
    (4, _pure(_dispatch_method("cdf"))),
)

logcdf = _pred("logcdf",
    (4, _pure(_dispatch_method("logcdf"))),
)

sf = _pred("sf",
    (4, _pure(_dispatch_method("sf"))),
)

logsf = _pred("logsf",
    (4, _pure(_dispatch_method("logsf"))),
)

ppf = _pred("ppf",
    (4, _pure(_dispatch_method("ppf"))),
)

pmf = _pred("pmf",
    (4, _pure(_dispatch_method("pmf"))),
)

logpmf = _pred("logpmf",
    (4, _pure(_dispatch_method("logpmf"))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Special functions
    "gamma_fn", "gammaln", "digamma",
    "erf", "erfc", "erfinv",
    "expit", "logit",
    "i0", "i1", "i0e", "i1e",
    "logsumexp",
    "beta_fn", "betainc",
    "polygamma",
    "rel_entr", "xlogy", "zeta",
    "factorial", "multigammaln", "spence",
    # Distribution registry
    "distribution",
    # Distribution methods
    "pdf", "logpdf", "cdf", "logcdf", "sf", "logsf", "ppf", "pmf", "logpmf",
]
