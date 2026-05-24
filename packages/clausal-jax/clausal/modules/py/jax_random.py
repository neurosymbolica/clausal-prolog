"""clausal.modules.py.jax_random — JAX PRNG predicates for Clausal.

JAX refuses to hide randomness in a global: every sampler takes an explicit
``PRNGKey`` and consumes it deterministically. That matches Clausal's
state-threading discipline exactly — consume a key, produce a sample; if
backtracking abandons the sample, the pre-split key is still valid.

Import usage::

    -import_from(py.jax_random, [
        key, split_key, fold_in, key_bytes,
        normal, uniform, bernoulli, categorical,
        poisson, gamma, beta, exponential, dirichlet,
        multivariate_normal, permutation, choice,
        randint, truncated_normal,
        sampler,
    ])

Phase 2 — PRNG Keys and Randomness
------------------------------------

Key primitives:
    key(SEED, K)                        Create a typed PRNGKey from an integer
    split_key(K, KEYS)                  Split into 2 subkeys (a Python list)
    split_key(K, N, KEYS)               Split into N subkeys
    fold_in(K, DATA, K2)                Fold an integer into a key
    key_bytes(K, BYTES)                 Bijective: typed key <-> uint32[2]

Samplers (all Tier 1 pure — state-threaded through the key):
    normal(K, SHAPE, A) / normal(K, SHAPE, OPTS, A)
    uniform(K, SHAPE, A) / uniform(K, SHAPE, OPTS, A)
      / uniform(K, SHAPE, MIN, MAX, A)
    bernoulli(K, P, A) / bernoulli(K, P, SHAPE, A)
    categorical(K, LOGITS, A) / categorical(K, LOGITS, AXIS, A)
    poisson(K, LAM, A) / poisson(K, LAM, SHAPE, A)
    gamma(K, A_PARAM, A) / gamma(K, A_PARAM, SHAPE, A)
    beta(K, A_PARAM, B_PARAM, A) / beta(K, A_PARAM, B_PARAM, SHAPE, A)
    exponential(K, A) / exponential(K, SHAPE, A)
    dirichlet(K, ALPHA, A) / dirichlet(K, ALPHA, SHAPE, A)
    multivariate_normal(K, MEAN, COV, A)
      / multivariate_normal(K, MEAN, COV, SHAPE, A)
    permutation(K, X, A)
    choice(K, X, SHAPE, A) / choice(K, X, SHAPE, OPTS, A)
    randint(K, SHAPE, MIN, MAX, A)
    truncated_normal(K, LOWER, UPPER, SHAPE, A)

Sampler registry:
    sampler(NAME, FN)   Enumerate or look up samplers in jax.random
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import (
    _pred, _pure, _bidir_2, _fact_table_2,
)
from clausal.modules.py.jax import _ensure_jax


# ── Lazy jax.random import ───────────────────────────────────────────────

_jr_mod = None
_jr_lock = _threading.Lock()


def _jr():
    global _jr_mod
    if _jr_mod is not None:
        return _jr_mod
    with _jr_lock:
        if _jr_mod is not None:
            return _jr_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jr_mod = _import_stdlib("jax.random")
    return _jr_mod


# ═══════════════════════════════════════════════════════════════════════════
# Key primitives
# ═══════════════════════════════════════════════════════════════════════════

key = _pred("key",
    (2, _pure(lambda seed: _jr().key(int(seed)))),
)


def _split_2(k):
    sub = _jr().split(k, 2)
    return [sub[0], sub[1]]


def _split_3(k, n):
    sub = _jr().split(k, int(n))
    return [sub[i] for i in range(int(n))]


split_key = _pred("split_key",
    (2, _pure(_split_2)),
    (3, _pure(_split_3)),
)

fold_in = _pred("fold_in",
    (3, _pure(lambda k, data: _jr().fold_in(k, int(data)))),
)

key_bytes = _pred("key_bytes",
    (2, _bidir_2(
        forward=lambda k: _jr().key_data(k),
        backward=lambda b: _jr().wrap_key_data(b),
    )),
)


# ═══════════════════════════════════════════════════════════════════════════
# Samplers
# ═══════════════════════════════════════════════════════════════════════════

normal = _pred("normal",
    (3, _pure(lambda k, shape: _jr().normal(k, shape))),
    (4, _pure(lambda k, shape, opts: _jr().normal(k, shape, **opts))),
)

uniform = _pred("uniform",
    (3, _pure(lambda k, shape: _jr().uniform(k, shape))),
    (4, _pure(lambda k, shape, opts: _jr().uniform(k, shape, **opts))),
    (5, _pure(lambda k, shape, minval, maxval:
              _jr().uniform(k, shape, minval=minval, maxval=maxval))),
)

bernoulli = _pred("bernoulli",
    (3, _pure(lambda k, p: _jr().bernoulli(k, p))),
    (4, _pure(lambda k, p, shape: _jr().bernoulli(k, p, shape))),
)

categorical = _pred("categorical",
    (3, _pure(lambda k, logits: _jr().categorical(k, logits))),
    (4, _pure(lambda k, logits, axis: _jr().categorical(k, logits, axis=int(axis)))),
)

poisson = _pred("poisson",
    (3, _pure(lambda k, lam: _jr().poisson(k, lam))),
    (4, _pure(lambda k, lam, shape: _jr().poisson(k, lam, shape))),
)

gamma = _pred("gamma",
    (3, _pure(lambda k, a: _jr().gamma(k, a))),
    (4, _pure(lambda k, a, shape: _jr().gamma(k, a, shape))),
)

beta = _pred("beta",
    (4, _pure(lambda k, a, b: _jr().beta(k, a, b))),
    (5, _pure(lambda k, a, b, shape: _jr().beta(k, a, b, shape))),
)

exponential = _pred("exponential",
    (2, _pure(lambda k: _jr().exponential(k))),
    (3, _pure(lambda k, shape: _jr().exponential(k, shape))),
)

dirichlet = _pred("dirichlet",
    (3, _pure(lambda k, alpha: _jr().dirichlet(k, alpha))),
    (4, _pure(lambda k, alpha, shape: _jr().dirichlet(k, alpha, shape))),
)

multivariate_normal = _pred("multivariate_normal",
    (4, _pure(lambda k, mean, cov: _jr().multivariate_normal(k, mean, cov))),
    (5, _pure(lambda k, mean, cov, shape:
              _jr().multivariate_normal(k, mean, cov, shape))),
)

permutation = _pred("permutation",
    (3, _pure(lambda k, x: _jr().permutation(k, x))),
)

choice = _pred("choice",
    (4, _pure(lambda k, x, shape: _jr().choice(k, x, shape=shape))),
    (5, _pure(lambda k, x, shape, opts: _jr().choice(k, x, shape=shape, **opts))),
)

randint = _pred("randint",
    (5, _pure(lambda k, shape, minval, maxval:
              _jr().randint(k, shape, int(minval), int(maxval)))),
)

truncated_normal = _pred("truncated_normal",
    (5, _pure(lambda k, lower, upper, shape:
              _jr().truncated_normal(k, float(lower), float(upper), shape))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Sampler registry
# ═══════════════════════════════════════════════════════════════════════════

_SAMPLER_NAMES = [
    "ball", "bernoulli", "beta", "binomial", "categorical", "cauchy",
    "chisquare", "choice", "dirichlet", "double_sided_maxwell",
    "exponential", "f", "gamma", "generalized_normal", "geometric",
    "gumbel", "laplace", "logistic", "loggamma", "lognormal",
    "maxwell", "multivariate_normal", "normal", "orthogonal", "pareto",
    "permutation", "poisson", "rademacher", "randint", "rayleigh",
    "t", "triangular", "truncated_normal", "uniform", "wald",
    "weibull_min",
]


def _build_sampler_facts():
    jr = _jr()
    facts = []
    for name in _SAMPLER_NAMES:
        fn = getattr(jr, name, None)
        if fn is not None and callable(fn):
            facts.append((name, fn))
    return facts


sampler = _pred("sampler",
    (2, _fact_table_2(_build_sampler_facts)),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Key primitives
    "key", "split_key", "fold_in", "key_bytes",
    # Samplers
    "normal", "uniform", "bernoulli", "categorical",
    "poisson", "gamma", "beta", "exponential", "dirichlet",
    "multivariate_normal", "permutation", "choice",
    "randint", "truncated_normal",
    # Registry
    "sampler",
]
