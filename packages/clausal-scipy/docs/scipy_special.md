# scipy.special — Mathematical Special Functions

The `scipy_special` module wraps [`scipy.special`](https://docs.scipy.org/doc/scipy/reference/special.html) as Clausal Prolog predicates. Most predicates are **pure functions** (Tier 1): they accept scalars or NumPy arrays, broadcast automatically, and unify the last argument with the result. Several predicates are **bidirectional relations** that dispatch on argument [groundness](indexing.md), supporting both forward evaluation and backward inversion.

---

## Import

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:import"
```

Or via the canonical `py.*` path:

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:import_ex2"
```

---

## Naming conventions

Predicate names follow Clausal Prolog conventions (TitleCase, readable), not scipy's terse abbreviation style:

| Module name | Clausal Prolog name |
|---|---|
| `scipy.special.gamma` | `gamma` |
| `scipy.special.gammaln` | `gamma_log` |
| `scipy.special.gammasgn` | `gamma_sign` |
| `scipy.special.betaln` | `beta_log` |
| `scipy.special.erfc` | `erf_complement` |
| `scipy.special.erfinv` | `erf` backward direction |
| `scipy.special.erfcinv` | `erf_complement` backward direction |
| `scipy.special.ndtr` | `normal_cdf` |
| `scipy.special.ndtri` | `normal_cdf` backward direction |
| `scipy.special.jn`, `jv` | `bessel_j`, `bessel_j_real` |
| `scipy.special.yn`, `yv` | `bessel_y`, `bessel_y_real` |
| `scipy.special.kn` | `bessel_k` |
| `scipy.special.iv` | `bessel_i` |
| `scipy.special.hyp1f1` | `hypergeometric_1f1` |
| `scipy.special.expit` | `logit` backward direction |
| `scipy.special.logit` | `logit` (bidirectional: logit ↔ sigmoid) |
| `scipy.special.gammainc` | `gamma_inc` (bidirectional) |
| `scipy.special.gammaincc` | `gamma_inc_complement` (bidirectional) |
| `scipy.special.betainc` | `beta_inc` (bidirectional) |
| `scipy.special.boxcox` | `boxcox` (bidirectional; Lambda first) |
| `scipy.special.boxcox1p` | `boxcox1p` (bidirectional; Lambda first) |
| `scipy.special.cbrt` | `cube_root` |
| `scipy.special.kl_div` | `kl_divergence` |
| `scipy.special.logsumexp` | `log_sum_exp` |
| `scipy.special.lpmv` | `assoc_legendre` |
| `scipy.special.eval_legendre` | `legendre_poly` |
| `scipy.special.eval_chebyt/u` | `chebyshev_t`, `chebyshev_u` |
| `scipy.special.eval_hermite` | `hermite_h` |
| `scipy.special.eval_genlaguerre` | `generalized_laguerre` |
| `scipy.special.xlogy` | `x_log_y` |
| `scipy.special.xlog1py` | `x_log1p_y` |

---

## Predicate catalogue

### gamma and related

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:gamma_and_related"
```

Example:

```seam
compute_coefficients(N, K, COEFF) <- (
    comb(N, K, COEFF),
    ++print(f"C({N},{K}) = {COEFF}")
)
```

---

### Error functions

These predicates are **bidirectional relations**: they dispatch on argument groundness, running forward or backward depending on which arguments are bound.

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:error_functions"
```

Example — bidirectional normal_cdf acts as both CDF and quantile function:

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:error_functions_ex2"
```

---

### Incomplete gamma, beta, and Box-Cox (bidirectional)

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:incomplete_gamma_beta_and_box_cox"
```

Example — round-trip through Box-Cox transform:

```seam
boxcox_round_trip(LAM, X) <- (
    boxcox(LAM, X, Y),
    boxcox(LAM, X2, Y),
    DIFF is ++(abs(float(X2) - float(X))),
    DIFF < 1e-9
)
```

---

### bessel functions

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:bessel_functions"
```

---

### elliptic integrals

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:elliptic_integrals"
```

---

### Hypergeometric functions

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:hypergeometric_functions"
```

---

### Information theory

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:information_theory"
```

Example — stable log-sum using `log_sum_exp`:

```seam
stable_log_prob(LOGITS, LP) <- (
    log_sum_exp(LOGITS, Z),
    LP is ++(LOGITS - float(Z))
)
```

---

### Orthogonal polynomials

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:orthogonal_polynomials"
```

---

### Convenience / misc

```seam
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:convenience_misc"
```

---

## Complete example — Gaussian process kernel

```seam
-import_from(scipy_special, [gamma, bessel_k, bessel_j_zeros])

# Matérn 5/2 covariance function value at distance D
matern52(D, NU_5_2, RESULT) <- (
    SQRT5 is ++(5.0 ** 0.5),
    ARG is SQRT5 * D,
    TERM1 is ARG,
    TERM2 is ARG * ARG / 3.0,
    RESULT is ++(float(NU_5_2) * (1.0 + float(TERM1) + float(TERM2)) * 2.718281828 ** (-(float(TERM1))))
)

# First zero of J_0 (wave antinodes)
first_antinode(ZERO) <- (
    bessel_j_zeros(0, 1, ZEROS),
    ZERO is ++float(list(ZEROS)[0])
)
```

---

## Notes

- All predicates accept Python `float`, `int`, or NumPy scalars/arrays; broadcasting is handled by scipy.
- Multi-value outputs (e.g. `bessel_j_zeros`) return NumPy arrays that can be further processed via [`++` escapes](python_integration.md).
- `lambert_w` returns a complex value; use `++(float(W.real))` to extract the real part.
- Predicates fail (no solution) when `unify` with a bound `RESULT` fails; they propagate scipy exceptions otherwise.

---

*See also: [scipy.stats](scipy_stats.md) — statistical distributions using special functions · [Arithmetic](arithmetic.md) — Clausal Prolog built-in arithmetic.*
