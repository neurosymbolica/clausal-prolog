# Symbolic Math (`sympy_module`)

The `sympy_module` standard library module provides symbolic mathematics predicates backed by [SymPy](https://www.sympy.org/). It accepts **native Clausal terms** directly — logic variables and arithmetic operators are converted to SymPy expressions automatically.

```clausal
-import_from(sympy_module, [Diff, Solve, Simplify, sin, cos, inf])

Test("diff sin") <- (
    Diff(sin(X), X, R),
    R == cos(X)
)

Test("solve quadratic") <- (
    Solve(X**2 - 4, X, S),
    S == 2
)
```

The implementation lives in `clausal/modules/sympy_module.py`.

---

## Import

```clausal
-import_from(sympy_module, [Simplify, Expand, Factor, Solve, Diff, Integrate,
                             sin, cos, exp, log, sqrt, inf, pi])
```

Or via [module import](import.md):

```clausal
-import_module(sympy_module)
# then use sympy_module.Diff(...), sympy_module.sin(...), etc.
```

---

## How it works

### Term conversion

Clausal [arithmetic](arithmetic.md) terms (`X**2 + 3*X + 1`) are trees of `Add`, `Mult`, `Pow` nodes containing logic variables (`Var`). The module converts these to SymPy expression trees automatically:

| Clausal | SymPy |
|---|---|
| `X` (unbound Var) | `Symbol('x')` |
| `X**2 + 1` | `Symbol('x')**2 + 1` |
| `sin(X)` | `sympy.sin(Symbol('x'))` |
| `3` (int) | `Integer(3)` |

Variables are auto-named alphabetically in discovery order: first Var → `x`, second → `y`, third → `z`, then `a`, `b`, `c`, ...

when the same Var appears in multiple arguments to a predicate, it maps to the same Symbol.

### Symbolic equality via `==`

Predicate results are wrapped in `SymExpr`, which overrides `__eq__` to do symbolic comparison. This means Clausal's native `==` works for comparing symbolic results:

```clausal
# skip
Diff(X**3, X, R),
R == 3*X**2             # symbolic comparison, not structural
```

This handles term reordering (SymPy may internally reorder `x + 1` to `1 + x`) and alpha-equivalence (different variable names between the result and the expected value).

Numeric results (integers, floats) are collapsed to plain Python values, so `Simplify(X - X, R), R == 0` works with ordinary equality.

### Chaining

Results from one predicate can be fed directly into another:

```clausal
# skip
Diff(X**4, X, D),
Integrate(D, X, I),
I == X**4
```

The `==` operator also preserves symbolic equality through chains:

```clausal
# skip
Diff(X**3, X, D),
R == D + 1,
R == 3*X**2 + 1
```

---

## Predicates

### Core calculus

#### Simplify/2

`Simplify(Expr, Result)` — simplify an expression:

```clausal
# skip
Simplify(X**2 + 2*X + 1 - (X + 1)**2, 0)
Simplify((X**2 - 1) / (X - 1), R),  R == X + 1
```

#### Expand/2

`Expand(Expr, Result)` — algebraic expansion:

```clausal
# skip
Expand((X + 1)**2, R),  R == X**2 + 2*X + 1
Expand((X + Y)**2, R),  R == X**2 + 2*X*Y + Y**2
```

#### Factor/2

`Factor(Expr, Result)` — factorization:

```clausal
# skip
Factor(X**2 - 1, R),      R == (X - 1) * (X + 1)
Factor(X**2 + 5*X + 6, R), R == (X + 2) * (X + 3)
```

#### Solve/3

`Solve(Equation, Var, Solution)` — solve equation = 0 for Var. **Nondeterministic** — yields one solution per answer on backtracking:

```clausal
# skip
Solve(2*X - 6, X, S),  S == 3
Solve(X**2 - 4, X, S), S == 2     # first solution
Solve(X**2 - 4, X, S), S == -2    # second solution (on backtracking)
```

#### SolveAll/3

`SolveAll(Equation, Var, Solutions)` — deterministic, unifies Solutions with a list:

```clausal
# skip
SolveAll(X**2 - 9, X, SOLS),
S is ++sorted(SOLS),
S == [-3, 3]
```

#### Diff/2, Diff/3

`Diff(Expr, Result)` — differentiate w.r.t. the single free variable.
`Diff(Expr, Var, Result)` — differentiate w.r.t. specified variable:

```clausal
# skip
Diff(X**3, X, R),          R == 3*X**2
Diff(sin(X), X, R),        R == cos(X)
Diff(X*Y + X**2, X, R),    R == Y + 2*X    # partial derivative
```

#### Integrate/2, Integrate/3

`Integrate(Expr, Result)` — indefinite integral w.r.t. the single free variable.
`Integrate(Expr, Var, Result)` — w.r.t. specified variable:

```clausal
# skip
Integrate(X**2, X, R),     R == X**3 / 3
Integrate(cos(X), X, R),   R == sin(X)
```

#### Limit/4

`Limit(Expr, Var, Point, Result)` — limit as Var approaches Point:

```clausal
# skip
Limit(X + 1, X, 0, R),     R == 1
Limit(1/X, X, inf, R),     R == 0
Limit(sin(X)/X, X, 0, R),  R == 1
```

#### Series/4, Series/5

`Series(Expr, Var, N, Result)` — Taylor series around Var=0 to N terms.
`Series(Expr, Var, Point, N, Result)` — around a specified point:

```clausal
# skip
Series(1/(1-X), X, 4, R),
R == 1 + X + X**2 + X**3
```

### Algebra extras

#### Collect/3

`Collect(Expr, Var, Result)` — collect terms by powers of Var:

```clausal
# skip
Collect(X**2 + 2*X + X*Y, X, R),
R == X**2 + X*(Y + 2)
```

#### Cancel/2

`Cancel(Expr, Result)` — cancel common factors in a rational expression:

```clausal
# skip
Cancel((X**2 - 1) / (X - 1), R),  R == X + 1
```

#### Apart/2, Apart/3

`Apart(Expr, Result)` — partial fraction decomposition:

```clausal
# skip
Apart(1 / (X**2 - 1), R),
R == 1/(2*(X - 1)) - 1/(2*(X + 1))
```

#### Together/2

`Together(Expr, Result)` — combine fractions over a common denominator:

```clausal
# skip
Together(1/X + 1/Y, R),  R == (X + Y) / (X * Y)
```

#### Degree/2, Degree/3

`Degree(Expr, Result)` / `Degree(Expr, Var, Result)` — polynomial degree:

```clausal
# skip
Degree(X**3 + 2*X + 1, X, D),  D == 3
```

#### Coeffs/3

`Coeffs(Expr, Var, Result)` — polynomial coefficients (highest degree first):

```clausal
# skip
Coeffs(2*X**3 - X + 7, X, C),  C == [2, 0, -1, 7]
```

#### Roots/3

`Roots(Equation, Var, Pair)` — **nondeterministic**, yields `(root, multiplicity)` tuples:

```clausal
# skip
Roots(X**2 - 2*X + 1, X, PAIR),
ROOT is ++PAIR[0],
MULT is ++PAIR[1],
ROOT == 1,
MULT == 2
```

### Trigonometry

#### TrigSimp/2

`TrigSimp(Expr, Result)` — simplify trigonometric expressions:

```clausal
# skip
TrigSimp(sin(X)**2 + cos(X)**2, R),  R == 1
TrigSimp(2 * sin(X) * cos(X), R),    R == sin(2*X)
```

#### ExpandTrig/2

`ExpandTrig(Expr, Result)` — expand trig identities:

```clausal
# skip
ExpandTrig(sin(X + Y), R),
R == sin(X)*cos(Y) + sin(Y)*cos(X)
```

### Number theory

#### IsPrime/1

`IsPrime(N)` — succeeds if N is prime:

```clausal
# skip
IsPrime(7)              # succeeds
not IsPrime(4)          # succeeds
```

#### NextPrime/2

`NextPrime(N, Result)` — smallest prime greater than N:

```clausal
# skip
NextPrime(7, P),  P == 11
```

#### FactorInt/2

`FactorInt(N, Result)` — prime factorization as `{prime: exponent}` dict:

```clausal
# skip
FactorInt(360, F),  F is ++{2: 3, 3: 2, 5: 1}
```

#### Divisors/2

`Divisors(N, Result)` — sorted list of positive divisors:

```clausal
# skip
Divisors(12, D),  D == [1, 2, 3, 4, 6, 12]
```

#### gcd/3, lcm/3

`gcd(A, B, Result)` / `lcm(A, B, Result)` — symbolic GCD/LCM (works on both integers and polynomials):

```clausal
# skip
gcd(12, 8, R),          R == 4
gcd(X**2 - 1, X - 1, R), R == X - 1
lcm(4, 6, R),            R == 12
```

### Special functions

#### sum_/5

`sum_(Expr, Var, Low, High, Result)` — symbolic summation:

```clausal
# skip
sum_(I, I, 1, N, R),      R == N*(N + 1)/2
sum_(I**2, I, 1, 5, R),   R == 55
```

#### Product/5

`Product(Expr, Var, Low, High, Result)` — symbolic product:

```clausal
# skip
Product(I, I, 1, 5, R),  R == 120
```

#### Binomial/3

`Binomial(N, K, Result)` — binomial coefficient:

```clausal
# skip
Binomial(5, 2, R),   R == 10
Binomial(N, 2, R),   R == N*(N - 1)/2
```

### Printing

#### Latex/2

`Latex(Expr, String)` — convert expression to LaTeX:

```clausal
# skip
Latex(X**2 + 1, S),  ++("x^{2}" in S)
```

#### Pretty/2

`Pretty(Expr, String)` — Unicode pretty-print:

```clausal
# skip
Pretty(X**2, S),  ++("2" in S)
```

#### MathML/2

`MathML(Expr, String)` — convert to MathML.

### Substitution and inspection

#### Subs/3

`Subs(Expr, Bindings, Result)` — substitute values. Bindings is a dict or list of pairs:

```clausal
# skip
Subs(X**2 + 1, ++{X: 3}, R),  R == 10
```

Note: binding dicts with logic variable keys must be wrapped in `++()` so the Vars are dereferenced.

#### FreeVars/2

`FreeVars(Expr, Names)` — sorted list of free symbol name strings:

```clausal
# skip
FreeVars(42, V),  V == []
```

### Display and comparison

#### SymStr/2

`SymStr(Expr, String)` — convert expression to a readable string via SymPy:

```clausal
# skip
SymStr(42, S),  S == "42"
```

#### SymEqual/2

`SymEqual(A, B)` — explicit symbolic equality (usually `==` suffices, but `SymEqual` is available for cases where both sides are raw Clausal terms):

```clausal
# skip
SymEqual(X**2 + 1, 1 + X**2)
SymEqual((X + 1)**2 - X**2, 2*X + 1)
```

### Conversion

#### Sym/2

`Sym(Name, Symbol)` — create a named SymPy Symbol. Rarely needed since predicates auto-convert Vars, but useful when you want a specific display name:

```clausal
# skip
Sym("x", X),
EXPR is ++(X**2 + 1),
S is ++str(EXPR),
S == "x**2 + 1"
```

#### ToSympy/2, FromSympy/2

Explicit conversion between Clausal terms and SymPy expressions. Rarely needed.

---

## Math functions

Importable callables that produce `Compound` terms. These are converted to SymPy functions by the predicates:

| Function | SymPy equivalent |
|---|---|
| `sin`, `cos`, `tan` | `sympy.sin`, `sympy.cos`, `sympy.tan` |
| `asin`, `acos`, `atan` | `sympy.asin`, `sympy.acos`, `sympy.atan` |
| `exp`, `log`, `ln` | `sympy.exp`, `sympy.log`, `sympy.log` |
| `sqrt` | `sympy.sqrt` |
| `factorial` | `sympy.factorial` |
| `abs_` | `sympy.abs_` |

Usage:

```clausal
# skip
-import_from(sympy_module, [Diff, sin, cos, exp, log, sqrt])

Diff(sin(X), X, R),  R == cos(X)
Simplify(exp(log(X)), R),  R == X
```

---

## Constants

| Constant | Value | Note |
|---|---|---|
| `inf` | `sympy.oo` (infinity) | SymPy uses `oo`; `inf` is more readable |
| `pi` | `sympy.pi` | |
| `e` | `sympy.E` (Euler's number) | Lowercase to avoid ALLCAPS logic variable conflict |

Usage:

```clausal
# skip
-import_from(sympy_module, [Limit, inf, pi])

Limit(1/X, X, inf, R),  R == 0
```

---

## Naming conventions

Function and constant names follow SymPy's conventions where possible:

- **Math functions**: lowercase (`sin`, `cos`, `exp`, `log`, `sqrt`, `factorial`) — matches SymPy exactly
- **`abs_`**: capitalized — matches SymPy (they capitalized it because `abs` is a Python builtin)
- **`inf`**: instead of SymPy's `oo` — readability
- **`e`**: instead of SymPy's `E` — `E` is ALLCAPS so Clausal treats it as a logic variable
- **Predicates**: capitalized (`Simplify`, `Diff`, `Solve`) — Clausal convention

---

??? info "Test coverage"

    - `tests/test_sympy_module.py` — 50 Python tests (conversion layer, predicates via API)
    - `tests/fixtures/sympy_basic.clausal` — 32 tests (core calculus, solve, series, chaining, multivariate)
    - `tests/fixtures/sympy_algebra.clausal` — 14 tests (collect, cancel, apart, together, degree, coeffs, roots)
    - `tests/fixtures/sympy_trig.clausal` — 5 tests (trigsimp, expand_trig, exp/log)
    - `tests/fixtures/sympy_printing.clausal` — 5 tests (latex, pretty)
    - `tests/fixtures/sympy_numtheory.clausal` — 18 tests (isprime, nextprime, factorint, divisors, gcd, lcm)
    - `tests/fixtures/sympy_special.clausal` — 8 tests (summation, product, binomial)

    Total: **132 tests**.

---

*See also: [Arithmetic](arithmetic.md) — Clausal's built-in arithmetic · [Python Interop](python_integration.md) — `++()` escape for additional SymPy operations.*
