# SCIPY_PORT.md
## SciPy → Clausal Module: Architecture Overview

This document is a planning brief for implementing SciPy as importable
clausal modules. It describes the overall porting strategy, naming
conventions, state model, and a proposed predicate catalogue grouped by
module. It is deliberately high-level — each module section is a spec input,
not a finished implementation.

---

## Conventions

### Naming
- Predicates: `TitleCase` — e.g. `LinalgSolve`, `OptimizeMinimize`
- Arguments: `ALLCAPS` named keywords — e.g. `A=`, `B=`, `METHOD=`, `RESULT=`
- Output arguments are always the **last** named argument(s), conventionally
  named `RESULT=`, `OUT=`, or a descriptive name like `X=`, `EIGENVALUES=`
- Multi-value outputs (e.g. U, S, Vh from SVD) use a dict/record term as
  `RESULT=` rather than multiple output arguments, unless the two-value case
  is idiomatic (e.g. `VALUE=`, `ERROR=` for integration)

### Statefulness tiers (see Architecture section)
- **Tier 1 — pure predicates**: no object construction; call and get a value
- **Tier 2 — result-record predicates**: call returns an immutable result record;
  fields accessed by name via a companion `Get*` predicate family
- **Tier 3 — handle predicates**: stateful objects managed by a Python-side
  registry; `Make*` constructs and returns an opaque `HANDLE=`; `Eval*`/`Query*`
  predicates take the handle; `Free*` releases it

### Result records
Every Tier 2 predicate returns a result dict. Implementors should expose
field accessors rather than requiring users to destructure raw dicts:
```
OptimizeMinimize(FUN=f, X0=x0, METHOD='BFGS', RESULT=R),
OptimizeResultGet(R, FIELD='x', VALUE=X),
OptimizeResultGet(R, FIELD='success', VALUE=Ok).
```

### Functions as arguments
Several predicates accept a callable `FUN=` argument (optimizer objective,
ODE RHS, integrand, etc.). In the Python implementation this is a first-class
Python callable passed through directly. Callers supply it via the `++()` Python
escape — e.g. `FUN=++lambda x: x**2` — or via a Python function reference
stored in a variable. No special boundary wrapping is needed; the predicate
implementation just receives and passes on a plain Python callable.

---

## Architecture

SciPy is a **confederation of independent subpackages**, not a unified library.
There is no shared base class or common protocol. Modules should be ported
and tested independently. The only cross-module dependency worth noting is
that `scipy.special` is called internally by `scipy.stats` distributions;
this is transparent to the wrapper.

### Implementation layout

Each SciPy subpackage maps to one Python file under `clausal/modules/py/`:

```
clausal/modules/py/scipy_special.py
clausal/modules/py/scipy_linalg.py
clausal/modules/py/scipy_optimize.py
clausal/modules/py/scipy_stats.py
clausal/modules/py/scipy_integrate.py
clausal/modules/py/scipy_interpolate.py
clausal/modules/py/scipy_fft.py
clausal/modules/py/scipy_ndimage.py
clausal/modules/py/scipy_signal.py
clausal/modules/py/scipy_spatial.py
clausal/modules/py/scipy_sparse.py
clausal/modules/py/scipy_cluster.py
clausal/modules/py/scipy_constants.py
clausal/modules/py/scipy_differentiate.py
```

Users import predicates in their `.clausal` files with:
```
-import_from(py.scipy_linalg, [LinalgSolve, LinalgSvd, LinalgEig]).
-import_from(py.scipy_optimize, [OptimizeMinimize, OptimizeResultGet]).
```

### Dispatch adapter (`_SciPyPredicate`)

Every predicate is exposed as a `_SciPyPredicate` object — modelled on
`_SklearnPredicate` in `clausal/modules/py/sklearn.py` — with a
`_get_dispatch()` method that returns a trampoline-mode generator function:

```python
class _SciPyPredicate:
    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name):
        self._name = name
        self._dispatch_fns = {}   # arity → fn

    def _register(self, arity, fn):
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self):
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1   # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)
```

Dispatch functions are trampoline-mode generators:
```python
def _linalg_solve(this_generator, parent, a, b, ..., result, trail):
    r = scipy.linalg.solve(deref(a), deref(b), ...)
    if unify(result, r, trail):
        yield (parent, None)
    yield (parent, DONE)
```

### Lazy scipy import

Each module file imports scipy lazily on first use, bypassing `ModulesFinder`
to avoid circular-import issues (the same pattern used in `sklearn.py`):

```python
_scipy_linalg = None
_scipy_lock = threading.Lock()

def _ensure_scipy_linalg():
    global _scipy_linalg
    if _scipy_linalg is not None:
        return
    with _scipy_lock:
        if _scipy_linalg is not None:
            return
        import sys, importlib
        from clausal.import_hook import ModulesFinder
        finders = [(i, f) for i, f in enumerate(sys.meta_path)
                   if isinstance(f, ModulesFinder)]
        for _, f in reversed(finders):
            sys.meta_path.remove(f)
        try:
            _scipy_linalg = importlib.import_module("scipy.linalg")
        finally:
            for i, f in finders:
                sys.meta_path.insert(i, f)
```

### Result records

Tier 2 result records are plain Python dicts. They are opaque values that
clausal variables can hold. Fields are accessed via companion `ResultGet`
predicates (which call `unify(value_var, result_dict[field], trail)`) or
directly via the `++()` Python escape:

```
OptimizeMinimize(FUN=++lambda x: x[0]**2, X0=++[1.0], METHOD='BFGS', RESULT=R),
OptimizeResultGet(R, FIELD='x', VALUE=X).
% or equivalently:
X is ++R['x'].
```

### Handle registry (Tier 3)

Tier 3 handles are plain Python integers stored in a module-level dict:
```python
_HANDLES: dict[int, Any] = {}
_NEXT_ID = 0
_HANDLE_LOCK = threading.Lock()

def _register(obj) -> int:
    global _NEXT_ID
    with _HANDLE_LOCK:
        h = _NEXT_ID; _NEXT_ID += 1
        _HANDLES[h] = obj
    return h

def _lookup(h: int):
    obj = _HANDLES.get(h)
    if obj is None:
        raise ValueError(f"Unknown handle {h!r}")
    return obj
```

The handle integer flows through clausal variables like any other Python
value. `Free*` predicates call `del _HANDLES[h]`.

### Variadic and kwargs arguments

Clausal has no native `*args` or `**kwargs` syntax. Predicates that wrap
variadic scipy functions take:
- `ARGS=` — a Python list (pass `++[a, b, c]` or a variable bound to a list)
- `KWARGS=` — a Python dict for extra keyword arguments (pass `++{'key': val}`)
  Defaults to `None` (omitted) when the predicate has no extra options.

### Module statefulness map

| Module | Tier | Notes |
|--------|------|-------|
| `scipy.special` | 1 — pure | All ufuncs, array → array |
| `scipy.linalg` | 1 — pure | Array in, array out; factorisation helpers are Tier 2 |
| `scipy.fft` | 1 — pure | Array → array |
| `scipy.ndimage` | 1 — pure | Array → array |
| `scipy.differentiate` | 1 — pure | Function + point → derivative |
| `scipy.constants` | 1 — pure | Lookup only |
| `scipy.spatial.distance` | 1 — pure | Array → distance matrix/scalar |
| `scipy.integrate` | 2 — result record | Returns `(value, error)` or `OdeResult` |
| `scipy.optimize` | 2 — result record | Returns `OptimizeResult` |
| `scipy.stats` (tests) | 2 — result record | Returns named result objects |
| `scipy.stats` (distributions) | 2/3 — frozen objects | Frozen dist = lightweight handle |
| `scipy.signal` | 1+2 mixed | Filter design = Tier 1; `lti` objects = Tier 3 |
| `scipy.cluster` | 2 — result record | Returns linkage/label arrays |
| `scipy.sparse.linalg` | 2 — result record | Solvers return result objects |
| `scipy.interpolate` | 3 — handle | Spline/interpolant objects need Make/Eval |
| `scipy.spatial` (trees) | 3 — handle | KDTree, ConvexHull need Make/Query |
| `scipy.sparse` (matrices) | 3 — handle | Sparse matrix objects |
| `scipy.odr` | 3 — handle | Low priority; very niche |

### Recommended porting order

| # | Module | Status |
|---|--------|--------|
| 1 | `scipy.special` | ✅ done — `clausal/modules/py/scipy_special.py`, 78 tests |
| 2 | `scipy.linalg` | ✅ done — `clausal/modules/py/scipy_linalg.py` |
| 3 | `scipy.optimize` | ✅ done — `clausal/modules/py/scipy_optimize.py`, 56 tests + 9 .clausal |
| 4 | `scipy.stats` (tests + distributions) | ⬜ next — Tier 2/3 |
| 5 | `scipy.integrate` | ✅ done — `clausal/modules/py/scipy_integrate.py`, 55 tests |
| 6 | `scipy.interpolate` | ✅ done — `clausal/modules/py/scipy_interpolate.py`, tests + docs |
| 7 | `scipy.fft` | ✅ done — `clausal/modules/py/scipy_fft.py`, 58 tests + 7 .clausal + docs |
| 8 | `scipy.ndimage` | ⬜ pure, domain-specific |
| 9 | `scipy.signal` | ⬜ mixed, domain-specific |
| 10 | `scipy.spatial` | ⬜ Tier 1 (distances) + Tier 3 (trees) |
| 11 | `scipy.sparse` + `scipy.sparse.linalg` | ⬜ niche but important |
| 12 | `scipy.cluster` | ⬜ Tier 2, simple |
| 13 | `scipy.constants`, `scipy.differentiate` | ⬜ trivial, do last |

---

## Module Specifications

---

### MODULE: scipy.special
**Tier 1 — pure functions**
**SciPy source**: `scipy.special`
**Predicate prefix**: `Special`

All functions are ufuncs: accept scalars or arrays, broadcast automatically.
The wrapper is mechanical: one predicate per function family. No result records.

#### Gamma and related
```
Gamma(X=, RESULT=)
    → scipy.special.gamma(x)
    RESULT: float or array

Gammaln(X=, RESULT=)
    → scipy.special.gammaln(x)        # log-gamma; more numerically stable

Gammasgn(X=, RESULT=)
    → scipy.special.gammasgn(x)       # sign of gamma

Betaln(A=, B=, RESULT=)
    → scipy.special.betaln(a, b)      # log-beta

Digamma(X=, RESULT=)
    → scipy.special.digamma(x)        # psi / logarithmic derivative of gamma

Polygamma(N=, X=, RESULT=)
    → scipy.special.polygamma(n, x)

Factorial(N=, EXACT=False, RESULT=)
    → scipy.special.factorial(n, exact=EXACT)

Comb(N=, K=, EXACT=False, REPETITION=False, RESULT=)
    → scipy.special.comb(N, K, exact=EXACT, repetition=REPETITION)

Perm(N=, K=, EXACT=False, RESULT=)
    → scipy.special.perm(N, K, exact=EXACT)
```

#### Error functions
```
Erf(X=, RESULT=)
    → scipy.special.erf(x)

Erfc(X=, RESULT=)
    → scipy.special.erfc(x)            # complementary erf

Erfinv(Y=, RESULT=)
    → scipy.special.erfinv(y)

Erfcinv(Y=, RESULT=)
    → scipy.special.erfcinv(y)

Ndtr(X=, RESULT=)
    → scipy.special.ndtr(x)            # normal CDF (area under gaussian)

Ndtri(P=, RESULT=)
    → scipy.special.ndtri(p)           # inverse normal CDF / probit
```

#### Bessel functions
```
Jn(N=, X=, RESULT=)
    → scipy.special.jn(n, x)           # Bessel J, integer order

Yn(N=, X=, RESULT=)
    → scipy.special.yn(n, x)           # Bessel Y, integer order

Jv(V=, Z=, RESULT=)
    → scipy.special.jv(v, z)           # Bessel J, real order

Yv(V=, Z=, RESULT=)
    → scipy.special.yv(v, z)

Kn(N=, X=, RESULT=)
    → scipy.special.kn(n, x)           # modified Bessel K

In(N=, X=, RESULT=)
    → scipy.special.iv(n, x)           # modified Bessel I (note: iv not in)

JnZeros(N=, NT=, RESULT=)
    → scipy.special.jn_zeros(n, nt)   # first NT zeros of Jn

SphericalJn(N=, Z=, DERIVATIVE=False, RESULT=)
    → scipy.special.spherical_jn(n, z, derivative=DERIVATIVE)
```

#### Elliptic integrals
```
Ellipk(M=, RESULT=)
    → scipy.special.ellipk(m)          # complete elliptic integral K

Ellipe(M=, RESULT=)
    → scipy.special.ellipe(m)          # complete elliptic integral E

Ellipkinc(Phi=, M=, RESULT=)
    → scipy.special.ellipkinc(phi, m)  # incomplete K

Ellipeinc(Phi=, M=, RESULT=)
    → scipy.special.ellipeinc(phi, m)  # incomplete E
```

#### Hypergeometric and related
```
Hyp1f1(A=, B=, X=, RESULT=)
    → scipy.special.hyp1f1(a, b, x)    # confluent hypergeometric 1F1

Hyp2f1(A=, B=, C=, Z=, RESULT=)
    → scipy.special.hyp2f1(a, b, c, z)

Hyp0f1(B=, X=, RESULT=)
    → scipy.special.hyp0f1(b, x)
```

#### Information theory / log-sum-exp
```
Entr(X=, RESULT=)
    → scipy.special.entr(x)            # -x*log(x); entropy element-wise

Kl_div(X=, Y=, RESULT=)
    → scipy.special.kl_div(x, y)

Logsumexp(A=, AXIS=None, B=None, KEEPDIMS=False, RESULT=)
    → scipy.special.logsumexp(a, axis=AXIS, b=B, keepdims=KEEPDIMS)
```

#### Legendre and orthogonal polynomials
```
Lpmv(M=, V=, X=, RESULT=)
    → scipy.special.lpmv(m, v, x)      # associated Legendre function

EvalLegendre(N=, X=, OUT=None, RESULT=)
    → scipy.special.eval_legendre(n, x)

EvalChebyt(N=, X=, RESULT=)
    → scipy.special.eval_chebyt(n, x)  # Chebyshev T

EvalChebyu(N=, X=, RESULT=)
    → scipy.special.eval_chebyu(n, x)  # Chebyshev U

EvalHermite(N=, X=, RESULT=)
    → scipy.special.eval_hermite(n, x)

EvalGenlaguerre(N=, ALPHA=, X=, RESULT=)
    → scipy.special.eval_genlaguerre(n, alpha, x)
```

#### Convenience / misc
```
Cbrt(X=, RESULT=)
    → scipy.special.cbrt(x)

Exp10(X=, RESULT=)
    → scipy.special.exp10(x)

Exp2(X=, RESULT=)
    → scipy.special.exp2(x)

Expit(X=, RESULT=)
    → scipy.special.expit(x)           # sigmoid: 1/(1+exp(-x))

Logit(X=, RESULT=)
    → scipy.special.logit(x)

LambertW(Z=, K=0, TOL=1e-8, RESULT=)
    → scipy.special.lambertw(z, k=K, tol=TOL)

Xlogy(X=, Y=, RESULT=)
    → scipy.special.xlogy(x, y)        # x*log(y), safe at x=0

Xlog1py(X=, Y=, RESULT=)
    → scipy.special.xlog1py(x, y)
```

---

### MODULE: scipy.linalg
**Tier 1 — pure functions; factorisation helpers are Tier 2**
**SciPy source**: `scipy.linalg`
**Predicate prefix**: `Linalg`

All inputs and outputs are NumPy arrays (passed as Python objects in the
Prolog layer). Multi-value decomposition outputs are returned as a dict
result record.

#### Linear system solvers
```
LinalgSolve(A=, B=, SYM_POS=False, LOWER=False, OVERWRITE_A=False,
            OVERWRITE_B=False, CHECK_FINITE=True, ASSUME_A='gen',
            TRANSPOSED=False, RESULT=)
    → scipy.linalg.solve(a, b, ...)
    RESULT: array X such that A @ X = B

LinalgLstsq(A=, B=, COND=None, OVERWRITE_A=False, OVERWRITE_B=False,
            CHECK_FINITE=True, LAPACK_DRIVER=None, RESULT=)
    → scipy.linalg.lstsq(a, b, ...)
    RESULT: dict {x, residuals, rank, s}
    # use LinalgResultGet(RESULT, FIELD='x', VALUE=X) to extract

LinalgSolveTriangular(A=, B=, TRANS=0, LOWER=False, UNIT_DIAGONAL=False,
                      OVERWRITE_B=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.solve_triangular(a, b, ...)
```

#### Matrix decompositions
```
LinalgLu(A=, PERMUTE_L=False, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.lu(a, ...)
    RESULT: dict {p, l, u}   (or {pl, u} when PERMUTE_L=True)

LinalgQr(A=, OVERWRITE_A=False, LWORK=None, MODE='full', PIVOTING=False,
         CHECK_FINITE=True, RESULT=)
    → scipy.linalg.qr(a, ...)
    RESULT: dict {q, r} (or {q, r, p} when PIVOTING=True)

LinalgSvd(A=, FULL_MATRICES=True, COMPUTE_UV=True, OVERWRITE_A=False,
          CHECK_FINITE=True, LAPACK_DRIVER='gesdd', RESULT=)
    → scipy.linalg.svd(a, ...)
    RESULT: dict {u, s, vh}

LinalgCholesky(A=, LOWER=False, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.cholesky(a, ...)
    RESULT: array (upper or lower triangular factor)

LinalgEig(A=, B=None, LEFT=False, RIGHT=True, OVERWRITE_A=False,
          OVERWRITE_B=False, CHECK_FINITE=True, HOMOGENEOUS_EIGVALS=False,
          RESULT=)
    → scipy.linalg.eig(a, b=B, ...)
    RESULT: dict {eigenvalues, eigenvectors}  (right vecs if RIGHT=True)

LinalgEigh(A=, B=None, LOWER=True, EIGVALS_ONLY=False, OVERWRITE_A=False,
           OVERWRITE_B=False, TYPE=1, CHECK_FINITE=True, SUBSET_BY_INDEX=None,
           SUBSET_BY_VALUE=None, DRIVER=None, RESULT=)
    → scipy.linalg.eigh(a, b=B, ...)    # symmetric/Hermitian specialisation
    RESULT: dict {eigenvalues, eigenvectors}

LinalgSchur(A=, OUTPUT='real', LWORK=None, OVERWRITE_A=False,
            SORT=None, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.schur(a, ...)
    RESULT: dict {t, z, sdim?}          # sdim only when SORT is specified
```

#### Matrix functions
```
LinalgInv(A=, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.inv(a, ...)

LinalgPinv(A=, ATOL=None, RTOL=None, RETURN_RANK=False,
           CHECK_FINITE=True, RESULT=)
    → scipy.linalg.pinv(a, ...)

LinalgDet(A=, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.det(a, ...)

LinalgNorm(A=, ORD=None, AXIS=None, KEEPDIMS=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.norm(a, ...)

LinalgExpm(A=, RESULT=)
    → scipy.linalg.expm(a)              # matrix exponential

LinalgLogm(A=, DISP=True, RESULT=)
    → scipy.linalg.logm(a, ...)         # matrix logarithm

LinalgSqrtm(A=, DISP=True, BLOCKSIZE=64, RESULT=)
    → scipy.linalg.sqrtm(a, ...)        # matrix square root

LinalgFunm(A=, FUNC=, DISP=True, RESULT=)
    → scipy.linalg.funm(a, func, ...)   # apply scalar func to matrix
```

#### Two-step factorisation helpers (pipeline pattern)
Some linalg operations naturally split into *factor* then *solve*, allowing
re-use of the factorisation across multiple RHS vectors. Model as a Tier-2
pair:
```
LinalgLuFactor(A=, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.lu_factor(a, ...)
    RESULT: opaque factorisation record (lu_piv tuple)

LinalgLuSolve(LU_PIV=, B=, TRANS=0, OVERWRITE_B=False,
              CHECK_FINITE=True, RESULT=)
    → scipy.linalg.lu_solve(lu_piv, b, ...)
    # LU_PIV is the RESULT from LinalgLuFactor

LinalgChoFactor(A=, LOWER=False, OVERWRITE_A=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.cho_factor(a, ...)

LinalgChoSolve(C_LOWER=, B=, OVERWRITE_B=False, CHECK_FINITE=True, RESULT=)
    → scipy.linalg.cho_solve(c_lower, b, ...)
```

---

### MODULE: scipy.fft
**Tier 1 — pure functions**
**SciPy source**: `scipy.fft`
**Predicate prefix**: `FFT`

```
FFTFFT(X=, N=None, AXIS=-1, NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.fft(x, ...)

FFTIfft(X=, N=None, AXIS=-1, NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.ifft(x, ...)

FFTFFT2(X=, S=None, AXES=(-2,-1), NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.fft2(x, ...)

FFTIfft2(X=, S=None, AXES=(-2,-1), NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.ifft2(x, ...)

FFTFFTn(X=, S=None, AXES=None, NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.fftn(x, ...)

FFTRfft(X=, N=None, AXIS=-1, NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.rfft(x, ...)             # real input → half-spectrum

FFTIrfft(X=, N=None, AXIS=-1, NORM=None, WORKERS=None, RESULT=)
    → scipy.fft.irfft(x, ...)

FFTDct(X=, TYPE=2, N=None, AXIS=-1, NORM=None, OVERWRITE_X=False,
       WORKERS=None, ORTHOGONALIZE=None, RESULT=)
    → scipy.fft.dct(x, ...)              # discrete cosine transform

FFTIdct(X=, TYPE=2, N=None, AXIS=-1, NORM=None, OVERWRITE_X=False,
        WORKERS=None, ORTHOGONALIZE=None, RESULT=)
    → scipy.fft.idct(x, ...)

FFTFFTfreq(N=, D=1.0, RESULT=)
    → scipy.fft.fftfreq(n, d=D)          # sample frequencies for fft output

FFTRfftfreq(N=, D=1.0, RESULT=)
    → scipy.fft.rfftfreq(n, d=D)

FFTFFTshift(X=, AXES=None, RESULT=)
    → scipy.fft.fftshift(x, ...)         # shift zero-freq to centre

FFTIfftshift(X=, AXES=None, RESULT=)
    → scipy.fft.ifftshift(x, ...)
```

**Common pipeline**: `FFTRfft` → process spectrum → `FFTIrfft`

---

### MODULE: scipy.integrate
**Tier 2 — result records**
**SciPy source**: `scipy.integrate`
**Predicate prefix**: `Integrate`

#### Quadrature (scalar integrals)
```
IntegrateQuad(FUNC=, A=, B=, ARGS=(), FULL_OUTPUT=False, LIMIT=50,
              EPSABS=1.49e-8, EPSREL=1.49e-8, RESULT=)
    → scipy.integrate.quad(func, a, b, ...)
    RESULT: dict {value, error, [infodict if FULL_OUTPUT]}

IntegrateDblquad(FUNC=, A=, B=, GFUN=, HFUN=, ARGS=(), EPSABS=1.49e-8,
                 EPSREL=1.49e-8, RESULT=)
    → scipy.integrate.dblquad(func, a, b, gfun, hfun, ...)
    RESULT: dict {value, error}

IntegrateTplquad(FUNC=, A=, B=, GFUN=, HFUN=, QFUN=, RFUN=,
                 ARGS=(), EPSABS=1.49e-8, EPSREL=1.49e-8, RESULT=)
    → scipy.integrate.tplquad(func, ...)
    RESULT: dict {value, error}

IntegrateNquad(FUNC=, RANGES=, ARGS=None, OPTS=None, FULL_OUTPUT=False,
               RESULT=)
    → scipy.integrate.nquad(func, ranges, ...)
    RESULT: dict {value, error, [out_dict if FULL_OUTPUT]}

IntegrateQuadVec(FUNC=, A=, B=, EPSABS=1e-200, EPSREL=1e-8, NORM='2',
                 CACHE_SIZE=100, LIMIT=10000, WORKERS=1,
                 POINTS=None, QUADRATURE=None, RESULT=)
    → scipy.integrate.quad_vec(func, a, b, ...)
    RESULT: dict {y, err, status, success, message, neval, intervals, integrals}
```

#### ODE solvers
```
IntegrateSolveIvp(FUN=, T_SPAN=, Y0=, METHOD='RK45', T_EVAL=None,
                  DENSE_OUTPUT=False, EVENTS=None, VECTORIZED=False,
                  ARGS=None, RESULT=, **OPTIONS)
    → scipy.integrate.solve_ivp(fun, t_span, y0, ...)
    RESULT: OdeResult dict {t, y, sol, t_events, y_events, nfev, njev,
                            nlu, status, message, success}
    # METHOD options: 'RK45','RK23','DOP853','Radau','BDF','LSODA'

IntegrateOdeint(FUNC=, Y0=, T=, ARGS=(), DFUN=None, COL_DERIV=False,
                FULL_OUTPUT=False, ML=None, MU=None, RTOL=None, ATOL=None,
                TCRIT=None, H0=0.0, HMAX=0.0, HMIN=0.0, IXPR=0,
                MXSTEP=0, MXHNIL=0, MXORDN=12, MXORDS=5,
                PRINTMESSG=0, TFIRST=False, RESULT=)
    → scipy.integrate.odeint(func, y0, t, ...)
    RESULT: dict {y, [infodict if FULL_OUTPUT]}
    # Legacy LSODA wrapper; prefer SolveIvp for new code
```

#### Cumulative / sampled integration
```
IntegrateCumulative(Y=, X=None, AXIS=-1, INITIAL=None, RESULT=)
    → scipy.integrate.cumulative_trapezoid(y, x=X, ...)
    RESULT: array

IntegrateTrapezoid(Y=, X=None, DX=1.0, AXIS=-1, RESULT=)
    → scipy.integrate.trapezoid(y, x=X, ...)
    RESULT: scalar or array

IntegrateSimpson(Y=, X=None, DX=1.0, AXIS=-1, RESULT=)
    → scipy.integrate.simpson(y, x=X, ...)
    RESULT: scalar or array
```

**ODE pipeline pattern**:
```
IntegrateSolveIvp(FUN=rhs, T_SPAN=(0,10), Y0=y0, METHOD='RK45',
                  T_EVAL=t_eval, RESULT=Sol),
IntegrateResultGet(Sol, FIELD='y', VALUE=Y),
IntegrateResultGet(Sol, FIELD='success', VALUE=Ok).
```

---

### MODULE: scipy.optimize
**Tier 2 — result records**
**SciPy source**: `scipy.optimize`
**Predicate prefix**: `Optimize`

#### Scalar minimisation
```
OptimizeMinimizeScalar(FUN=, BRACKET=None, BOUNDS=None,
                       METHOD=None, TOLS=None, OPTIONS=None, RESULT=)
    → scipy.optimize.minimize_scalar(fun, ...)
    RESULT: OptimizeResult dict {x, fun, success, message, nit, nfev}
    # METHOD options: 'brent', 'golden', 'bounded'
```

#### Multivariate minimisation
```
OptimizeMinimize(FUN=, X0=, ARGS=(), METHOD=None, JAC=None, HESS=None,
                 HESSP=None, BOUNDS=None, CONSTRAINTS=(), TOL=None,
                 CALLBACK=None, OPTIONS=None, RESULT=)
    → scipy.optimize.minimize(fun, x0, ...)
    RESULT: OptimizeResult dict {x, fun, jac, hess_inv, nfev, njev,
                                  nit, success, status, message}
    # METHOD options: 'Nelder-Mead','Powell','CG','BFGS','Newton-CG',
    #   'L-BFGS-B','TNC','COBYLA','SLSQP','trust-constr','dogleg',
    #   'trust-ncg','trust-exact','trust-krylov'
```

#### Global optimisation
```
OptimizeDifferentialEvolution(FUNC=, BOUNDS=, ARGS=(), STRATEGY='best1bin',
    MAXITER=1000, POPSIZE=15, TOL=0.01, MUTATION=(0.5,1), RECOMBINATION=0.7,
    SEED=None, CALLBACK=None, DISP=False, POLISH=True, INIT='latinhypercube',
    ATOL=0, UPDATING='immediate', WORKERS=1, CONSTRAINTS=(),
    X0=None, INTEGRALITY=None, VECTORIZED=False, RESULT=)
    → scipy.optimize.differential_evolution(func, bounds, ...)

OptimizeBasinhopping(FUNC=, X0=, NITER=100, T=1.0, STEPSIZE=0.5,
    MINIMIZER_KWARGS=None, TAKE_STEP=None, ACCEPT_TEST=None,
    CALLBACK=None, INTERVAL=50, DISP=False, NITER_SUCCESS=None,
    SEED=None, TARGET_ACCEPT_RATE=0.5, STEPWISE_FACTOR=0.9, RESULT=)
    → scipy.optimize.basinhopping(func, x0, ...)

OptimizeDualAnnealing(FUNC=, BOUNDS=, ARGS=(), MAXITER=1000,
    MINIMIZER_KWARGS=None, INITIAL_TEMP=5230, RESTART_TEMP_RATIO=2e-5,
    VISIT=2.62, ACCEPT=-5.0, MAXFUN=1e7, SEED=None, NO_LOCAL_SEARCH=False,
    CALLBACK=None, X0=None, RESULT=)
    → scipy.optimize.dual_annealing(func, bounds, ...)

OptimizeShgo(FUNC=, BOUNDS=, ARGS=(), CONSTRAINTS=None, N=100,
    ITERS=1, CALLBACK=None, MINIMIZER_KWARGS=None, OPTIONS=None,
    SAMPLING_METHOD='simplicial', WORKERS=1, RESULT=)
    → scipy.optimize.shgo(func, bounds, ...)
```

#### Least squares and curve fitting
```
OptimizeLeastSquares(FUN=, X0=, JACS='2-point', BOUNDS=(-inf,inf),
    METHOD='trf', FTOL=1e-8, XTOL=1e-8, GTOL=1e-8, X_SCALE=1.0,
    LOSS='linear', F_SCALE=1.0, MAX_NFEV=None, DIFF_STEP=None,
    TR_SOLVER=None, TR_OPTIONS=None, JACS_SPARSITY=None, VERBOSE=0,
    ARGS=(), KWARGS={}, RESULT=)
    → scipy.optimize.least_squares(fun, x0, ...)
    RESULT: OptimizeResult dict {x, cost, fun, jac, grad, optimality,
                                  active_mask, nfev, njev, status, message, success}

OptimizeCurveFit(F=, XDATA=, YDATA=, P0=None, SIGMA=None, ABSOLUTE_SIGMA=False,
    CHECK_FINITE=True, BOUNDS=(-inf,inf), METHOD=None, JAC=None,
    FULL_OUTPUT=False, NAN_POLICY=None, RESULT=)
    → scipy.optimize.curve_fit(f, xdata, ydata, ...)
    RESULT: dict {popt, pcov, [infodict, mesg, ier if FULL_OUTPUT]}
```

#### Root finding
```
OptimizeRootScalar(F=, ARGS=(), METHOD=None, BRACKET=None, FPRIME=None,
    FPRIME2=None, X0=None, X1=None, XTOL=None, RTOL=None, MAXITER=None,
    OPTIONS=None, RESULT=)
    → scipy.optimize.root_scalar(f, ...)
    RESULT: RootResults dict {root, iterations, function_calls, converged, flag}
    # METHOD options: 'bisect','brentq','brenth','ridder','toms748',
    #   'newton','secant','halley'

OptimizeRoot(FUN=, X0=, ARGS=(), METHOD=None, JAC=None, TOL=None,
    CALLBACK=None, OPTIONS=None, RESULT=)
    → scipy.optimize.root(fun, x0, ...)
    RESULT: OptimizeResult dict {x, fun, fjac, nfev, njev, status,
                                  success, message}
    # METHOD options: 'hybr','lm','broyden1','broyden2','anderson',
    #   'linearmixing','diagbroyden','excitingmixing','krylov','df-sane'
```

#### Linear and mixed-integer programming
```
OptimizeLinprog(C=, A_UB=None, B_UB=None, A_EQ=None, B_EQ=None,
    BOUNDS=None, METHOD='highs', CALLBACK=None, OPTIONS=None,
    X0=None, INTEGRALITY=None, RESULT=)
    → scipy.optimize.linprog(c, ...)
    RESULT: OptimizeResult dict {x, fun, ineqlin, eqlin, lower, upper,
                                  status, success, message, nit}

OptimizeMilp(C=, CONSTRAINTS=None, INTEGRALITY=None, BOUNDS=None,
    OPTIONS=None, RESULT=)
    → scipy.optimize.milp(c, ...)
    RESULT: OptimizeResult dict {x, fun, mip_node_count, mip_dual_bound,
                                  mip_gap, status, success, message}
    # CONSTRAINTS built via LinearConstraint; BOUNDS via Bounds
    # Helper predicates:
    #   OptimizeLinearConstraint(A=, LB=, UB=, RESULT=)
    #     → scipy.optimize.LinearConstraint(A, lb=LB, ub=UB)
    #   OptimizeBounds(LB=, UB=, KEEP_FEASIBLE=False, RESULT=)
    #     → scipy.optimize.Bounds(lb=LB, ub=UB, keep_feasible=KEEP_FEASIBLE)
```

#### Result accessor
```
OptimizeResultGet(RESULT=, FIELD=, VALUE=)
    # Field-by-field accessor for any OptimizeResult or similar dict
    # FIELD is a string: 'x', 'fun', 'success', 'message', 'nit', etc.
```

---

### MODULE: scipy.stats
**Tier 2 — result records; distributions are Tier 2/3 (frozen objects)**
**SciPy source**: `scipy.stats`
**Predicate prefix**: `Stats`

#### Descriptive statistics
```
StatsDescribe(A=, AXIS=0, DDOF=1, BIAS=True, NAN_POLICY='propagate', RESULT=)
    → scipy.stats.describe(a, ...)
    RESULT: dict {nobs, minmax, mean, variance, skewness, kurtosis}

StatsMean(A=, AXIS=None, RESULT=)          # arithmetic mean
StatsGmean(A=, AXIS=0, DTYPE=None, RESULT=)  # geometric mean
StatsHmean(A=, AXIS=0, DTYPE=None, RESULT=)  # harmonic mean

StatsMode(A=, AXIS=0, NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.mode(a, ...)
    RESULT: dict {mode, count}

StatsSkew(A=, AXIS=0, BIAS=True, NAN_POLICY='propagate',
          KEEPDIMS=False, RESULT=)
    → scipy.stats.skew(a, ...)

StatsKurtosis(A=, AXIS=0, FISHER=True, BIAS=True, NAN_POLICY='propagate',
              KEEPDIMS=False, RESULT=)
    → scipy.stats.kurtosis(a, ...)

StatsIqr(X=, RNG=(25,75), SCALE=1.0, NAN_POLICY='propagate',
         INTERPOLATION='linear', KEEPDIMS=False, RESULT=)
    → scipy.stats.iqr(x, ...)

StatsZscore(A=, AXIS=0, DDOF=0, NAN_POLICY='propagate', RESULT=)
    → scipy.stats.zscore(a, ...)

StatsMedianAbsDeviation(X=, AXIS=0, CENTER=None, SCALE=1.4826,
    NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.median_abs_deviation(x, ...)
```

#### Correlation and regression
```
StatsPearsonr(X=, Y=, ALTERNATIVE='two-sided', METHOD=None, RESULT=)
    → scipy.stats.pearsonr(x, y, ...)
    RESULT: dict {statistic, pvalue}

StatsSpearmanr(A=, B=None, AXIS=0, NAN_POLICY='propagate',
               ALTERNATIVE='two-sided', RESULT=)
    → scipy.stats.spearmanr(a, b=B, ...)
    RESULT: dict {statistic, pvalue}

StatsKendalltau(X=, Y=, NAN_POLICY='propagate', METHOD='auto',
                ALTERNATIVE='two-sided', RESULT=)
    → scipy.stats.kendalltau(x, y, ...)
    RESULT: dict {statistic, pvalue}

StatsLinregress(X=, Y=None, ALTERNATIVE='two-sided', RESULT=)
    → scipy.stats.linregress(x, y=Y, ...)
    RESULT: dict {slope, intercept, rvalue, pvalue, stderr,
                  intercept_stderr}

StatsTheilslopes(Y=, X=None, ALPHA=0.95, METHOD='separate',
                 RESULT=)
    → scipy.stats.theilslopes(y, ...)
    RESULT: dict {slope, intercept, low_slope, high_slope}
```

#### Hypothesis tests — parametric
```
StatsTtest1samp(A=, POPMEAN=, AXIS=0, NAN_POLICY='propagate',
    ALTERNATIVE='two-sided', KEEPDIMS=False, RESULT=)
    → scipy.stats.ttest_1samp(a, popmean, ...)
    RESULT: dict {statistic, pvalue, df}

StatsTtestInd(A=, B=, AXIS=0, EQUAL_VAR=True, NAN_POLICY='propagate',
    PERMUTATIONS=None, RANDOM_STATE=None, ALTERNATIVE='two-sided',
    TRIM=0, KEEPDIMS=False, RESULT=)
    → scipy.stats.ttest_ind(a, b, ...)
    RESULT: dict {statistic, pvalue, df}

StatsTtestRel(A=, B=, AXIS=0, NAN_POLICY='propagate',
    ALTERNATIVE='two-sided', KEEPDIMS=False, RESULT=)
    → scipy.stats.ttest_rel(a, b, ...)
    RESULT: dict {statistic, pvalue, df}

StatsFOneway(ARGS=, AXIS=0, NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.f_oneway(*deref(ARGS), ...)
    # ARGS: Python list of arrays, e.g. ++[group1, group2, group3]
    RESULT: dict {statistic, pvalue}

StatsChisquare(F_OBS=, F_EXP=None, DDOF=0, AXIS=0, RESULT=)
    → scipy.stats.chisquare(f_obs, ...)
    RESULT: dict {statistic, pvalue}

StatsChi2Contingency(OBSERVED=, CORRECTION=True, LAMBDA_=None, RESULT=)
    → scipy.stats.chi2_contingency(observed, ...)
    RESULT: dict {statistic, pvalue, dof, expected_freq}

StatsFisherExact(TABLE=, ALTERNATIVE='two-sided', RESULT=)
    → scipy.stats.fisher_exact(table, ...)
    RESULT: dict {statistic, pvalue}
```

#### Hypothesis tests — nonparametric
```
StatsMannwhitneyu(X=, Y=, USE_CONTINUITY=True, ALTERNATIVE='two-sided',
    AXIS=0, METHOD='auto', NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.mannwhitneyu(x, y, ...)
    RESULT: dict {statistic, pvalue}

StatsWilcoxon(X=, Y=None, ZERO_METHOD='wilcox', CORRECTION=False,
    ALTERNATIVE='two-sided', METHOD='auto', AXIS=0,
    NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.wilcoxon(x, ...)
    RESULT: dict {statistic, pvalue}

StatsKruskal(ARGS=, NAN_POLICY='propagate', AXIS=0,
             KEEPDIMS=False, RESULT=)
    → scipy.stats.kruskal(*deref(ARGS), ...)
    # ARGS: Python list of arrays
    RESULT: dict {statistic, pvalue}

StatsFriedmanchisquare(ARGS=, RESULT=)
    → scipy.stats.friedmanchisquare(*deref(ARGS))
    # ARGS: Python list of arrays (each is one repeated-measures condition)
    RESULT: dict {statistic, pvalue}

StatsKstest(RVSD=, CDF=, ARGS=(), N=20, ALTERNATIVE='two-sided',
    METHOD='auto', RESULT=)
    → scipy.stats.kstest(rvs, cdf, ...)
    RESULT: dict {statistic, pvalue, statistic_location, statistic_sign}

StatsKs2samp(DATA1=, DATA2=, ALTERNATIVE='two-sided',
             METHOD='auto', RESULT=)
    → scipy.stats.ks_2samp(data1, data2, ...)
    RESULT: dict {statistic, pvalue, statistic_location, statistic_sign}

StatsNormaltest(A=, AXIS=0, NAN_POLICY='propagate', KEEPDIMS=False, RESULT=)
    → scipy.stats.normaltest(a, ...)
    RESULT: dict {statistic, pvalue}

StatsShapiro(X=, RESULT=)
    → scipy.stats.shapiro(x)
    RESULT: dict {statistic, pvalue}

StatsAndersonDarling(X=, DIST='norm', RESULT=)
    → scipy.stats.anderson(x, dist=DIST)
    RESULT: dict {statistic, critical_values, significance_level, fit_result}
```

#### Distributions (frozen-object pattern)
SciPy distributions have both a functional and an object-oriented interface.
Map the functional interface directly as Tier 1 calls under each distribution
name, and the frozen-object interface as Tier 3 handles.

**Tier 1 (functional) — call directly on named distribution**:
```
StatsDist(DIST=, METHOD=, X=, **PARAMS, RESULT=)
    # Generic dispatcher; METHOD is one of: 'pdf','logpdf','cdf','logcdf',
    # 'sf','logsf','ppf','isf','rvs','stats','moment','entropy','fit'
    # DIST is a string: 'norm','t','chi2','f','expon','gamma','beta',
    #   'lognorm','uniform','binom','poisson','nbinom', etc.
    # PARAMS are the distribution parameters: loc=, scale=, a=, etc.
    # Examples:
    #   StatsDist(DIST='norm', METHOD='pdf', X=1.5, LOC=0, SCALE=1, RESULT=P)
    #   StatsDist(DIST='t', METHOD='ppf', X=0.975, DF=10, RESULT=T)
```

**Convenience shorthands for most common distributions**:
```
StatsNormPdf(X=, LOC=0, SCALE=1, RESULT=)
StatsNormCdf(X=, LOC=0, SCALE=1, RESULT=)
StatsNormPpf(Q=, LOC=0, SCALE=1, RESULT=)
StatsNormRvs(LOC=0, SCALE=1, SIZE=None, RANDOM_STATE=None, RESULT=)
StatsNormFit(DATA=, RESULT=)              # → dict {loc, scale}

StatsTDist(DF=, METHOD=, X=, LOC=0, SCALE=1, RESULT=)
StatsChi2Dist(DF=, METHOD=, X=, LOC=0, SCALE=1, RESULT=)
StatsGammaDist(A=, METHOD=, X=, LOC=0, SCALE=1, RESULT=)
StatsBetaDist(A=, B=, METHOD=, X=, LOC=0, SCALE=1, RESULT=)
```

**Tier 3 (frozen distribution handle)**:
```
StatsFreezeDist(DIST=, PARAMS=, RESULT=HANDLE)
    # Creates a frozen distribution object; HANDLE is an opaque integer ref
    # PARAMS: Python dict of distribution parameters, e.g. ++{'loc': 2.0, 'scale': 0.5}
    # Example: StatsFreezeDist(DIST='norm', PARAMS=++{'loc': 2.0, 'scale': 0.5}, RESULT=H)

StatsFrozenPdf(HANDLE=, X=, RESULT=)
StatsFrozenCdf(HANDLE=, X=, RESULT=)
StatsFrozenPpf(HANDLE=, Q=, RESULT=)
StatsFrozenRvs(HANDLE=, SIZE=None, RANDOM_STATE=None, RESULT=)
StatsFrozenStats(HANDLE=, MOMENTS='mv', RESULT=)
    # RESULT: dict with requested moments (mean, variance, skewness, kurtosis)
StatsFrozenFree(HANDLE=)
    # Release the Python-side frozen distribution object
```

---

### MODULE: scipy.interpolate
**Tier 3 — handle predicates**
**SciPy source**: `scipy.interpolate`
**Predicate prefix**: none (module name acts as namespace)

All objects are constructed with `Make*` predicates, used with `Eval*`
predicates, and released with `Free`.

```
MakeSpline(X=, Y=, K=3, BC_TYPE=None, AXIS=0, RESULT=HANDLE)
    → scipy.interpolate.make_interp_spline(x, y, k=K, bc_type=BC_TYPE)
    # Recommended 1D spline constructor; returns BSpline object

EvalSpline(HANDLE=, X=, NU=0, EXTRAPOLATE=None, RESULT=)
    # Evaluate spline (or its NU-th derivative) at points X

MakeCubic(X=, Y=, AXIS=0, BC_TYPE='not-a-knot', EXTRAPOLATE=None,
                RESULT=HANDLE)
    → scipy.interpolate.CubicSpline(x, y, ...)

MakePCHIP(X=, Y=, AXIS=0, EXTRAPOLATE=None, RESULT=HANDLE)
    → scipy.interpolate.PchipInterpolator(x, y, ...)
    # Monotone cubic; good for data with outliers

MakeAkima(X=, Y=, AXIS=0, RESULT=HANDLE)
    → scipy.interpolate.Akima1DInterpolator(x, y)

MakeLinear1D(X=, Y=, KIND='linear', AXIS=0, BOUNDS_ERROR=True,
                   FILL_VALUE=nan, ASSUME_SORTED=False, RESULT=HANDLE)
    → scipy.interpolate.interp1d(x, y, kind=KIND, ...)
    # Supports: 'linear','nearest','nearest-up','zero','slinear',
    #   'quadratic','cubic','previous','next'

MakeRegularGrid(POINTS=, VALUES=, METHOD='linear', BOUNDS_ERROR=True,
                      FILL_VALUE=nan, RESULT=HANDLE)
    → scipy.interpolate.RegularGridInterpolator(points, values, ...)
    # N-D interpolation on a regular (rectilinear) grid

EvalRegularGrid(HANDLE=, XI=, METHOD=None, RESULT=)
    # XI: array of query points shape (..., ndim)

MakeRadialBasis(X=, Y=, FUNCTION='multiquadric', EPSILON=None, SMOOTH=0,
              NORM='euclidean', MODE='1-D', RESULT=HANDLE)
    → scipy.interpolate.RBFInterpolator(x, y, ...)
    # Radial basis function interpolation

EvalRadialBasis(HANDLE=, X=, RESULT=)

SplineIntegral(HANDLE=, A=, B=, RESULT=)
    # Definite integral of spline from A to B
    # Calls handle.integrate(a, b)

SplineDerivative(HANDLE=, ORDER=1, RESULT=NEW_HANDLE)
    # Returns a new spline handle representing the derivative

SplineRoots(HANDLE=, RESULT=)
    # Returns roots (zero-crossings) of the spline

Free(HANDLE=)
    # Release handle from Python-side registry
```

**Interpolation pipeline pattern**:
```
MakeSpline(X=xs, Y=ys, K=3, RESULT=H),
EvalSpline(HANDLE=H, X=new_xs, NU=0, RESULT=YInterp),
SplineIntegral(HANDLE=H, A=0.0, B=10.0, RESULT=Area),
Free(HANDLE=H).
```

---

### MODULE: scipy.spatial
**Tier 1 — distance functions (pure)**
**Tier 3 — tree/hull objects (handle)**
**SciPy source**: `scipy.spatial`, `scipy.spatial.distance`, `scipy.spatial.transform`
**Predicate prefix**: `Spatial`

#### Distance functions (pure, Tier 1)
```
SpatialCdist(XA=, XB=, METRIC='minkowski', OUT=None, KWARGS=None, RESULT=)
    → scipy.spatial.distance.cdist(XA, XB, metric=METRIC, **(KWARGS or {}))
    # KWARGS: optional Python dict of extra metric-specific keyword args
    RESULT: distance matrix (nA x nB array)

SpatialPdist(X=, METRIC='minkowski', OUT=None, KWARGS=None, RESULT=)
    → scipy.spatial.distance.pdist(X, metric=METRIC, **(KWARGS or {}))
    # KWARGS: optional Python dict of extra metric-specific keyword args
    RESULT: condensed distance vector

SpatialSquareform(X=, FORCE='no', CHECKS=True, RESULT=)
    → scipy.spatial.distance.squareform(X, ...)
    # Convert between condensed and square distance matrices

SpatialDistanceMetric(METRIC=, X=, Y=, RESULT=)
    # Single-pair scalar distance for named metric
    # METRIC: 'euclidean','cityblock','cosine','correlation','chebyshev',
    #   'canberra','braycurtis','jensenshannon','mahalanobis', etc.

SpatialConvexHullArea(HANDLE=, RESULT=)
    # area attribute of ConvexHull
SpatialConvexHullVolume(HANDLE=, RESULT=)
SpatialConvexHullVertices(HANDLE=, RESULT=)
SpatialConvexHullSimplices(HANDLE=, RESULT=)
```

#### KDTree (Tier 3)
```
SpatialMakeKdtree(DATA=, LEAFSIZE=10, COMPACT_NODES=True,
                  COPY_DATA=False, BALANCED_TREE=True,
                  BOXSIZE=None, RESULT=HANDLE)
    → scipy.spatial.KDTree(data, ...)

SpatialKdtreeQuery(HANDLE=, X=, K=1, EPS=0, P=2, DISTANCE_UPPER_BOUND=inf,
                   WORKERS=1, RESULT=)
    → handle.query(x, k=K, ...)
    RESULT: dict {distances, indices}

SpatialKdtreeQueryBall(HANDLE=, X=, R=, P=2.0, EPS=0, WORKERS=1,
                       RETURN_SORTED=None, RETURN_LENGTH=False, RESULT=)
    → handle.query_ball_point(x, r, ...)

SpatialKdtreeQueryPairs(HANDLE=, R=, P=2.0, EPS=0, OUTPUT_TYPE='set', RESULT=)
    → handle.query_pairs(r, ...)
```

#### ConvexHull (Tier 3)
```
SpatialMakeConvexHull(POINTS=, INCREMENTAL=False, QHULL_OPTIONS='', RESULT=HANDLE)
    → scipy.spatial.ConvexHull(points, ...)

SpatialConvexHullAttr(HANDLE=, ATTR=, RESULT=)
    # ATTR: 'vertices','simplices','equations','area','volume',
    #   'coplanar','good','neighbors'
```

#### Delaunay (Tier 3)
```
SpatialMakeDelaunay(POINTS=, FURTHEST_SITE=False, INCREMENTAL=False,
                    QHULL_OPTIONS='', RESULT=HANDLE)
    → scipy.spatial.Delaunay(points, ...)

SpatialDelaunayFindSimplex(HANDLE=, XI=, BRUTEFORCE=False,
                           TOL=None, RESULT=)
    → handle.find_simplex(xi, ...)
```

#### Rotation (Tier 3)
```
SpatialMakeRotation(METHOD=, DATA=, RESULT=HANDLE)
    → scipy.spatial.transform.Rotation.from_*(data)
    # METHOD: 'quat','matrix','rotvec','euler','mrp','davenport'

SpatialRotationApply(HANDLE=, VECTORS=, INVERSE=False, RESULT=)
    → handle.apply(vectors, inverse=INVERSE)

SpatialRotationAs(HANDLE=, FORM=, RESULT=)
    → handle.as_quat() / as_matrix() / as_rotvec() / as_euler(seq)
    # FORM: 'quat','matrix','rotvec','euler'
    # For euler: also pass SEQ= e.g. 'xyz'

SpatialRotationCompose(HANDLE_A=, HANDLE_B=, RESULT=HANDLE)
    → handle_a * handle_b

SpatialRotationInverse(HANDLE=, RESULT=HANDLE)
    → handle.inv()
```

---

### MODULE: scipy.ndimage
**Tier 1 — pure functions**
**SciPy source**: `scipy.ndimage`
**Predicate prefix**: `Ndimage`

```
NdimageGaussianFilter(INPUT=, SIGMA=, ORDER=0, OUTPUT=None, MODE='reflect',
    CVAL=0.0, TRUNCATE=4.0, AXES=None, RESULT=)
    → scipy.ndimage.gaussian_filter(input, sigma, ...)

NdimageUniformFilter(INPUT=, SIZE=3, OUTPUT=None, MODE='reflect',
    CVAL=0.0, ORIGIN=0, AXES=None, RESULT=)
    → scipy.ndimage.uniform_filter(input, ...)

NdimageMedianFilter(INPUT=, SIZE=None, FOOTPRINT=None, OUTPUT=None,
    MODE='reflect', CVAL=0.0, ORIGIN=0, RESULT=)
    → scipy.ndimage.median_filter(input, ...)

NdimageConvolve(INPUT=, WEIGHTS=, OUTPUT=None, MODE='reflect', CVAL=0.0,
    ORIGIN=0, RESULT=)
    → scipy.ndimage.convolve(input, weights, ...)

NdimageLabel(INPUT=, STRUCTURE=None, OUTPUT=None, RESULT=)
    → scipy.ndimage.label(input, ...)
    RESULT: dict {label_array, num_features}

NdimageBinaryErosion(INPUT=, STRUCTURE=None, ITERATIONS=1, MASK=None,
    OUTPUT=None, BORDER_VALUE=0, ORIGIN=0, BRUTE_FORCE=False, RESULT=)
    → scipy.ndimage.binary_erosion(input, ...)

NdimageBinaryDilation(INPUT=, STRUCTURE=None, ITERATIONS=1, MASK=None,
    OUTPUT=None, BORDER_VALUE=0, ORIGIN=0, BRUTE_FORCE=False, RESULT=)
    → scipy.ndimage.binary_dilation(input, ...)

NdimageBinaryOpening(INPUT=, STRUCTURE=None, ITERATIONS=1, OUTPUT=None,
    ORIGIN=0, MASK=None, BORDER_VALUE=0, BRUTE_FORCE=False, RESULT=)
    → scipy.ndimage.binary_opening(input, ...)

NdimageBinaryClosing(INPUT=, STRUCTURE=None, ITERATIONS=1, OUTPUT=None,
    ORIGIN=0, MASK=None, BORDER_VALUE=0, BRUTE_FORCE=False, RESULT=)
    → scipy.ndimage.binary_closing(input, ...)

NdimageZoom(INPUT=, ZOOM=, OUTPUT=None, ORDER=3, MODE='constant',
    CVAL=0.0, PREFILTER=True, GRID_MODE=False, RESULT=)
    → scipy.ndimage.zoom(input, zoom, ...)

NdimageRotate(INPUT=, ANGLE=, AXES=(1,0), RESHAPE=True, OUTPUT=None,
    ORDER=3, MODE='constant', CVAL=0.0, PREFILTER=True, RESULT=)
    → scipy.ndimage.rotate(input, angle, ...)

NdimageShift(INPUT=, SHIFT=, OUTPUT=None, ORDER=3, MODE='constant',
    CVAL=0.0, PREFILTER=True, RESULT=)
    → scipy.ndimage.shift(input, shift, ...)

NdimageFindObjects(INPUT=, MAX_LABEL=0, RESULT=)
    → scipy.ndimage.find_objects(input, ...)
    RESULT: list of slice tuples per labelled region

NdimageCenterOfMass(INPUT=, LABELS=None, INDEX=None, RESULT=)
    → scipy.ndimage.center_of_mass(input, ...)
```

---

### MODULE: scipy.signal
**Tier 1 — filter design functions (pure)**
**Tier 2 — filtering functions (result or array)**
**Tier 3 — LTI system objects (handle)**
**SciPy source**: `scipy.signal`
**Predicate prefix**: `Signal`

#### Filter design (pure, Tier 1)
```
SignalButter(N=, WN=, BTYPE='low', ANALOG=False, OUTPUT='ba', FS=None, RESULT=)
    → scipy.signal.butter(N, Wn, ...)
    RESULT: dict {b, a} (or {z, p, k} for OUTPUT='zpk', {sos} for 'sos')

SignalBessel(N=, WN=, BTYPE='low', ANALOG=False, OUTPUT='ba', NORM='phase',
    FS=None, RESULT=)
    → scipy.signal.bessel(N, Wn, ...)

SignalCheby1(N=, RP=, WN=, BTYPE='low', ANALOG=False, OUTPUT='ba',
    FS=None, RESULT=)
    → scipy.signal.cheby1(N, rp, Wn, ...)

SignalCheby2(N=, RS=, WN=, BTYPE='low', ANALOG=False, OUTPUT='ba',
    FS=None, RESULT=)
    → scipy.signal.cheby2(N, rs, Wn, ...)

SignalEllip(N=, RP=, RS=, WN=, BTYPE='low', ANALOG=False, OUTPUT='ba',
    FS=None, RESULT=)
    → scipy.signal.ellip(N, rp, rs, Wn, ...)

SignalFreqz(B=, A=1, WORSEN=512, WHOLE=False, PLOT=None, FS=(2*pi),
    INCLUDE_NYQUIST=False, RESULT=)
    → scipy.signal.freqz(b, a, ...)
    RESULT: dict {w, h}    # frequencies and complex frequency response
```

#### Filtering (Tier 1/2)
```
SignalLfilter(B=, A=, X=, AXIS=-1, ZI=None, RESULT=)
    → scipy.signal.lfilter(b, a, x, ...)
    RESULT: array (or dict {y, zf} when ZI provided)

SignalSosfilt(SOS=, X=, AXIS=-1, ZI=None, RESULT=)
    → scipy.signal.sosfilt(sos, x, ...)
    # SOS form more numerically stable; use OUTPUT='sos' in filter design

SignalFiltfilt(B=, A=, X=, AXIS=-1, PADTYPE='odd', PADLEN=None,
    METHOD='pad', IRLEN=None, RESULT=)
    → scipy.signal.filtfilt(b, a, x, ...)    # zero-phase (forward-backward)

SignalSosfiltfilt(SOS=, X=, AXIS=-1, PADTYPE='odd', PADLEN=None, RESULT=)
    → scipy.signal.sosfiltfilt(sos, x, ...)

SignalDecimate(X=, Q=, N=None, FTY='iir', ZERO_PHASE=True, AXIS=-1, RESULT=)
    → scipy.signal.decimate(x, q, ...)

SignalResample(X=, NUM=, T=None, AXIS=0, WINDOW=None, DOMAIN='time', RESULT=)
    → scipy.signal.resample(x, num, ...)
```

#### Convolution and correlation (pure, Tier 1)
```
SignalConvolve(IN1=, IN2=, MODE='full', METHOD='auto', RESULT=)
    → scipy.signal.convolve(in1, in2, ...)

SignalCorrelate(IN1=, IN2=, MODE='full', METHOD='auto', RESULT=)
    → scipy.signal.correlate(in1, in2, ...)

SignalFFTconvolve(IN1=, IN2=, MODE='full', AXES=None, RESULT=)
    → scipy.signal.fftconvolve(in1, in2, ...)
```

#### Spectral analysis (Tier 2)
```
SignalPeriodogram(X=, FS=1.0, WINDOW='boxcar', NFFT=None, DETREND='constant',
    RETURN_ONESIDED=True, SCALING='density', AXIS=-1, RESULT=)
    → scipy.signal.periodogram(x, ...)
    RESULT: dict {f, Pxx}

SignalWelch(X=, FS=1.0, WINDOW='hann', NPERSEG=None, NOVERLAP=None,
    NFFT=None, DETREND='constant', RETURN_ONESIDED=True,
    SCALING='density', AXIS=-1, AVERAGE='mean', RESULT=)
    → scipy.signal.welch(x, ...)
    RESULT: dict {f, Pxx}

SignalSpectrogram(X=, FS=1.0, WINDOW=('tukey',0.25), NPERSEG=None,
    NOVERLAP=None, NFFT=None, DETREND='constant', RETURN_ONESIDED=True,
    SCALING='density', AXIS=-1, MODE='psd', RESULT=)
    → scipy.signal.spectrogram(x, ...)
    RESULT: dict {f, t, Sxx}
```

**Filter design → filter application pipeline**:
```
SignalButter(N=4, WN=0.1, BTYPE='low', OUTPUT='sos', RESULT=Filter),
SignalResultGet(Filter, FIELD='sos', VALUE=SOS),
SignalSosfiltfilt(SOS=SOS, X=raw_signal, RESULT=Filtered).
% or with ++ escape:
% SignalSosfiltfilt(SOS=++Filter['sos'], X=raw_signal, RESULT=Filtered).
```

---

### MODULE: scipy.cluster
**Tier 2 — result records (linkage arrays + flat labels)**
**SciPy source**: `scipy.cluster.hierarchy`, `scipy.cluster.vq`
**Predicate prefix**: `Cluster`

#### Hierarchical clustering
```
ClusterLinkage(Y=, METHOD='single', METRIC='euclidean', OPTIMAL_ORDERING=False,
               RESULT=)
    → scipy.cluster.hierarchy.linkage(y, method=METHOD, ...)
    RESULT: (n-1) x 4 linkage matrix Z
    # METHOD: 'single','complete','average','weighted','centroid',
    #   'median','ward'

ClusterFcluster(Z=, T=, CRITERION='inconsistent', DEPTH=2, R=None,
                MONOCRIT=None, RESULT=)
    → scipy.cluster.hierarchy.fcluster(Z, t, ...)
    RESULT: flat cluster assignment array (n,)

ClusterDendrogram(Z=, P=30, TRUNCATE_MODE=None, COLOR_THRESHOLD=None,
    GET_LEAVES=True, ORIENTATION='top', LABELS=None, COUNT_SORT=False,
    DISTANCE_SORT=False, SHOW_LEAF_COUNTS=True, NO_PLOT=True,
    NO_LABELS=False, LEAF_FONT_SIZE=None, LEAF_ROTATION=None,
    LEAF_LABEL_FUNC=None, SHOW_CONTRACTED=False, LINK_COLOR_FUNC=None,
    AX=None, ABOVE_THRESHOLD_COLOR='C0', RESULT=)
    → scipy.cluster.hierarchy.dendrogram(Z, ...)
    RESULT: dict {icoord, dcoord, ivl, leaves, color_list}

ClusterCophenet(Z=, Y=None, RESULT=)
    → scipy.cluster.hierarchy.cophenet(Z, Y=Y)
    RESULT: dict {c, d}   # cophenetic correlation + cophenetic distances

ClusterInconsistent(Z=, D=2, RESULT=)
    → scipy.cluster.hierarchy.inconsistent(Z, d=D)
```

#### Vector quantisation (k-means)
```
ClusterKmeans2(DATA=, K=, ITER=10, THRESH=1e-5, MINIT='random',
    MISSING='warn', CHECK_FINITE=True, SEED=None, RESULT=)
    → scipy.cluster.vq.kmeans2(data, k, ...)
    RESULT: dict {centroid, label}

ClusterKmeans(OBS=, K_OR_GUESS=, ITER=10, THRESH=1e-5, CHECK_FINITE=True,
    SEED=None, RESULT=)
    → scipy.cluster.vq.kmeans(obs, k_or_guess, ...)
    RESULT: dict {codebook, distortion}

ClusterVq(OBS=, CODE_BOOK=, CHECK_FINITE=True, RESULT=)
    → scipy.cluster.vq.vq(obs, code_book, ...)
    RESULT: dict {code, dist}

ClusterWhiten(OBS=, CHECK_FINITE=True, RESULT=)
    → scipy.cluster.vq.whiten(obs, ...)
    RESULT: normalised observation array
```

**Hierarchical clustering pipeline**:
```
ClusterLinkage(Y=data, METHOD='ward', RESULT=Z),
ClusterFcluster(Z=Z, T=3, CRITERION='maxclust', RESULT=Labels).
```

---

### MODULE: scipy.sparse (overview only — implement on demand)
**Tier 3 — handle (sparse matrix objects)**
**SciPy source**: `scipy.sparse`, `scipy.sparse.linalg`
**Predicate prefix**: `Sparse`

Sparse matrix objects are large mutable data structures. The wrapper should
expose construction + the most common solver interface. Full matrix algebra
methods (`+`, `@`, slice, etc.) are out of scope for an initial port.

```
SparseMakeCsr(DATA=, INDICES=, INDPTR=, SHAPE=None, DTYPE=None, RESULT=HANDLE)
    → scipy.sparse.csr_matrix((data, indices, indptr), shape=SHAPE)

SparseMakeCsc(DATA=, INDICES=, INDPTR=, SHAPE=None, DTYPE=None, RESULT=HANDLE)
    → scipy.sparse.csc_matrix(...)

SparseMakeCoo(DATA=, ROW=, COL=, SHAPE=None, DTYPE=None, RESULT=HANDLE)
    → scipy.sparse.coo_matrix((data, (row, col)), shape=SHAPE)

SparseMakeDiags(DIAGONALS=, OFFSETS=0, SHAPE=None, FORMAT=None,
                DTYPE=None, RESULT=HANDLE)
    → scipy.sparse.diags(diagonals, offsets=OFFSETS, ...)

SparseMakeEye(N=, M=None, K=0, DTYPE='d', FORMAT=None, RESULT=HANDLE)
    → scipy.sparse.eye(N, M=M, k=K, ...)

SparseToDense(HANDLE=, ORDER=None, OUT=None, RESULT=)
    → handle.toarray(order=ORDER, out=OUT)

SparseToHandle(DENSE=, FORMAT='csr', DTYPE=None, RESULT=HANDLE)
    → scipy.sparse.csr_matrix(dense) or similar

SparseShape(HANDLE=, RESULT=)
SparseNnz(HANDLE=, RESULT=)    # number of stored elements

SparseLinalg_Spsolve(A=, B=, PERMC_SPEC=None, USE_UMFPACK=True, RESULT=)
    → scipy.sparse.linalg.spsolve(A, b, ...)
    # A=HANDLE, B=dense array; RESULT=dense array X

SparseLinalg_Eigsh(A=, K=6, M=None, SIGMA=None, WHICH='LM', V0=None,
    NCVS=None, MAXITER=None, TOL=0, RETURN_EIGENVECTORS=True,
    RESULT=)
    → scipy.sparse.linalg.eigsh(A, k=K, ...)
    RESULT: dict {eigenvalues, eigenvectors}

SparseLinalg_Svds(A=, K=6, NCVS=None, TOL=0, WHICH='LM', V0=None,
    MAXITER=None, RETURN_SINGULAR_VECTORS=True, SOLVER='arpack',
    RANDOM_STATE=None, OPTIONS=None, RESULT=)
    → scipy.sparse.linalg.svds(A, k=K, ...)
    RESULT: dict {u, s, vt}
```

---

### MODULE: scipy.constants (trivial — Tier 1)
**SciPy source**: `scipy.constants`
**Predicate prefix**: `Const`

All values are floats; no computation involved.

```
ConstValue(NAME=, RESULT=)
    → scipy.constants.value(name)       # CODATA constant by name string
    # Examples: NAME='speed of light in vacuum', 'Planck constant',
    #   'Avogadro constant', 'elementary charge', 'Boltzmann constant'

ConstUnit(NAME=, RESULT=)
    → scipy.constants.unit(name)        # unit string for named constant

ConstPrecision(NAME=, RESULT=)
    → scipy.constants.precision(name)   # relative uncertainty

# Physical constants as direct predicates (no args):
ConstC(RESULT=)          # speed of light: 299792458.0
ConstH(RESULT=)          # Planck constant: 6.62607015e-34
ConstHbar(RESULT=)       # h / (2*pi)
ConstG(RESULT=)          # gravitational constant
ConstNa(RESULT=)         # Avogadro constant
ConstKb(RESULT=)         # Boltzmann constant
ConstEcharge(RESULT=)    # elementary charge
ConstMe(RESULT=)         # electron mass
ConstMp(RESULT=)         # proton mass

# Conversion factors:
ConstEv(RESULT=)         # electron volt in joules
ConstAtm(RESULT=)        # standard atmosphere in pascals
ConstKilo(RESULT=)       # 1e3
ConstMega(RESULT=)       # 1e6
ConstGiga(RESULT=)       # 1e9
```

---

### MODULE: scipy.differentiate (Tier 1)
**SciPy source**: `scipy.differentiate`
**Predicate prefix**: `Diff`

```
DiffDerivative(F=, X=, ARGS=(), TOLERANCES=None, MAXITER=10,
               ORDER=8, INITIAL_STEP=0.5, STEP_FACTOR=2.0,
               STEP_DIRECTION=0, PRESERVE_SHAPE=False,
               CALLBACK=None, RESULT=)
    → scipy.differentiate.derivative(f, x, ...)
    RESULT: dict {x, df, error, success, status, nfev, nit}

DiffJacobian(F=, X=, ARGS=(), TOLERANCES=None, MAXITER=10,
             ORDER=8, INITIAL_STEP=0.5, STEP_FACTOR=2.0,
             STEP_DIRECTION=0, PRESERVE_SHAPE=False,
             CALLBACK=None, RESULT=)
    → scipy.differentiate.jacobian(f, x, ...)
    RESULT: dict {x, df, error, success, status, nfev, nit}

DiffHessian(F=, X=, ARGS=(), TOLERANCES=None, MAXITER=10,
            ORDER=8, INITIAL_STEP=0.5, STEP_FACTOR=2.0,
            PRESERVE_SHAPE=False, CALLBACK=None, RESULT=)
    → scipy.differentiate.hessian(f, x, ...)
    RESULT: dict {x, ddf, error, success, status, nfev, nit}
```

---

## Cross-cutting Concerns for Implementors

### Array handling
All array arguments (`X=`, `A=`, `DATA=`, etc.) accept Python lists, NumPy
arrays, or anything that NumPy can coerce. The wrapper should call
`numpy.asarray()` on all numeric array inputs before passing to SciPy.

### Error handling
SciPy functions raise `ValueError`, `LinAlgError`, or return a result with
`success=False`. The clausal wrapper should map these uniformly:
- Runtime errors → re-raise as a clausal `LogicException` via `throw/1`, so
  callers can catch with `catch/3`. Use `clausal.logic.exceptions.LogicException`
  and wrap the original Python exception message in an `error(scipy_error(msg), _)`
  term.
- `success=False` results → predicate still **succeeds** but `RESULT['success']`
  is `False`; the caller checks this field. Do not fail the predicate on a
  `success=False` result — that makes it impossible to inspect the partial result.

### NaN policy
Many `scipy.stats` functions accept `NAN_POLICY=` with values
`'propagate'`, `'omit'`, or `'raise'`. Default to `'propagate'` in all
wrappers unless overridden by the caller.

### Workers / parallelism
Several functions accept `WORKERS=` (number of threads). Default to `1`
(serial) in the wrapper; expose the argument for callers that want parallelism.

### Handle registry
Tier 3 handles are plain Python integers stored in a module-level `dict`.
They flow through clausal variables as ordinary Python values — no special
atom encoding is needed. Use the `_register` / `_lookup` / `_free` pattern
shown in the Implementation layout section above. The registry is
module-level (not global interpreter state). Each Tier 3 module should
expose a `FreeAll()` predicate that calls `_HANDLES.clear()`.

### Result record accessors
Every Tier 2 predicate that returns a `RESULT=` dict should be accompanied by
a module-namespaced accessor:
```
<Prefix>ResultGet(RESULT=, FIELD=, VALUE=)
```
This avoids callers having to know the internal dict key names and allows
the accessor to raise a meaningful error for unknown fields. The
implementation simply calls `unify(value, result_dict[field], trail)`:

```python
def _result_get(this_generator, parent, result, field, value, trail):
    r = deref(result)
    f = deref(field)
    try:
        v = r[f]
    except (KeyError, TypeError) as e:
        raise LogicException(f"ResultGet: unknown field {f!r}") from e
    if unify(value, v, trail):
        yield (parent, None)
    yield (parent, DONE)
```

Callers may also use the `++()` escape directly for one-off field access:
`X is ++R['x']`.

---

## Proposed Groupings / Pipelines Summary

The following natural pipelines exist across modules and should be
documented as examples in each module's implementation:

| Name | Steps |
|------|-------|
| **Curve fitting** | `OptimizeCurveFit` → inspect `popt`, `pcov` |
| **ODE integration** | `IntegrateSolveIvp` → `IntegrateResultGet(t)` + `(y)` |
| **Spectral analysis** | `FFTRfft` → process → `FFTIrfft` |
| **Filter-then-apply** | `SignalButter(OUTPUT='sos')` → `SignalSosfiltfilt` |
| **Spline interpolation** | `MakeSpline` → `EvalSpline` → `SplineIntegral` → `Free` |
| **Hierarchical clustering** | `ClusterLinkage` → `ClusterFcluster` |
| **k-means** | `ClusterWhiten` → `ClusterKmeans2` → `ClusterVq` |
| **LP / MIP** | `OptimizeLinearConstraint` + `OptimizeBounds` → `OptimizeMilp` |
| **KD-tree nearest-neighbour** | `SpatialMakeKdtree` → `SpatialKdtreeQuery` |
| **LU re-use** | `LinalgLuFactor` → `LinalgLuSolve` (multiple RHS) |
| **Distribution fitting** | `StatsNormFit(DATA=)` → `StatsNormCdf` / `StatsNormPpf` |
| **Statistical test battery** | `StatsNormaltest` → decide → `StatsTtestInd` or `StatsMannwhitneyu` |
