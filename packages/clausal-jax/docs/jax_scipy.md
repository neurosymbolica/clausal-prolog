# jax_scipy — JAX Special Functions and Distributions

`jax.scipy` is JAX's reimplementation of a subset of SciPy — same
function surface, different array type. Where the existing
`py.scipy_special` / `py.scipy_stats` wrappers operate on
`numpy.ndarray`, this module operates on `jax.Array`, so the
computations participate in `jax.grad`, `jax.jit`, and GPU/TPU
execution. If you're building a likelihood you want to differentiate,
this is the module to import.

All predicates are Tier 1 pure.

## Import

```clausal
-import_from(py.jax_scipy, [
    gamma_fn, gammaln, digamma,
    erf, erfc, erfinv,
    expit, logit,
    i0, i1, i0e, i1e,
    logsumexp,
    beta_fn, betainc, polygamma,
    rel_entr, xlogy, zeta,
    factorial, multigammaln, spence,
    distribution,
    pdf, logpdf, cdf, logcdf, sf, logsf, ppf, pmf, logpmf
])
```

---

## Special functions

Each predicate applies the corresponding `jax.scipy.special` function
element-wise to a `jax.Array`.

| Predicate | Semantics |
|---|---|
| `gamma_fn(X, R)` | Γ(x) |
| `gammaln(X, R)` | log Γ(x) — numerically stable |
| `digamma(X, R)` | ψ(x) = Γ′(x)/Γ(x) |
| `erf(X, R)` | Error function |
| `erfc(X, R)` | Complementary error function |
| `erfinv(X, R)` | Inverse error function |
| `expit(X, R)` | 1 / (1 + exp(−x)) (logistic sigmoid) |
| `logit(X, R)` | log(x / (1 − x)) — inverse of `expit` |
| `i0(X, R)`, `i1(X, R)` | Modified Bessel I₀ / I₁ |
| `i0e(X, R)`, `i1e(X, R)` | Exponentially-scaled I₀ / I₁ |
| `logsumexp(A, R)` / `logsumexp(A, AXIS, R)` | log Σ exp(aᵢ) — stable |
| `beta_fn(A, B, R)` | B(a, b) = Γ(a)Γ(b)/Γ(a+b) |
| `betainc(A, B, X, R)` | Regularised incomplete beta |
| `polygamma(N, X, R)` | ψ⁽ⁿ⁾(x) |
| `rel_entr(P, Q, R)` | Relative entropy element: p·log(p/q) |
| `xlogy(X, Y, R)` | x·log(y), safe at x=0 |
| `zeta(X, Q, R)` | Hurwitz zeta ζ(x, q) |
| `factorial(N, R)` | n! via gamma |
| `multigammaln(A, D, R)` | log of multivariate gamma |
| `spence(X, R)` | Spence's (dilogarithm) |

```clausal
test("erf at 0 is 0") <- (
    array([0.0], X),
    erf(X, R),
    array(0.0, ZERO),
    allclose(R, ZERO, 0.0001, 0.0)
)

test("expit + logit round-trip") <- (
    array([0.7], X),
    expit(X, Y),
    logit(Y, X2),
    allclose(X, X2, 0.0001, 0.0)
)
```

### Name clashes: `gamma_fn` / `beta_fn`

JAX has **three** namespaces that would all produce a Clausal-level
`gamma` or `beta`:

| Namespace | Meaning | Module |
|---|---|---|
| `jax.random.gamma` | Sampler | `py.jax_random` (name `gamma`) |
| `jax.scipy.special.gamma` | Γ function | *this module* (name `gamma_fn`) |
| `jax.scipy.stats.gamma` | Distribution | accessed as atom `"gamma"` via `pdf/cdf/...` |

Predicates are module-scoped, so the three only collide when a user
imports from multiple modules. The `_fn` suffix keeps the intent
explicit without blocking users who want all three. Same pattern for
`beta_fn` (sampler, special function, distribution).

---

## Distribution registry

### `distribution(NAME, MODULE)`

Nondeterministic fact table of `jax.scipy.stats` submodules. Same
shape as `activation/2` and `initializer/2` in `py.jax_nn`.

Enumerated names: `norm`, `uniform`, `bernoulli`, `beta`, `binom`,
`cauchy`, `chi2`, `dirichlet`, `expon`, `gamma`, `laplace`, `logistic`,
`multinomial`, `multivariate_normal`, `nbinom`, `pareto`, `poisson`,
`t`, `truncnorm`, `vonmises`, `wrapcauchy`, `gennorm`, `geom`.

```clausal
test("distribution lookup") <- (
    distribution("norm", M),
    M != ++(None)
)

test("distribution enumeration") <- (
    findall(N, distribution(N, _), NS),
    length(NS, 23)
)
```

### Distribution methods

Each method takes a distribution name (a string atom), a value, and a
dict of parameters matching the distribution's keyword arguments.

| Predicate | For | Semantics |
|---|---|---|
| `pdf(DIST, X, PARAMS, R)` | continuous | Probability density |
| `logpdf(DIST, X, PARAMS, R)` | continuous | Log density |
| `cdf(DIST, X, PARAMS, R)` | both | CDF |
| `logcdf(DIST, X, PARAMS, R)` | both | Log CDF |
| `sf(DIST, X, PARAMS, R)` | both | Survival = 1 − CDF |
| `logsf(DIST, X, PARAMS, R)` | both | Log survival |
| `ppf(DIST, Q, PARAMS, R)` | continuous | Inverse CDF |
| `pmf(DIST, X, PARAMS, R)` | discrete | Probability mass |
| `logpmf(DIST, X, PARAMS, R)` | discrete | Log mass |

```clausal
test("normal pdf at mean") <- (
    pdf("norm", 0.0, {"loc": 0.0, "scale": 1.0}, P),
    array(0.3989423, EXPECTED),
    allclose(P, EXPECTED, 0.0001, 0.0)
)

test("bernoulli pmf at 1") <- (
    pmf("bernoulli", 1, {"p": 0.3}, P),
    array(0.3, EXPECTED),
    allclose(P, EXPECTED, 0.0001, 0.0)
)
```

### Missing methods fail cleanly

JAX's `scipy.stats` is a **subset** of SciPy's. Some distributions
have only a few of the standard methods — for example, `bernoulli` is
discrete, so it has `pmf`/`logpmf` but no `pdf`; `t` ships with
`pdf`/`logpdf` only; `binom` has no CDF. When the requested method is
missing for the named distribution, `_pure`'s exception handler turns
the resulting `AttributeError` into predicate failure:

```clausal
test("bernoulli has no pdf") <- (
    not pdf("bernoulli", 1, {"p": 0.5}, _P)
)
```

---

## Why JAX-native scipy?

The obvious question: the project already has `py.scipy_special` and
`py.scipy_stats`. Why add a parallel set?

**Autodiff.** `jax.grad(lambda params: logpdf(norm, x, params, LP))`
tracers flow through `jax.scipy.stats.norm.logpdf` but not through
`scipy.stats.norm.logpdf` (which coerces to numpy).

**JIT and accelerators.** `jax.jit(loss_fn)` and GPU/TPU execution
similarly require the jax-native code path.

**No-op if you don't need them.** If you're computing a static log
likelihood over numpy data, `py.scipy_stats` is perfectly fine —
pick the module that matches your array type.

## Comparison

| Need | Use |
|---|---|
| Differentiate a log-likelihood | `py.jax_scipy` + `py.jax` arrays |
| Run on GPU/TPU | `py.jax_scipy` + `py.jax` arrays |
| JIT-compile a score function | `py.jax_scipy` + `py.jax` arrays |
| Offline statistics on numpy data | `py.scipy_special` / `py.scipy_stats` |
| One-shot plot or report | Either — pick by array type at hand |
