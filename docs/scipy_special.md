# scipy.special — Mathematical Special Functions

The `scipy_special` module wraps [`scipy.special`](https://docs.scipy.org/doc/scipy/reference/special.html) as Clausal predicates. Most predicates are **pure functions** (Tier 1): they accept scalars or NumPy arrays, broadcast automatically, and unify the last argument with the result. Several predicates are **bidirectional relations** that dispatch on argument groundness, supporting both forward evaluation and backward inversion.

---

## Import

```clausal
-import_from(scipy_special, [Gamma, Erf, BesselJ, EllipticK, ...])
```

Or via the canonical `py.*` path:

```clausal
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
| `scipy.special.boxcox` | `Boxcox` (bidirectional; Lambda first) |
| `scipy.special.boxcox1p` | `Boxcox1p` (bidirectional; Lambda first) |
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

```clausal
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

```clausal
ComputeCoefficients(N, K, COEFF) <- (
    Comb(N, K, COEFF),
    ++print(f"C({N},{K}) = {COEFF}")
)
```

---

### Error functions

These predicates are **bidirectional relations**: they dispatch on argument groundness, running forward or backward depending on which arguments are bound.

```clausal
Erf(X, Y)
    X ground, Y unbound → Y = erf(x)
    Y ground, X unbound → X = erfinv(y)   # inverse direction
    Both ground         → consistency check: succeeds iff erf(x) ≈ y

ErfComplement(X, Y)
    X ground, Y unbound → Y = erfc(x)
    Y ground, X unbound → X = erfcinv(y)
    Both ground         → consistency check: succeeds iff erfc(x) ≈ y

NormalCdf(X, P)
    X ground, P unbound → P = Φ(x)   # standard normal CDF
    P ground, X unbound → X = Φ⁻¹(p) # probit / quantile function
    Both ground         → consistency check: succeeds iff Φ(x) ≈ p
```

Example — bidirectional NormalCdf acts as both CDF and quantile function:

```clausal
# Forward: P = Φ(1.96) ≈ 0.975
NormalCdf(1.96, P)

# Backward: X = Φ⁻¹(0.975) ≈ 1.96
NormalCdf(X, 0.975)

# Round-trip
CheckQuantile(X) <- (
    NormalCdf(X, P),
    NormalCdf(X2, P),
    DIFF is ++(abs(float(X2) - float(X))),
    DIFF < 1e-9
)
```

---

### Incomplete gamma, beta, and Box-Cox (bidirectional)

```clausal
GammaInc(A, X, Y)
    A fixed (always ground).
    X ground, Y unbound → Y = gammainc(a, x)    # regularised lower incomplete gamma
    Y ground, X unbound → X = gammaincinv(a, y)
    Both ground         → consistency check: succeeds iff gammainc(a, x) ≈ y

GammaIncComplement(A, X, Y)
    A fixed.
    X ground, Y unbound → Y = gammaincc(a, x)   # upper tail
    Y ground, X unbound → X = gammainccinv(a, y)
    Both ground         → consistency check: succeeds iff gammaincc(a, x) ≈ y

BetaInc(A, B, X, Y)
    A, B fixed.
    X ground, Y unbound → Y = betainc(a, b, x)
    Y ground, X unbound → X = betaincinv(a, b, y)
    Both ground         → consistency check: succeeds iff betainc(a, b, x) ≈ y

Boxcox(Lambda, X, Y)
    Lambda fixed (always first argument).
    X ground, Y unbound → Y = boxcox(x, lambda)
    Y ground, X unbound → X = inv_boxcox(y, lambda)
    Both ground         → consistency check: succeeds iff boxcox(x, lambda) ≈ y

Boxcox1p(Lambda, X, Y)
    Lambda fixed (always first argument).
    X ground, Y unbound → Y = boxcox1p(x, lambda)
    Y ground, X unbound → X = inv_boxcox1p(y, lambda)
    Both ground         → consistency check: succeeds iff boxcox1p(x, lambda) ≈ y
```

Example — round-trip through Box-Cox transform:

```clausal
BoxcoxRoundTrip(LAM, X) <- (
    Boxcox(LAM, X, Y),
    Boxcox(LAM, X2, Y),
    DIFF is ++(abs(float(X2) - float(X))),
    DIFF < 1e-9
)
```

---

### Bessel functions

```clausal
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

```clausal
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

```clausal
Hypergeometric1F1(A, B, X, RESULT)
    RESULT = ₁F₁(a; b; x)   # confluent / Kummer's function

Hypergeometric2F1(A, B, C, Z, RESULT)
    RESULT = ₂F₁(a, b; c; z)   # Gauss hypergeometric function

Hypergeometric0F1(B, X, RESULT)
    RESULT = ₀F₁(; b; x)
```

---

### Information theory

```clausal
Entr(X, RESULT)
    RESULT = −x log(x)   # entropy element-wise; 0 when x=0

KlDivergence(X, Y, RESULT)
    RESULT = x log(x/y) − x + y   # Kullback-Leibler element-wise

LogSumExp(A, RESULT)                        # log(sum(exp(a)))
LogSumExp(A, AXIS, B, KEEPDIMS, RESULT)     # with axis, weights, keepdims
```

Example — stable log-sum using `LogSumExp`:

```clausal
StableLogProb(LOGITS, LP) <- (
    LogSumExp(LOGITS, Z),
    LP is ++(LOGITS - float(Z))
)
```

---

### Orthogonal polynomials

```clausal
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

```clausal
CubeRoot(X, RESULT)
    RESULT = x^(1/3)   # works correctly for negative x

Exp10(X, RESULT)
    RESULT = 10^x

Exp2(X, RESULT)
    RESULT = 2^x

Logit(X, Y)                        # bidirectional
    X ground, Y unbound → Y = log(x / (1−x))      # logit function
    Y ground, X unbound → X = 1 / (1 + exp(−y))   # sigmoid / expit (inverse)
    Both ground         → consistency check: succeeds iff logit(x) ≈ y

LambertW(Z, RESULT)               # principal branch (k=0)
LambertW(Z, K, TOL, RESULT)       # branch K with tolerance TOL

XLogY(X, Y, RESULT)
    RESULT = x · log(y)   # 0 when x=0 (safe for entropy-style computations)

XLog1pY(X, Y, RESULT)
    RESULT = x · log(1+y)   # 0 when x=0
```

---

## Complete example — Gaussian process kernel

```clausal
-import_from(scipy_special, [Gamma, BesselK, BesselJZeros])

# Matérn 5/2 covariance function value at distance D
Matern52(D, NU_5_2, RESULT) <- (
    SQRT5 is ++(5.0 ** 0.5),
    ARG is SQRT5 * D,
    TERM1 is ARG,
    TERM2 is ARG * ARG / 3.0,
    RESULT is ++(float(NU_5_2) * (1.0 + float(TERM1) + float(TERM2)) * 2.718281828 ** (-(float(TERM1))))
)

# First zero of J_0 (wave antinodes)
FirstAntinode(ZERO) <- (
    BesselJZeros(0, 1, ZEROS),
    ZERO is ++float(list(ZEROS)[0])
)
```

---

## Notes

- All predicates accept Python `float`, `int`, or NumPy scalars/arrays; broadcasting is handled by scipy.
- Multi-value outputs (e.g. `BesselJZeros`) return NumPy arrays that can be further processed via `++` escapes.
- `LambertW` returns a complex value; use `++(float(W.real))` to extract the real part.
- Predicates fail (no solution) when `unify` with a bound `RESULT` fails; they propagate scipy exceptions otherwise.
