# Phase 11 — jax.scipy: Special Functions and Distributions

Wraps `jax.scipy.special` (special functions) and `jax.scipy.stats`
(probability distribution shapes). Mirrors PyTorch Phase 9 (torch
distributions) and the scipy wrappers' `scipy_special.py` /
`scipy_stats.py`.

**File to create:** `clausal/modules/py/jax_scipy.py`

**Depends on:** Phase 1, Phase 2 (for sampling in distribution
examples).

---

## Predicates

### Special functions (all `_pure`)

| Name | Arity | Modes | JAX source |
|---|---|---|---|
| `gamma_fn` | `/2` | `(+A, -R)` | `jss.gamma` |
| `gammaln` | `/2` | | `jss.gammaln` |
| `digamma` | `/2` | | |
| `erf` | `/2` | | |
| `erfc` | `/2` | | |
| `erfinv` | `/2` | | |
| `expit` | `/2` | | Logistic sigmoid |
| `logit` | `/2` | | Inverse of expit |
| `i0` | `/2` | | Modified Bessel of 1st kind, order 0 |
| `i1` | `/2` | | Order 1 |
| `logsumexp` | `/2, /3` | | `jss.logsumexp` |
| `beta_fn` | `/3` | `(+A, +B, -R)` | |
| `betainc` | `/4` | `(+A, +B, +X, -R)` | Regularised incomplete beta |
| `polygamma` | `/3` | `(+N, +X, -R)` | |
| `rel_entr` | `/3` | `(+P, +Q, -R)` | Relative entropy |
| `xlogy` | `/3` | `(+X, +Y, -R)` | |

Note `gamma_fn` / `beta_fn` suffix: `gamma` and `beta` clash with
`jax_random.gamma` / `jax_random.beta` samplers. Predicates are
module-scoped so the clash is only visible when a user imports both —
but the `_fn` suffix keeps disambiguation explicit.

### Distribution registry

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `distribution` | `/2` | `(+N, -MODULE)`, `(-N, -MODULE)` | pure | yes | Enumerate `jax.scipy.stats` submodules |

### Distribution operations

Per-distribution, JAX exposes `pdf`, `logpdf`, `cdf`, `logcdf`, `sf`,
`logsf`, `ppf` (or `isf` for survival). Not all distributions have all
methods.

| Name | Arity | Modes | Description |
|---|---|---|---|
| `pdf` | `/3, /N` | `(+DIST_NAME, +X, +PARAMS, -R)` | Probability density |
| `logpdf` | `/3, /N` | same | Log density |
| `cdf` | `/3, /N` | same | CDF |
| `logcdf` | `/3, /N` | same | Log CDF |

`PARAMS` is a dict matching the distribution's keyword args (e.g.
`{"loc": 0.0, "scale": 1.0}` for normal).

---

## Context and Reference Patterns

### Special functions — straightforward `_pure`

```python
def _jss_mod():
    _ensure_jax()
    import jax.scipy.special as _m
    return _m

erf = _pred("erf", (2, _pure(lambda a: _jss_mod().erf(a))))
gammaln = _pred("gammaln", (2, _pure(lambda a: _jss_mod().gammaln(a))))
```

### Distribution registry

Introspect `jax.scipy.stats`:

```python
def _build_distribution_facts():
    _ensure_jax()
    import jax.scipy.stats as jst
    wanted = [
        "norm", "uniform", "bernoulli", "beta", "binom",
        "cauchy", "chi2", "dirichlet", "expon", "gamma",
        "laplace", "logistic", "multinomial",
        "multivariate_normal", "nbinom", "pareto", "poisson",
        "t", "truncnorm", "vonmises", "wrapcauchy",
    ]
    facts = []
    for name in wanted:
        mod = getattr(jst, name, None)
        if mod is not None:
            facts.append((name, mod))
    return facts

distribution = _pred("distribution",
    (2, _fact_table_2(_build_distribution_facts)),
)
```

### `pdf`, `logpdf`, etc.

Each takes a distribution name, a value, and a params dict:

```python
def _call_dist_method(method):
    def inner(name, x, params):
        _ensure_jax()
        import jax.scipy.stats as jst
        mod = getattr(jst, name)
        fn = getattr(mod, method)
        return fn(x, **params)
    return inner

pdf = _pred("pdf",
    (4, _pure(_call_dist_method("pdf"))),
)
logpdf = _pred("logpdf", (4, _pure(_call_dist_method("logpdf"))))
cdf    = _pred("cdf",    (4, _pure(_call_dist_method("cdf"))))
logcdf = _pred("logcdf", (4, _pure(_call_dist_method("logcdf"))))
```

Why 4-arity (with params dict) rather than variadic: dict is the
uniform idiom used by every other wrapper in this codebase and avoids
having to enumerate per-distribution kwarg shapes. See PyTorch Phase 9
`make_distribution("Normal", {"loc": 0.0, "scale": 1.0}, D)` for the
precedent.

---

## Example Usage

```clausal
-import_from(py.jax, [array, array_list, allclose])
-import_from(py.jax_scipy, [gammaln, erf, expit, logsumexp,
                             distribution, pdf, logpdf, cdf])

Test("gammaln of integers") <- (
    array([1.0, 2.0, 3.0, 4.0, 5.0], X),
    gammaln(X, R),
    array_list(R, L),
    # log-gamma(1) = 0, log-gamma(2) = 0, log-gamma(3) = log(2)
    [V1, V2, V3, V4, V5] is L,
    V1 < 0.01,
    V2 < 0.01
)

Test("erf at 0 is 0") <- (
    array(0.0, X),
    erf(X, R),
    array_list(R, V),
    V > -0.01,
    V < 0.01
)

Test("expit is sigmoid") <- (
    array(0.0, X),
    expit(X, R),
    array_list(R, V),
    V > 0.49,
    V < 0.51
)

Test("enumerate distributions") <- (
    findall(N, distribution(N, _), NS),
    member("norm", NS),
    member("gamma", NS),
    member("beta", NS)
)

Test("normal pdf at mean") <- (
    array(0.0, X),
    pdf("norm", X, {"loc": 0.0, "scale": 1.0}, P),
    # 1 / sqrt(2 pi) ≈ 0.3989
    array_list(P, V),
    V > 0.39,
    V < 0.40
)

Test("normal cdf at mean is 0.5") <- (
    array(0.0, X),
    cdf("norm", X, {"loc": 0.0, "scale": 1.0}, P),
    array_list(P, V),
    V > 0.49,
    V < 0.51
)
```

---

## Tests

`tests/fixtures/jax_scipy_tests.clausal`:
- Spot-check special functions at known values
- `distribution/2` enumeration
- `pdf`/`logpdf`/`cdf` for `norm`, `gamma`, `beta`
- `exp(logpdf(...)) ≈ pdf(...)` consistency

---

## Docs

Create `docs/jax_scipy.md`:
- Split: special functions vs distribution shapes
- Distribution API shape (name + params dict)
- Comparison to `scipy_stats.py` and `torch_distributions.py`

---

## Issues

_To be populated during implementation._

1. **Name clash: `gamma`, `beta`.** These are both samplers (Phase 2)
   and special functions (here). Using `gamma_fn` / `beta_fn` in this
   phase to avoid collisions when users import both modules.
2. **`multivariate_normal` params** include `mean` and `cov` arrays,
   not scalars. Params dict still works but tests must pass arrays.
3. **No `ppf` (inverse CDF) in all distributions.** JAX's scipy.stats
   is a subset of scipy's. Predicate fails (via `_pure`'s
   except-handler) for unsupported methods.
