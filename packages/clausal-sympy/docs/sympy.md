# Symbolic Math (`sympy`)

The `sympy` standard library module provides symbolic mathematics predicates backed by [SymPy](https://www.sympy.org/). It accepts **native Clausal terms** directly — logic variables and arithmetic operators are converted to SymPy expressions automatically.

```clausal
-import_from(sympy, [diff, solve, simplify, sin, cos, inf])

test("diff sin") <- (
    diff(sin(X), X, R),
    R == cos(X)
)

test("solve quadratic") <- (
    solve(X**2 - 4, X, S),
    S == 2
)
```

The implementation lives in `clausal/modules/sympy.py`.

---

## Import

```clausal
-import_from(sympy, [simplify, expand, factor, solve, diff, integrate,
                             sin, cos, exp, log, sqrt, inf, pi])
```

Or via [module import](import.md):

```clausal
-import_module(sympy)
# then use sympy.diff(...), sympy.sin(...), etc.
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
--8<-- "tests/fixtures/docs/sympy_sigs.txt:symbolic_equality"
```

This handles term reordering (SymPy may internally reorder `x + 1` to `1 + x`) and alpha-equivalence (different variable names between the result and the expected value).

Numeric results (integers, floats) are collapsed to plain Python values, so `simplify(X - X, R), R == 0` works with ordinary equality.

### Chaining

Results from one predicate can be fed directly into another:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:chaining"
```

The `==` operator also preserves symbolic equality through chains:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:chaining_ex2"
```

---

## Predicates

### Core calculus

#### simplify/2

`simplify(Expr, Result)` — simplify an expression:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:simplify_2"
```

#### expand/2

`expand(Expr, Result)` — algebraic expansion:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:expand_2"
```

#### factor/2

`factor(Expr, Result)` — factorization:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:factor_2"
```

#### solve/3

`solve(Equation, Var, Solution)` — solve equation = 0 for Var. **Nondeterministic** — yields one solution per answer on backtracking:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:solve_3"
```

#### solve_all/3

`solve_all(Equation, Var, Solutions)` — deterministic, unifies Solutions with a list:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:solve_all_3"
```

#### diff/2, diff/3

`diff(Expr, Result)` — differentiate w.r.t. the single free variable.
`diff(Expr, Var, Result)` — differentiate w.r.t. specified variable:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:diff_2_3"
```

#### integrate/2, integrate/3

`integrate(Expr, Result)` — indefinite integral w.r.t. the single free variable.
`integrate(Expr, Var, Result)` — w.r.t. specified variable:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:integrate_2_3"
```

#### limit/4

`limit(Expr, Var, Point, Result)` — limit as Var approaches Point:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:limit_4"
```

#### series/4, series/5

`series(Expr, Var, N, Result)` — Taylor series around Var=0 to N terms.
`series(Expr, Var, Point, N, Result)` — around a specified point:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:series_4_5"
```

### Algebra extras

#### collect/3

`collect(Expr, Var, Result)` — collect terms by powers of Var:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:collect_3"
```

#### cancel/2

`cancel(Expr, Result)` — cancel common factors in a rational expression:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:cancel_2"
```

#### apart/2, apart/3

`apart(Expr, Result)` — partial fraction decomposition:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:apart_2_3"
```

#### together/2

`together(Expr, Result)` — combine fractions over a common denominator:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:together_2"
```

#### degree/2, degree/3

`degree(Expr, Result)` / `degree(Expr, Var, Result)` — polynomial degree:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:degree_2_3"
```

#### coeffs/3

`coeffs(Expr, Var, Result)` — polynomial coefficients (highest degree first):

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:coeffs_3"
```

#### roots/3

`roots(Equation, Var, Pair)` — **nondeterministic**, yields `(root, multiplicity)` tuples:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:roots_3"
```

### Trigonometry

#### trig_simp/2

`trig_simp(Expr, Result)` — simplify trigonometric expressions:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:trig_simp_2"
```

#### expand_trig/2

`expand_trig(Expr, Result)` — expand trig identities:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:expand_trig_2"
```

### Number theory

#### is_prime/1

`is_prime(N)` — succeeds if N is prime:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:is_prime_1"
```

#### next_prime/2

`next_prime(N, Result)` — smallest prime greater than N:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:next_prime_2"
```

#### factor_int/2

`factor_int(N, Result)` — prime factorization as `{prime: exponent}` dict:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:factor_int_2"
```

#### divisors/2

`divisors(N, Result)` — sorted list of positive divisors:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:divisors_2"
```

#### gcd/3, lcm/3

`gcd(A, B, Result)` / `lcm(A, B, Result)` — symbolic GCD/LCM (works on both integers and polynomials):

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:gcd_lcm_3"
```

### Special functions

#### sum_/5

`sum_(Expr, Var, Low, High, Result)` — symbolic summation:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sum_5"
```

#### product/5

`product(Expr, Var, Low, High, Result)` — symbolic product:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:product_5"
```

#### binomial/3

`binomial(N, K, Result)` — binomial coefficient:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:binomial_3"
```

### Printing

#### latex/2

`latex(Expr, String)` — convert expression to LaTeX:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:latex_2"
```

#### pretty/2

`pretty(Expr, String)` — Unicode pretty-print:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:pretty_2"
```

#### math_ml/2

`math_ml(Expr, String)` — convert to math_ml.

### Substitution and inspection

#### subs/3

`subs(Expr, Bindings, Result)` — substitute values. Bindings is a dict or list of pairs:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:subs_3"
```

Note: binding dicts with logic variable keys must be wrapped in `++()` so the Vars are dereferenced.

#### free_vars/2

`free_vars(Expr, Names)` — sorted list of free symbol name strings:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:free_vars_2"
```

### Display and comparison

#### sym_str/2

`sym_str(Expr, String)` — convert expression to a readable string via SymPy:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_str_2"
```

#### sym_equal/2

`sym_equal(A, B)` — explicit symbolic equality (usually `==` suffices, but `sym_equal` is available for cases where both sides are raw Clausal terms):

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_equal_2"
```

### Conversion

#### sym/2

`sym(Name, Symbol)` — create a named SymPy Symbol. Rarely needed since predicates auto-convert Vars, but useful when you want a specific display name:

```clausal
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_2"
```

#### ToSympy/2, FromSympy/2

Explicit conversion between Clausal terms and SymPy expressions. Rarely needed.

---

## Math functions

Importable callables that produce compound terms (cells). These are converted to SymPy functions by the predicates:

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
--8<-- "tests/fixtures/docs/sympy_sigs.txt:math_functions_usage"
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
--8<-- "tests/fixtures/docs/sympy_sigs.txt:constants_usage"
```

---

## Naming conventions

Function and constant names follow SymPy's conventions where possible:

- **Math functions**: lowercase (`sin`, `cos`, `exp`, `log`, `sqrt`, `factorial`) — matches SymPy exactly
- **`abs_`**: capitalized — matches SymPy (they capitalized it because `abs` is a Python builtin)
- **`inf`**: instead of SymPy's `oo` — readability
- **`e`**: instead of SymPy's `E` — `E` is ALLCAPS so Clausal treats it as a logic variable
- **Predicates**: capitalized (`simplify`, `diff`, `solve`) — these are Python
  objects reached through the `-import_from(sympy, [...])` list, not Clausal
  predicates; a name that arrives through an import list keeps its Python
  spelling. Clausal's own predicates are lowercase.

---

??? info "Test coverage"

    - `packages/clausal-sympy/tests/test_sympy_module.py` — 50 Python tests (conversion layer, predicates via API)
    - `packages/clausal-sympy/tests/fixtures/sympy_basic.clausal` — 32 tests (core calculus, solve, series, chaining, multivariate)
    - `packages/clausal-sympy/tests/fixtures/sympy_algebra.clausal` — 14 tests (collect, cancel, apart, together, degree, coeffs, roots)
    - `packages/clausal-sympy/tests/fixtures/sympy_trig.clausal` — 5 tests (trigsimp, expand_trig, exp/log)
    - `packages/clausal-sympy/tests/fixtures/sympy_printing.clausal` — 5 tests (latex, pretty)
    - `packages/clausal-sympy/tests/fixtures/sympy_numtheory.clausal` — 18 tests (isprime, nextprime, factorint, divisors, gcd, lcm)
    - `packages/clausal-sympy/tests/fixtures/sympy_special.clausal` — 8 tests (summation, product, binomial)

    Total: **132 tests**.

---

*See also: [Arithmetic](arithmetic.md) — Clausal's built-in arithmetic · [Python Interop](python_integration.md) — `++()` escape for additional SymPy operations.*
