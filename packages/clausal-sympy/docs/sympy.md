# Symbolic Math (`sympy`)

The `sympy` standard library module provides symbolic mathematics predicates backed by [SymPy](https://www.sympy.org/). It accepts **native Clausal Prolog terms** directly — logic variables and arithmetic operators are converted to SymPy expressions automatically.

```seam
-import_from(sympy, [diff, solve, simplify, sin, cos, inf])

test("diff sin") <- (
    diff(sin(X), X, R),
    sym_equal(R, cos(X))
)

test("solve quadratic") <- (
    solve(X**2 - 4, X, S),
    S == 2
)
```

The implementation lives in `clausal/modules/sympy.py`.

---

## Import

```seam
-import_from(sympy, [simplify, expand, factor, solve, diff, integrate,
                             sin, cos, exp, log, sqrt, inf, pi])
```

Or via [module import](import.md):

```seam
-import_module(sympy)
# then use sympy.diff(...), sympy.sin(...), etc.
```

---

## How it works

### Term conversion

Clausal Prolog [arithmetic](arithmetic.md) terms (`X**2 + 3*X + 1`) are trees of `Add`, `Mult`, `Pow` nodes containing logic variables (`Var`). The module converts these to SymPy expression trees automatically:

| Clausal Prolog | SymPy |
|---|---|
| `X` (unbound Var) | `Symbol('x')` |
| `X**2 + 1` | `Symbol('x')**2 + 1` |
| `sin(X)` | `sympy.sin(Symbol('x'))` |
| `3` (int) | `Integer(3)` |

Variables are auto-named alphabetically in discovery order: first Var → `x`, second → `y`, third → `z`, then `a`, `b`, `c`, ...

when the same Var appears in multiple arguments to a predicate, it maps to the same Symbol.

### Symbolic equality: `sym_equal/2`

Predicate results are SymPy expressions. Compare one with an expected
expression with `sym_equal/2`:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:symbolic_equality"
```

This handles term reordering (SymPy may internally reorder `x + 1` to `1 + x`) and alpha-equivalence (different variable names between the result and the expected value).

`==` is arithmetic comparison and does not compare symbolic expressions: `R == 3*X**2` with `R` bound to a SymPy result raises `domain_error(clpz_expression, ...)`. Numeric results (integers, floats) are collapsed to plain Python values, so `simplify(X - X, R), R == 0` still works with `==`.

### Chaining

Results from one predicate can be fed directly into another:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:chaining"
```

`sym_equal/2` also compares through chains:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:chaining_ex2"
```

### Quantities (units)

A [quantity](https://github.com/neurosymbolica/clausal-prolog/blob/main/docs/units.md)
may appear anywhere in an expression. It goes to SymPy as its exact
magnitude, in SI base units, times one dimension symbol per base unit
(`kilogram`, `metre`, `second`, `kelvin`, ...); a `Decimal` or `Fraction`
magnitude stays an exact `Rational`. The dimension symbols are constants,
never variables: `diff/2`, `integrate/2`, `degree/2`, `free_vars/2` and
`sym_equal/2` do not see them. They print as `(kelvin)`, the way a quantity
prints its unit, so they cannot be confused with an atom `kelvin`.

Dimensions are judged by Clausal's units system, as everywhere else, with
`Quantity` arithmetic: on the Clausal term before SymPy sees it (SymPy would
fold `5(pascal) - 5(pascal)` to a dimensionless 0), and again on every result. A plain
number is dimensionless, as in the engine (`0 + 3(kelvin)` is a mismatch); a
variable's dimension is unknown, but two terms with the same powers of the
same variables must agree (`X * 1(kelvin) + X * 1(pascal)` is refused), and a sum such
as `X - 3(kelvin)` tells `solve` that X is a temperature, so its root `0` comes
back as `0(kelvin)`.

What comes back:

- a ground result with a rational magnitude is a quantity with an exact
  magnitude; units that cancel give a plain number; a zero keeps the
  dimension of the input (`simplify(3(kelvin) - 3(kelvin))` is `0(kelvin)`);
- a ground result with an irrational magnitude (`sqrt(2)`, `20/log(3)`, a
  `LambertW` root) is a FLOAT quantity, which compares, `has_units/2` and
  `strip_units/2` like any other (operator ruling 2026-11-04). The exact
  form is available behind the switch
  `clausal.modules.py._sympy_units.EXACT_IRRATIONAL_RESULTS`: set to `True`,
  such a result is the Clausal arithmetic term `Magnitude * 1 (unit)`, e.g.
  `2**(1/2) * 1 (metre)`, when the engine can evaluate every function in it
  (`sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log`, `abs`,
  `ceiling`, `floor`, `pi`, `e`); evaluate it (`eval_(R, V)`, `V is R`)
  before comparing or checking its units, and a further sympy call reads it
  back exactly;
- a result that still holds a variable stays symbolic, dimension symbols
  included;
- `solve/3`, `solve_all/3` and `roots/3` of an equation that holds a
  quantity follow one rule:
  - the answers are its real GROUND roots, in increasing order, each once
    (`roots/3` adds up the multiplicities of roots that coincide). A root
    with another variable in it cannot be classified and is kept as SymPy
    gives it, after the ground ones (`X**2 + Y**2 * 1(metre**2)` answers
    `+-I*y*(metre)`);
  - a root SymPy gives exactly and knows is real is kept as it is, without
    any numeric check: it is correct by construction (roots 1e-30, 1 and
    1e30 metre all survive, and two exact roots are merged only if equal);
  - any other root (a float coefficient, a cubic's real roots written with
    complex radicals, a `LambertW` branch) is evaluated to 50 significant
    digits and polished by Newton's method at 50 digits on the equation in
    SI magnitudes (at most 20 steps, stopping when a step stops
    shrinking). A root is kept, as a float quantity of its real part, only if its
    imaginary part is negligible relative to its size, and if substituting
    it back leaves a residual negligible relative to the equation's own
    terms there (|sum of the terms| <= tolerance * sum of |each term|).
    The tolerance follows the input's precision: 1e-12 when a float is in
    the equation, 1e-25 when every number is exact. Neither test depends
    on the scale of a root or a coefficient. Two such roots closer than the
    same relative tolerance are one root;
  - no real root means no answer: `solve/3` fails, `solve_all/3` gives
    `[]`, `roots/3` fails (`X**2 + 4(metre**2)`);
  - when SymPy gives up on a POLYNOMIAL (it answers `[]` for some quintics,
    or `roots` finds fewer roots than the degree), all its roots are found
    numerically (50 digits) and the rule above applies; only if that fails
    too is it `error(system_error(no_symbolic_solution), _)`. SymPy unable
    to solve any other equation (`X - cos(X / 1(kelvin)) * 1(kelvin)`) is
    that error as well, never a partial list. `roots/3` of an equation that
    is not a polynomial is `type_error(polynomial, Equation)`;
  - an equation without quantities is answered as SymPy gives it, complex
    roots included;
  - a POLYNOMIAL WITH A FLOAT COEFFICIENT is never given to SymPy's
    `solve` (in double precision a small root beside large ones loses its
    digits, a repeated root splits into a complex pair, and degree 20 takes
    minutes). Each float is read as the decimal its shortest repr shows
    (`1.1` is 11/10), the polynomial is split exactly into square-free
    factors, and each factor's roots are found at 50 digits; the real ones
    come back as floats, a repeated root once with its multiplicity
    (`(X - 1.1(metre))**2 * (X - 3(metre))` gives 1.1 and 3.0 metres;
    `roots/3` gives multiplicities 2 and 1; `(X - 1.1(metre))**10` and
    `(X - 1(metre))**10` give 1.1 and 1.0 metres). Only if that fails are
    all its roots found at 50 digits and Newton-polished. A degree-20
    polynomial takes well under a second. An ill-conditioned one (roots
    0.5, 1, ..., 15 metres, degree 30) has its larger roots moved off the
    real axis by the rounding of its coefficients, so fewer real roots come
    back: the float input itself says so. Two distinct roots closer than a double can
    tell apart come back as two equal floats;
  - mpmath not converging at all is `no_symbolic_solution`.

`^` follows SymPy, not ISO: `2^-1` is `1/2` (ISO's `^` is a type error for
a negative integer exponent) and `X^2` is `X**2`, so a unit-free
`solve_all(X^2 - 4, X, R)` now gives `[-2, 2]` (it used to be a raw
`NotImplementedError`). Without quantities, `0^-1` and `atan2(0, 0)` come
back as SymPy's values `zoo` and `nan`; with a quantity such a value is
`evaluation_error(undefined)`.
- a VALUE that is complex, infinite or NaN (`sqrt(-4(metre**2))`) is
  `evaluation_error(undefined)`, as is a quantity whose magnitude is
  infinite or NaN on the way in;
- `gcd/3`, `lcm/3` and `sym_equal/2` refuse two quantities of different
  dimensions with `units_mismatch`, and `subs/3` refuses a quantity as the
  thing to substitute for (`type_error(variable, Q)`).

```seam
--8<-- "tests/fixtures/sympy_units.seam:heat_exchanger_quantities"
```

Solving backwards gives a root with its dimension, a mass flow here:

```seam
--8<-- "tests/fixtures/sympy_units.seam:solve_for_a_quantity"
```

A mismatch is the units system's own error, `error(system_error(units_mismatch), _)`:

```seam
--8<-- "tests/fixtures/sympy_units.seam:dimension_mismatch"
```

Every function is in one class. `abs`, `max`, `min` and `hypot` keep
their arguments' one dimension (`max(3(kelvin), 5(pascal))` is refused).
`atan2` takes two values of one dimension and gives an angle (a number).
`sign` takes any dimension and gives a number. `sqrt`, `cbrt` and `^` are
powers (`cbrt` of a volume is a length; `cbrt` is SymPy's principal root, so
`cbrt(-8(metre**3))` is complex and refused, not `-2(metre)`). A known
function with the wrong number of arguments (`abs(3(kelvin), 4(kelvin))`)
is `type_error(evaluable, abs/2)`, as in the engine. Every other function
needs dimensionless arguments and gives a dimensionless value:
`log`, `exp`, the trigonometric functions, `floor`, `ceiling`, `gamma`,
`factorial`, and any function the wrapper does not know (`log10`, `sinh`,
`f`), whose dimension it cannot judge, so `log10(100(kelvin))` and
`f(3(kelvin))` are refused with `units_mismatch`. A ratio of two
temperature differences is dimensionless, and the log mean temperature
difference comes back as a float quantity in kelvin:

```seam
--8<-- "tests/fixtures/sympy_units.seam:log_mean_temperature_difference"
```

`abs` keeps its argument's dimension and `sqrt` is a power: `sqrt` of an area
is a length, `sqrt` of a temperature is refused (a dimension exponent must be
an integer). A temperature is in kelvin and only differences are
meaningful to the units system (there is no Celsius offset scale): enter a
difference in millidegrees Celsius as kelvin over 1000, `12345(kelvin) / 1000`,
which stays exact: 2469/200 times 1(kelvin).

Solving the log mean temperature difference backwards, SymPy offers 17
candidate roots; exactly one is real and satisfies the equation:

```seam
--8<-- "tests/fixtures/sympy_units.seam:log_mean_temperature_difference_inverse"
```

**Limitations.** There is no time limit on a SymPy call (a todo; the
sandbox budget should allow for it meanwhile). Measured on review of
45371c2d: the log mean temperature difference solved backwards (from
10(kelvin) to 18(kelvin)) takes 8.7 s; duty = U * A * LMTD solved for the
hot-end difference, 19.1 s; the same inverse with float inputs, 94.5 s; the
inverse from 12.34(kelvin) and 18.20(kelvin), and the Colebrook friction
equation, more than 120 s.

A zero that SymPy produces AFTER the input has been
checked carries no dimension, so it comes back as a plain `0`: `subs/3`
putting `0` (or `0(kilogram/second)`) into `M * 4186(joule/kilogram/kelvin)
* 1(kelvin)`, `limit(X * 1(kelvin) - 2(kelvin), X, 2)`, a root that is zero
when the equation has a second unknown, and a zero polynomial coefficient.
For the same reason a zero derivative `diff(3(kelvin), X, R)` is a plain
`0`: nothing says what X is, so "kelvin per X" has no known dimension
(when the expression does say, as in `X * 1(metre) - X * 1(metre) +
3(kelvin) * 1(metre)`, the zero derivative is `0(metre)`).

---

## Predicates

### Core calculus

#### simplify/2

`simplify(Expr, Result)` — simplify an expression:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:simplify_2"
```

#### expand/2

`expand(Expr, Result)` — algebraic expansion:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:expand_2"
```

#### factor/2

`factor(Expr, Result)` — factorization:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:factor_2"
```

#### solve/3

`solve(Equation, Var, Solution)` — solve equation = 0 for Var. **Nondeterministic** — yields one solution per answer on backtracking:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:solve_3"
```

#### solve_all/3

`solve_all(Equation, Var, Solutions)` — deterministic, unifies Solutions with a list:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:solve_all_3"
```

#### diff/2, diff/3

`diff(Expr, Result)` — differentiate w.r.t. the single free variable.
`diff(Expr, Var, Result)` — differentiate w.r.t. specified variable:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:diff_2_3"
```

#### integrate/2, integrate/3

`integrate(Expr, Result)` — indefinite integral w.r.t. the single free variable.
`integrate(Expr, Var, Result)` — w.r.t. specified variable:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:integrate_2_3"
```

#### limit/4

`limit(Expr, Var, Point, Result)` — limit as Var approaches Point:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:limit_4"
```

#### series/4, series/5

`series(Expr, Var, N, Result)` — Taylor series around Var=0 to N terms.
`series(Expr, Var, Point, N, Result)` — around a specified point:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:series_4_5"
```

### Algebra extras

#### collect/3

`collect(Expr, Var, Result)` — collect terms by powers of Var:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:collect_3"
```

#### cancel/2

`cancel(Expr, Result)` — cancel common factors in a rational expression:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:cancel_2"
```

#### apart/2, apart/3

`apart(Expr, Result)` — partial fraction decomposition:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:apart_2_3"
```

#### together/2

`together(Expr, Result)` — combine fractions over a common denominator:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:together_2"
```

#### degree/2, degree/3

`degree(Expr, Result)` / `degree(Expr, Var, Result)` — polynomial degree:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:degree_2_3"
```

#### coeffs/3

`coeffs(Expr, Var, Result)` — polynomial coefficients (highest degree first):

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:coeffs_3"
```

#### roots/3

`roots(Equation, Var, Pair)` — **nondeterministic**, yields `(root, multiplicity)` tuples:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:roots_3"
```

### Trigonometry

#### trig_simp/2

`trig_simp(Expr, Result)` — simplify trigonometric expressions:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:trig_simp_2"
```

#### expand_trig/2

`expand_trig(Expr, Result)` — expand trig identities:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:expand_trig_2"
```

### Number theory

#### is_prime/1

`is_prime(N)` — succeeds if N is prime:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:is_prime_1"
```

#### next_prime/2

`next_prime(N, Result)` — smallest prime greater than N:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:next_prime_2"
```

#### factor_int/2

`factor_int(N, Result)` — prime factorization as `{prime: exponent}` dict:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:factor_int_2"
```

#### divisors/2

`divisors(N, Result)` — sorted list of positive divisors:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:divisors_2"
```

#### gcd/3, lcm/3

`gcd(A, B, Result)` / `lcm(A, B, Result)` — symbolic GCD/LCM (works on both integers and polynomials):

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:gcd_lcm_3"
```

### Special functions

#### sum_/5

`sum_(Expr, Var, Low, High, Result)` — symbolic summation:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sum_5"
```

#### product/5

`product(Expr, Var, Low, High, Result)` — symbolic product:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:product_5"
```

#### binomial/3

`binomial(N, K, Result)` — binomial coefficient:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:binomial_3"
```

### Printing

The printing predicates (and `sym_str/2`) answer a **string**, `"x + 1"`
(the term `('$chars', 'x + 1')`), not an atom: a printed representation is
free-form text. Compare with a string (`S == "42"`); the atom `'42'` is a
different term. The `++` escape is unchanged -- `S is ++str(E)` still binds
the atom.

#### latex/2

`latex(Expr, String)` — convert expression to LaTeX:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:latex_2"
```

#### pretty/2

`pretty(Expr, String)` — Unicode pretty-print:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:pretty_2"
```

#### math_ml/2

`math_ml(Expr, String)` — convert to MathML (content markup, `<cn>42</cn>`).

### Substitution and inspection

#### subs/3

`subs(Expr, Bindings, Result)` — substitute values. Bindings is a dict or list of pairs:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:subs_3"
```

Note: binding dicts with logic variable keys must be wrapped in `++()` so the Vars are dereferenced.

#### free_vars/2

`free_vars(Expr, Names)` — sorted list of the free symbols' names, as atoms (`[x, y]`):

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:free_vars_2"
```

### Display and comparison

#### sym_str/2

`sym_str(Expr, String)` — convert expression to a readable string via SymPy:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_str_2"
```

#### sym_equal/2

`sym_equal(A, B)` — symbolic equality (`==` is arithmetic and does not compare symbolic expressions):

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_equal_2"
```

### Conversion

#### sym/2

`sym(Name, Symbol)` — create a named SymPy Symbol. Rarely needed since predicates auto-convert Vars, but useful when you want a specific display name:

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:sym_2"
```

#### sympy_term/2

`sympy_term(Sympy, Term)` — explicit bidirectional conversion between a SymPy expression and a Clausal Prolog term. Rarely needed (predicates auto-convert), but useful for inspecting or constructing a raw SymPy expression. Mode-switches like ISO `atom_codes/2`:

- `Sympy` already a SymPy expression → `Term` is unified with the equivalent Clausal Prolog term.
- `Sympy` unbound, `Term` bound to anything other than a bare unbound variable (a number, an atom, a term that may itself contain variables, e.g. `X+1`) → `Sympy` is unified with the equivalent SymPy expression.
- Both unbound → `instantiation_error`.
- `Sympy` bound to something that is neither a SymPy expression nor unbound → `type_error(sympy_expression, Sympy)`.
- A `Term` with no SymPy counterpart (TO-SYMPY direction) → `type_error(sympy_expression, Term)`. This includes a list, a dict, a compound whose functor is not an atom, and a cyclic term (`X = f(X)`); every other predicate fails on these instead. Strings are never parsed as Python: an atom or string names a symbol, nothing more. A SymPy expression with no Clausal Prolog term counterpart (FROM-SYMPY direction) → `type_error(clausal_term, Sympy)` (this one is believed unreachable today: the converter always has a fallback -- a SymPy object with no term form comes back as its printed form, a **string** such as `"Eq(a, 1)"` -- but the predicate does not rely on that staying true).

**Not a true bijection.** SymPy canonicalises on construction: `X+X` becomes `2*X`, `X*1` becomes `X`, and term order is not preserved. So `Term → Sympy → Term` returns an *equivalent* term, not necessarily the *same* one:

```
sympy_term(S, X+X), sympy_term(S, T)   % T = 2*X, not X+X
```

Variables DO round-trip exactly, even across two separate calls with their own fresh conversion state: `sympy_term(S, X+1), sympy_term(S, T)` gives `T = X+1` with the *same* `X`. Two distinct variables never collapse onto one SymPy symbol, even if both happen to get the same auto-assigned display name.

(`ToSympy/2` and `FromSympy/2` were merged into this one relation, RULED 2026-10-02 — neither old name survives, and there is no alias.)

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

```seam
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

```seam
--8<-- "tests/fixtures/docs/sympy_sigs.txt:constants_usage"
```

---

## Naming conventions

Function and constant names follow SymPy's conventions where possible:

- **Math functions**: lowercase (`sin`, `cos`, `exp`, `log`, `sqrt`, `factorial`) — matches SymPy exactly
- **`abs_`**: capitalized — matches SymPy (they capitalized it because `abs` is a Python builtin)
- **`inf`**: instead of SymPy's `oo` — readability
- **`e`**: instead of SymPy's `E` — `E` is ALLCAPS so seam source treats it as a logic variable
- **Predicates**: capitalized (`simplify`, `diff`, `solve`) — these are Python
  objects reached through the `-import_from(sympy, [...])` list, not Clausal Prolog
  predicates; a name that arrives through an import list keeps its Python
  spelling. Clausal Prolog's own predicates are lowercase.

---

??? info "Test coverage"

    - `packages/clausal-sympy/tests/test_sympy_module.py` — 50 Python tests (conversion layer, predicates via API)
    - `packages/clausal-sympy/tests/fixtures/sympy_basic.seam` — 32 tests (core calculus, solve, series, chaining, multivariate)
    - `packages/clausal-sympy/tests/fixtures/sympy_algebra.seam` — 14 tests (collect, cancel, apart, together, degree, coeffs, roots)
    - `packages/clausal-sympy/tests/fixtures/sympy_trig.seam` — 5 tests (trigsimp, expand_trig, exp/log)
    - `packages/clausal-sympy/tests/fixtures/sympy_printing.seam` — 5 tests (latex, pretty)
    - `packages/clausal-sympy/tests/fixtures/sympy_numtheory.seam` — 18 tests (isprime, nextprime, factorint, divisors, gcd, lcm)
    - `packages/clausal-sympy/tests/fixtures/sympy_special.seam` — 8 tests (summation, product, binomial)

    Total: **132 tests**.

---

*See also: [Arithmetic](arithmetic.md) — Clausal Prolog's built-in arithmetic · [Python Interop](python_integration.md) — `++()` escape for additional SymPy operations.*
