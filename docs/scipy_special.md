# scipy.special — Mathematical Special Functions

The `scipy_special` module wraps [`scipy.special`](https://docs.scipy.org/doc/scipy/reference/special.html) as Clausal predicates. All predicates are **pure functions** (Tier 1): they accept scalars or NumPy arrays, broadcast automatically, and unify the last argument with the result.

---

## Import

```
-import_from(scipy_special, [Gamma, Erf, BesselJ, EllipticK, ...])
```

Or via the canonical `py.*` path:

```
-import_from(py.scipy_special, [Gamma, Erf, BesselJ, ...])
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
| `scipy.special.erfinv` | `ErfInverse` |
| `scipy.special.erfcinv` | `ErfComplementInverse` |
| `scipy.special.ndtr` | `NormalCdf` |
| `scipy.special.ndtri` | `NormalCdfInverse` |
| `scipy.special.jn`, `jv` | `BesselJ`, `BesselJReal` |
| `scipy.special.yn`, `yv` | `BesselY`, `BesselYReal` |
| `scipy.special.kn` | `BesselK` |
| `scipy.special.iv` | `BesselI` |
| `scipy.special.hyp1f1` | `Hypergeometric1F1` |
| `scipy.special.expit` | `Sigmoid` |
| `scipy.special.cbrt` | `CubeRoot` |
| `scipy.special.kl_div` | `KlDivergence` |
| `scipy.special.logsumexp` | `LogSumExp` |
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

```
Gamma(X, RESULT)
    RESULT = Γ(x)

GammaLog(X, RESULT)
    RESULT = log Γ(x)   # more numerically stable than log(Gamma(x))

GammaSign(X, RESULT)
    RESULT = sign of Γ(x)   # +1 or -1

BetaLog(A, B, RESULT)
    RESULT = log B(a,b) = log Γ(a) + log Γ(b) − log Γ(a+b)

Digamma(X, RESULT)
    RESULT = ψ(x) = Γ'(x) / Γ(x)   # logarithmic derivative of gamma

Polygamma(N, X, RESULT)
    RESULT = ψ^(n)(x)   # N-th derivative of digamma

Factorial(N, RESULT)                  # exact=False (float)
Factorial(N, EXACT, RESULT)           # EXACT=True returns an integer

Comb(N, K, RESULT)                    # C(n,k), inexact
Comb(N, K, EXACT, RESULT)             # EXACT=True returns an integer
Comb(N, K, EXACT, REPETITION, RESULT) # with-repetition variant

Perm(N, K, RESULT)                    # P(n,k), inexact
Perm(N, K, EXACT, RESULT)             # EXACT=True returns an integer
```

Example:

```
ComputeCoefficients(N_, K_, COEFF_) <- (
    Comb(N_, K_, COEFF_) and
    ++print(f"C({N_},{K_}) = {COEFF_}")
)
```

---

### Error functions

```
Erf(X, RESULT)
    RESULT = erf(x) = (2/√π) ∫₀ˣ exp(−t²) dt

ErfComplement(X, RESULT)
    RESULT = erfc(x) = 1 − erf(x)

ErfInverse(Y, RESULT)
    RESULT = erf⁻¹(y)

ErfComplementInverse(Y, RESULT)
    RESULT = erfc⁻¹(y)

NormalCdf(X, RESULT)
    RESULT = Φ(x) = ½ erfc(−x/√2)   # standard normal CDF

NormalCdfInverse(P, RESULT)
    RESULT = Φ⁻¹(p)   # probit / quantile function
```

Example — round-trip through the normal CDF:

```
CheckQuantile(P_, X_) <- (
    NormalCdfInverse(P_, X_) and
    NormalCdf(X_, P2_) and
    DIFF is ++(abs(float(P2_) - float(P_))) and
    DIFF < 1e-9
)
```

---

### Bessel functions

```
BesselJ(N, X, RESULT)       # J_n(x), first kind, integer order
BesselY(N, X, RESULT)       # Y_n(x), second kind, integer order

BesselJReal(V, Z, RESULT)   # J_v(z), first kind, real order
BesselYReal(V, Z, RESULT)   # Y_v(z), second kind, real order

BesselK(N, X, RESULT)       # K_n(x), modified Bessel of second kind
BesselI(V, X, RESULT)       # I_v(x), modified Bessel of first kind

BesselJZeros(N, NT, RESULT)
    RESULT: array of first NT zeros of J_n

SphericalBesselJ(N, Z, RESULT)              # j_n(z), derivative=False
SphericalBesselJ(N, Z, DERIVATIVE, RESULT)  # derivative=DERIVATIVE
```

---

### Elliptic integrals

```
EllipticK(M, RESULT)
    RESULT = K(m) = ∫₀^{π/2} (1 − m sin²θ)^{−½} dθ   # complete, first kind

EllipticE(M, RESULT)
    RESULT = E(m) = ∫₀^{π/2} (1 − m sin²θ)^{½} dθ    # complete, second kind

EllipticKIncomplete(PHI, M, RESULT)
    RESULT = K(φ, m)   # incomplete, first kind

EllipticEIncomplete(PHI, M, RESULT)
    RESULT = E(φ, m)   # incomplete, second kind
```

---

### Hypergeometric functions

```
Hypergeometric1F1(A, B, X, RESULT)
    RESULT = ₁F₁(a; b; x)   # confluent / Kummer's function

Hypergeometric2F1(A, B, C, Z, RESULT)
    RESULT = ₂F₁(a, b; c; z)   # Gauss hypergeometric function

Hypergeometric0F1(B, X, RESULT)
    RESULT = ₀F₁(; b; x)
```

---

### Information theory

```
Entr(X, RESULT)
    RESULT = −x log(x)   # entropy element-wise; 0 when x=0

KlDivergence(X, Y, RESULT)
    RESULT = x log(x/y) − x + y   # Kullback-Leibler element-wise

LogSumExp(A, RESULT)                        # log(sum(exp(a)))
LogSumExp(A, AXIS, B, KEEPDIMS, RESULT)     # with axis, weights, keepdims
```

Example — stable log-sum using `LogSumExp`:

```
StableLogProb(LOGITS_, LP_) <- (
    LogSumExp(LOGITS_, Z_) and
    LP_ is ++(LOGITS_ - float(Z_))
)
```

---

### Orthogonal polynomials

```
AssocLegendre(M, V, X, RESULT)
    RESULT = P_v^m(x)   # associated Legendre function; M is the order, V the degree

LegendrePoly(N, X, RESULT)
    RESULT = P_n(x)   # Legendre polynomial

ChebyshevT(N, X, RESULT)
    RESULT = T_n(x)   # Chebyshev polynomial of first kind

ChebyshevU(N, X, RESULT)
    RESULT = U_n(x)   # Chebyshev polynomial of second kind

HermiteH(N, X, RESULT)
    RESULT = H_n(x)   # physicists' Hermite polynomial

GeneralizedLaguerre(N, ALPHA, X, RESULT)
    RESULT = L_n^α(x)   # generalised Laguerre polynomial
```

---

### Convenience / misc

```
CubeRoot(X, RESULT)
    RESULT = x^(1/3)   # works correctly for negative x

Exp10(X, RESULT)
    RESULT = 10^x

Exp2(X, RESULT)
    RESULT = 2^x

Sigmoid(X, RESULT)
    RESULT = 1 / (1 + exp(−x))   # logistic / expit function

Logit(X, RESULT)
    RESULT = log(x / (1−x))   # inverse of Sigmoid

LambertW(Z, RESULT)               # principal branch (k=0)
LambertW(Z, K, TOL, RESULT)       # branch K with tolerance TOL

XLogY(X, Y, RESULT)
    RESULT = x · log(y)   # 0 when x=0 (safe for entropy-style computations)

XLog1pY(X, Y, RESULT)
    RESULT = x · log(1+y)   # 0 when x=0
```

---

## Complete example — Gaussian process kernel

```
-import_from(scipy_special, [Gamma, BesselK, BesselJZeros])

# Matérn 5/2 covariance function value at distance D
Matern52(D_, NU_5_2_, RESULT_) <- (
    SQRT5 is ++(5.0 ** 0.5) and
    ARG_ is SQRT5 * D_ and
    TERM1_ is ARG_ and
    TERM2_ is ARG_ * ARG_ / 3.0 and
    RESULT_ is ++(float(NU_5_2_) * (1.0 + float(TERM1_) + float(TERM2_)) * 2.718281828 ** (-(float(TERM1_))))
)

# First zero of J_0 (wave antinodes)
FirstAntinode(ZERO_) <- (
    BesselJZeros(0, 1, ZEROS_) and
    ZERO_ is ++float(list(ZEROS_)[0])
)
```

---

## Notes

- All predicates accept Python `float`, `int`, or NumPy scalars/arrays; broadcasting is handled by scipy.
- Multi-value outputs (e.g. `BesselJZeros`) return NumPy arrays that can be further processed via `++` escapes.
- `LambertW` returns a complex value; use `++(float(W.real))` to extract the real part.
- Predicates fail (no solution) when `unify` with a bound `RESULT` fails; they propagate scipy exceptions otherwise.
