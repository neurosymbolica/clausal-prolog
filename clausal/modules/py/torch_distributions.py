"""clausal.modules.py.torch_distributions — Probability distribution predicates.

Wraps ``torch.distributions`` — probability distributions with sampling,
log-probability, and property queries::

    -import_from(py.torch_distributions, [distribution, make_distribution,
        sample, log_prob, entropy, mean, variance, stddev, cdf, icdf])

Registry
--------
distribution(NAME, CLASS)           Available distribution types.

Construction
------------
make_distribution(NAME, PARAMS, D)  Construct a distribution from name + params dict.

Sampling
--------
sample(D, S)                        Draw a single sample.
sample(D, SHAPE, S)                 Draw sample(s) with given shape.

Properties
----------
log_prob(D, VALUE, LP)              Log probability of value.
entropy(D, H)                       Distribution entropy.
mean(D, M)                          Distribution mean.
variance(D, V)                      Distribution variance.
stddev(D, S)                        Distribution standard deviation.

CDF / Inverse CDF
------------------
cdf(D, VALUE, P)                    Cumulative distribution function.
icdf(D, PROB, V)                    Inverse CDF (quantile function).

Names use original PyTorch class names (e.g. "Normal", "Bernoulli").
"""

from __future__ import annotations

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _deep_deref, _pure, _fact_table_2
from clausal.modules.py.torch import _ensure_torch, _th


def _property_2(getter):
    """Property predicate: (+dist, -value)."""
    def dispatch(this_generator, _proceed, _fail, _catcher, dist_var, value_var, trail):
        d = _deep_deref(dist_var)
        try:
            actual = getter(d)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(value_var, actual, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


# ── Registry builder ─────────────────────────────────────────────────────

def _build_distribution_facts():
    _ensure_torch()
    dists = _th().distributions
    facts = []
    for name in sorted(dir(dists)):
        if name.startswith("_") or not name[0].isupper():
            continue
        cls = getattr(dists, name, None)
        if isinstance(cls, type) and issubclass(cls, dists.Distribution):
            facts.append((name, cls))
    return facts


# ═══════════════════════════════════════════════════════════════════════════
# Predicates
# ═══════════════════════════════════════════════════════════════════════════

# -- distribution/2: registry fact table --

distribution = _pred("distribution",
    (2, _fact_table_2(_build_distribution_facts)),
)


# -- make_distribution/3: construct from name + params dict --

def _make_distribution(name, params):
    _ensure_torch()
    dists = _th().distributions
    cls = getattr(dists, name, None)
    if cls is None or not (isinstance(cls, type)
                           and issubclass(cls, dists.Distribution)):
        raise ValueError(f"Unknown distribution: {name}")
    return cls(**params)


make_distribution = _pred("make_distribution",
    (3, _pure(_make_distribution)),
)


# -- sample/2, sample/3 --

def _sample_no_shape(dist):
    return dist.sample()


def _sample_with_shape(dist, shape):
    return dist.sample(shape)


sample = _pred("sample",
    (2, _pure(_sample_no_shape)),
    (3, _pure(_sample_with_shape)),
)


# -- log_prob/3 --

log_prob = _pred("log_prob",
    (3, _pure(lambda dist, value: dist.log_prob(value))),
)


# -- entropy/2 --

entropy = _pred("entropy",
    (2, _property_2(lambda d: d.entropy())),
)


# -- mean/2, variance/2, stddev/2 --

mean = _pred("mean",
    (2, _property_2(lambda d: d.mean)),
)

variance = _pred("variance",
    (2, _property_2(lambda d: d.variance)),
)

stddev = _pred("stddev",
    (2, _property_2(lambda d: d.stddev)),
)


# -- cdf/3, icdf/3 --

cdf = _pred("cdf",
    (3, _pure(lambda dist, value: dist.cdf(value))),
)

icdf = _pred("icdf",
    (3, _pure(lambda dist, prob: dist.icdf(prob))),
)


# ── Module-level exports ─────────────────────────────────────────────────

__all__ = [
    "distribution", "make_distribution",
    "sample", "log_prob", "entropy",
    "mean", "variance", "stddev",
    "cdf", "icdf",
]
