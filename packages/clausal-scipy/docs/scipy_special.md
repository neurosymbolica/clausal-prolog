# scipy.special — Mathematical Special Functions

The `scipy_special` module wraps [`scipy.special`](https://docs.scipy.org/doc/scipy/reference/special.html) as Clausal predicates. Most predicates are **pure functions** (Tier 1): they accept scalars or NumPy arrays, broadcast automatically, and unify the last argument with the result. Several predicates are **bidirectional relations** that dispatch on argument [groundness](indexing.md), supporting both forward evaluation and backward inversion.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:import_ex2"
```

---

## Naming conventions

Predicate names follow Clausal conventions (TitleCase, readable), not scipy's terse abbreviation style:

| Module name | Clausal name |
|---|---|
| `scipy.special.gamma` | `Gamma` |
| `scipy.special.gammaln` | `GammaLog` |
| `scipy.special.gammasgn` | `GammaSign` |
| `scipy.special.betaln` | `BetaLog` |
| `scipy.special.erfc` | `ErfComplement` |
| `scipy.special.erfinv` | `Erf` backward direction |
| `scipy.special.erfcinv` | `ErfComplement` backward direction |
| `scipy.special.ndtr` | `NormalCdf` |
| `scipy.special.ndtri` | `NormalCdf` backward direction |
| `scipy.special.jn`, `jv` | `BesselJ`, `BesselJReal` |
| `scipy.special.yn`, `yv` | `BesselY`, `BesselYReal` |
| `scipy.special.kn` | `BesselK` |
| `scipy.special.iv` | `BesselI` |
| `scipy.special.hyp1f1` | `Hypergeometric1F1` |
| `scipy.special.expit` | `Logit` backward direction |
| `scipy.special.logit` | `Logit` (bidirectional: logit ↔ sigmoid) |
| `scipy.special.gammainc` | `GammaInc` (bidirectional) |
| `scipy.special.gammaincc` | `GammaIncComplement` (bidirectional) |
| `scipy.special.betainc` | `BetaInc` (bidirectional) |
| `scipy.special.boxcox` | `boxcox` (bidirectional; Lambda first) |
| `scipy.special.boxcox1p` | `Boxcox1p` (bidirectional; Lambda first) |
| `scipy.special.cbrt` | `CubeRoot` |
| `scipy.special.kl_div` | `KlDivergence` |
| `scipy.special.logsumexp` | `log_sum_exp` |
| `scipy.special.lpmv` | `AssocLegendre` |
| `scipy.special.eval_legendre` | `LegendrePoly` |
| `scipy.special.eval_chebyt/u` | `ChebyshevT`, `ChebyshevU` |
| `scipy.special.eval_hermite` | `HermiteH` |
| `scipy.special.eval_genlaguerre` | `GeneralizedLaguerre` |
| `scipy.special.xlogy` | `XLogY` |
| `scipy.special.xlog1py` | `XLog1pY` |

---

## Predicate catalogue

### Gamma and related

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:gamma_and_related"
```

Example:

```clausal
compute_coefficients(N, K, COEFF) <- (
    comb(N, K, COEFF),
    ++print(f"C({N},{K}) = {COEFF}")
)
```

---

### Error functions

These predicates are **bidirectional relations**: they dispatch on argument groundness, running forward or backward depending on which arguments are bound.

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:error_functions"
```

Example — bidirectional NormalCdf acts as both CDF and quantile function:

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:error_functions_ex2"
```

---

### Incomplete gamma, beta, and Box-Cox (bidirectional)

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:incomplete_gamma_beta_and_box_cox"
```

Example — round-trip through Box-Cox transform:

```clausal
boxcox_round_trip(LAM, X) <- (
    boxcox(LAM, X, Y),
    boxcox(LAM, X2, Y),
    DIFF is ++(abs(float(X2) - float(X))),
    DIFF < 1e-9
)
```

---

### Bessel functions

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:bessel_functions"
```

---

### Elliptic integrals

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:elliptic_integrals"
```

---

### Hypergeometric functions

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:hypergeometric_functions"
```

---

### Information theory

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:information_theory"
```

Example — stable log-sum using `log_sum_exp`:

```clausal
stable_log_prob(LOGITS, LP) <- (
    log_sum_exp(LOGITS, Z),
    LP is ++(LOGITS - float(Z))
)
```

---

### Orthogonal polynomials

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:orthogonal_polynomials"
```

---

### Convenience / misc

```clausal
--8<-- "tests/fixtures/docs/scipy_special_sigs.txt:convenience_misc"
```

---

## Complete example — Gaussian process kernel

```clausal
-import_from(scipy_special, [Gamma, BesselK, BesselJZeros])

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
    BesselJZeros(0, 1, ZEROS),
    ZERO is ++float(list(ZEROS)[0])
)
```

---

## Notes

- All predicates accept Python `float`, `int`, or NumPy scalars/arrays; broadcasting is handled by scipy.
- Multi-value outputs (e.g. `BesselJZeros`) return NumPy arrays that can be further processed via [`++` escapes](python_integration.md).
- `LambertW` returns a complex value; use `++(float(W.real))` to extract the real part.
- Predicates fail (no solution) when `unify` with a bound `RESULT` fails; they propagate scipy exceptions otherwise.

---

*See also: [scipy.stats](scipy_stats.md) — statistical distributions using special functions · [Arithmetic](arithmetic.md) — Clausal built-in arithmetic.*
