# Arithmetic

Clausal supports Python's arithmetic operators directly in clause bodies, plus
relational arithmetic predicates that work in multiple directions.

---

## Quick Example

```seam
factorial(0, 1),
factorial(N, F) <- (
    N > 0,
    N1 == N - 1,
    factorial(N1, F1),
    F == N * F1
)

test("fact 5") <- factorial(5, 120)
```

---

## Evaluation & Comparison

### The `==` operator

`==` posts an arithmetic constraint ([CLP(ℤ)](constraints.md) or [CLP(ℝ)](clpr.md)) that works in all directions:

```seam
test("eval") <- (X == 3 + 4 * 2, X == 11)
```

Supported operators: `+`, `-`, `*`, `/`, `//` (integer division), `%` (modulo),
`**` (power). The other evaluable functors (`abs()`, `min()`, `max()`,
`round()`, `sqrt()`, ... below) are evaluated when their operands are ground;
the constraint does not propagate through them, so `X == max(Y, 3)` with `Y`
unbound raises `domain_error(clpz_expression, max(_, 3))` (Scryer's clpz posts
`abs`, `min` and `max` as constraints; this engine does not yet).

A **bare** operator keeps Python's meaning in today's syntax (`-7 // 2` is -4,
`2 ** 3` is 8); its **quoted** spelling follows Scryer Prolog (`'//'(-7, 2)` is
-3, `'**'(2, 3)` is 8.0). [Operators](operators.md) has the whole table.

### eval_/2 — eager evaluation

`eval_(EXPR, RESULT)` evaluates `EXPR` immediately and unifies the value with
`RESULT` (Prolog's `is/2`):

```seam
test("eval") <- (eval_(6 * 7, X), X == 42)
```

Prefer `==` for ordinary relational arithmetic — it works in all directions.
`EXPR` is evaluated the way ISO `is/2` evaluates:

- A **variable** is evaluated at runtime, whatever it is bound to — a number,
  or an arithmetic term such as `+(1, 2)` built by `unpack/2` (`=..`) or
  `functor/3`. `unpack(T, ['+', 1, 2]), eval_(T, X)` gives `X = 3`.
- An **unbound** variable raises `instantiation_error`.
- An **atom**, a **string** or a **compound that is not evaluable** raises
  `type_error(evaluable, Name/Arity)` — `eval_(foo(1), X)` raises
  `type_error(evaluable, foo/1)`. Before 2026-09-27 these were handed back
  unevaluated (`X = foo(1)`), a silent wrong answer.
- A Python value — a [`Quantity`](units.md), a `date`, a list, the result of a
  `++` escape or of a qualified Python call such as `math.sqrt(X)` — keeps
  Python's own operators, as before: `eval_(L + [3], X)` concatenates and
  `eval_(++("%d") % 5, X)` formats.
- A Python `str` that reaches `eval_` through a **variable** or a qualified
  **name** (`os.sep`) is an atom — an atom *is* its str — and raises like any
  atom: `F is ++("%d items"), eval_(F % N, X)` raises
  `type_error(evaluable, '%d items'/0)`. Do string work in the escape:
  `X is ++(F % N)`.

Reach for `eval_/2` when you specifically need *eager* evaluation:

- **Unit-carrying values** — `eval_(20(metre), D)`, `eval_(D / T, V)`; CLP
  constraints don't operate on [`Quantity`](units.md) objects.
- **Catchable exceptions** — `catch(eval_(X // Y, R), E, ...)` sees
  `error(evaluation_error(zero_divisor), (//)/2)` when `Y` is 0. A
  constraint never raises it: over a zero divisor it simply fails.
- **Accumulator recursion** — an eagerly ground argument keeps
  tail-recursive predicates eligible for [tail-call
  optimisation](compiler.md).

Choosing an arithmetic idiom:

| Goal | Use |
|---|---|
| Relational arithmetic, any direction | `X == EXPR` |
| Eager arithmetic (Prolog `is/2`) | `eval_(EXPR, X)` |
| Structural unification (no evaluation) | `X is TERM` |
| Arbitrary Python expression | `X is ++(PYEXPR)` |

### Arithmetic terms built at runtime — the evaluable table

Arithmetic written in source (`1 + 2`) and arithmetic built as a term at
runtime (`unpack(T, ['+', 1, 2])`) are both evaluable. `eval_/2`, the ISO
`'is'`/`'=:='`/`'<'`… builtins, `==`/`!=`/`<`/`<=` (CLP(ℤ)),
`clpq.rational/1`, `clpr.real/1` and `between/3` all accept both spellings. A
cell evaluates through **one** table, keyed by name and arity; the table is
closed — there is no way to register a new evaluable functor. Its functors
are builtins: in scope in every module without a declaration
(`'is'(X, rdiv(7, 2))`, `'is'(X, '//'(-7, 2))`), and ordinary terms as data.

Operator rulings of 2026-09-28: the table is the **Scryer** meaning of each
functor, which a quoted spelling and a runtime-built cell get. A bare operator
written in source keeps Python's meaning, and the two differ for `//` and `**`
(see [Operators](operators.md)):

| Term | Meaning (Scryer) | Bare source operator (Python) |
|---|---|---|
| `+(A, B)`, `-(A, B)`, `*(A, B)` | exact (a `Decimal` keeps its scale) | `A + B`, `A - B`, `A * B`: the same |
| `/(A, B)` | division as a **float**: `'/'(7, 2)` is 3.5, `'/'(6, 2)` is 3.0 | `A / B`: Python true division, `7 / 2` is 3.5, `6 / 2` is 3.0 |
| `rdiv(A, B)` | **exact** rational division: `rdiv(7, 2)` is 7/2, `rdiv(6, 2)` is 3 | — |
| `//(A, B)` | integer division **truncating** toward zero: `'//'(-7, 2)` is -3 | `A // B` **floors**: `-7 // 2` is -4 |
| `div(A, B)` | integer division rounded toward negative infinity: -4 | — |
| `mod(A, B)` | integer modulo, sign of the divisor | `A % B`: Python modulo (the same on integers) |
| `**(A, B)` | power as a **float**: `'**'(2, 3)` is 8.0 | `A ** B`: Python power, `2 ** 3` is the integer 8 |
| `^(A, B)` | integer power: `'^'(2, 3)` is 8 | — (`A ^ B` is Python's XOR, for CLP(B)) |
| `-(A)` | negation | `-A`: the same |
| `abs(A)` | absolute value, in the operand's own kind: `abs(-3)` is 3, `abs(-3.5)` is 3.5 | — |
| `min(A, B)`, `max(A, B)` | the smaller / larger operand, in its own kind (`max(2, 5)` is 5); beside a float the operands compare as floats and a tie answers the float (`max(1, 1.0)` is 1.0) | — |
| `+(A)` | the number itself | `+A`: not evaluable (a Python unary plus) |
| `sign(A)` | -1, 0 or 1 in the operand's kind: `sign(-2.5)` is -1.0; an exact rational's sign is an integer | — |
| `rem(A, B)` | the remainder of `'//'`, the sign of the **dividend**: `rem(-7, 2)` is -1; integers only | — |
| `truncate(A)`, `round(A)`, `ceiling(A)`, `floor(A)` | an **integer** from any number: `truncate(-3.7)` is -3; `round` halves away from zero (`round(-2.5)` is -3), exactly | — |
| `float(A)` | the operand as a float: `float(rdiv(7, 2))` is 3.5 | — |
| `float_integer_part(A)`, `float_fractional_part(A)` | the integer part and the rest, as floats: -3.0 and -0.75 for -3.75 | — |
| `gcd(A, B)` | greatest common divisor, non-negative; integers only | — |
| `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log` (arity 1) | a **float**; an exact operand is taken at its value. `sqrt(-1)`, `log(0)`, `log(-1)`, `asin(2)` are `evaluation_error(undefined)`; `exp(1000)` is `evaluation_error(float_overflow)` | — |
| `atan2(Y, X)`, `atan(Y, X)` | the angle of the point (X, Y), a float; `atan2(0, 0)` is `evaluation_error(undefined)` | — |
| `pi`, `e` | the constants, as floats (`'is'(X, pi)`); no declaration needed in arithmetic position, ordinary atoms as data (see [Operators](operators.md#writing-a-quoted-arithmetic-cell)) | — |
| `'>>'(A, N)`, `'<<'(A, N)` | arithmetic shifts; a negative count shifts the other way (`'<<'(1, -1)` is 0); integers only | `A >> N`, `A << N`: Python shifts, not evaluable |
| `'/\\'(A, B)`, `'\\/'(A, B)`, `'\\'(A)`, `xor(A, B)` | bitwise and, or, complement, exclusive or (two's complement: `'\\'(5)` is -6); integers only | `&`, `\|`, `~`, `^`: Python's, for CLP(B); not evaluable |

`//`, `div` and `mod` take integers only (`type_error(integer, 7.0)` for
`'//'(7.0, 2)`), as in Scryer. `^` follows Scryer's rules for a negative
exponent: `'^'(2, -1)` is `type_error(float, 2)`, `'^'(1, -1)` is 1, and
`'^'(0, -1)` is `evaluation_error(undefined)`; an exact rational base stays
exact (`'^'(rdiv(1, 2), 2)` is 1/4, where Scryer answers 0.25). `rem`, `gcd`
and the bitwise functors take integers only, too (`type_error(integer, 1.0)`
for `xor(12, 1.0)`), and an integral rational counts as an integer
(`gcd(rdiv(12, 1), 18)` is 6; Scryer keeps `12 rdiv 1` a rational and
refuses it). The table is ISO's evaluables (ISO 13211-1 9.1.7, 9.3, 9.4 and
Cor.2) with Scryer's kinds and errors, and two ISO readings where Scryer
differs: `log(0)` is `evaluation_error(undefined)` (Scryer:
`float_overflow`), and `atan/2` is evaluable, as `atan2/2` (Scryer has only
`atan2/2`). `integer/1` and `log/2` are not in the table (nor in ISO or
Scryer). The exact-number term `decimal(M, S)` evaluates as the number it
denotes.

```seam
test("rounding") <- ('is'(A, round(-2.5)), A == -3, 'is'(B, truncate(3.7)), B == 3)
test("rem and gcd") <- ('is'(R, rem(-7, 2)), R == -1, 'is'(G, gcd(12, 18)), G == 6)
test("bitwise") <- ('is'(X, '/\\'(12, 10)), X == 8, 'is'(Y, '>>'(-7, 1)), Y == -4)
test("float functions") <- ('is'(S, sqrt(4)), S == 2.0, 'is'(P, pi), P > 3.14)
```

**Division (ruling Q15, 2026-09-28).** In *evaluation* — `eval_/2`, `'is'`,
the ISO comparisons — `/` is a float division for two integers: bare it is
Python's (`7 / 2` is 3.5, `6 / 2` is 3.0), quoted it is Scryer's (the same
floats). A bare `/` keeps exact kinds exact where Python does: a `Fraction`
over an int is a `Fraction`, a `Decimal` over an int is Python's `Decimal`
quotient (rounded at 28 digits). A `Decimal` beside a `Fraction` divides
exactly; a float beside either raises `type_error(exact_number, F)`. The
quoted `'/'` always answers a float. `rdiv` is the exact spelling:
`rdiv(7, 2)` is 7/2 and `rdiv(1, 3) + 1` is 4/3, and it never rounds.
**Inside a constraint** (`==`, `!=`, `<`, ...) `/` is rational, as before:
`X == 7 / 2` gives 7/2 and `X == 6 / 2` gives 3.

A **zero divisor** in plain arithmetic raises
`evaluation_error(zero_divisor)` naming the operator, on every spelling, bare or
quoted: `eval_(1 / 0, X)`, `'is'(X, 1 // 0)` and `'=:='(1, 1 / 0)` all raise it.

A **constraint** is a relation (ruling Q14, 2026-09-28): over an expression
with no value — a zero divisor, or `'^'(2, -1)` — it has no solutions and
**fails**, as Scryer's clpz does, in every goal order. `X == 1 // 0`,
`(X == 1 // Y, Y is 0)` and `X != 1 // 0` all fail; in a search
(`X == 10 // Y, in_domain(Y, 0, 2), label([Y])`) the branch Y = 0 fails and
the search goes on to Y = 1 and Y = 2; reified, as in
`if_(X == 1 // 0, ...)`, the test is false.

In a CLP(ℤ) constraint (`==`, `!=`, `<`, ...), a term that is not arithmetic
raises Scryer's `domain_error(clpz_expression, T)`: `X == foo(1)` raises
`error(domain_error(clpz_expression, foo(1)), (==)/2)`. So does the float
power `'**'`, which is not a clpz expression, over a CLP(ℤ) variable
(`X == '**'(Y, 2)`) or nested in a CLP(ℤ) expression (`X == Y + '**'(2, 3)`);
use `'^'` there. A ground `'**'(2, 3)` as a whole side of the comparison is
simply the float 8.0.

### Comparison operators

```seam
test("compare") <- (3 < 5, 5 >= 5, 10 != 7)
```

Both sides must be ground (bound to numbers) at evaluation time.

| Operator | Meaning |
|----------|---------|
| `<`      | less than |
| `>`      | greater than |
| `<=`     | less than or equal |
| `>=`     | greater than or equal |
| `==`     | equal |
| `!=`     | not equal |

---

## Relational Arithmetic Predicates

These work in multiple argument modes — give any two arguments and the third is
computed.

### plus/3

`plus(X, Y, Z)` — `Z = X + Y`. Any two arguments determine the third.

```seam
test("plus forward") <- plus(3, 4, 7)
test("plus subtract") <- (plus(3, Y, 7), Y == 4)
test("plus other") <- (plus(X, 4, 7), X == 3)
```

### succ/2

`succ(X, Y)` — `Y = X + 1` for non-negative integers. Bidirectional.

```seam
test("succ forward") <- succ(4, 5)
test("succ backward") <- (succ(X, 5), X == 4)
```

---

## Range Generation

### between/3

`between(Low, High, X)` — generate or test integers in a range (inclusive).

```seam
test("generate") <- (between(1, 5, X), X == 3)
test("check") <- between(1, 10, 7)
```

`between` is nondeterministic in generate mode — it yields each integer on
backtracking.

---

## Numeric Functions

### abs_/2

`abs_(X, Y)` — `Y` is the absolute value of `X`.

```seam
test("abs") <- abs_(-7, 7)
```

### sign/2

`sign(X, S)` — `S` is `-1`, `0`, or `1` depending on the sign of `X`.

```seam
test("sign negative") <- sign(-42, -1)
test("sign zero") <- sign(0, 0)
test("sign positive") <- sign(99, 1)
```

### max_/3, min_/3

`max_(X, Y, Z)` / `min_(X, Y, Z)` — `Z` is the maximum/minimum of `X` and `Y`.

```seam
test("max") <- max_(3, 7, 7)
test("min") <- min_(3, 7, 3)
```

### gcd/3

`gcd(X, Y, G)` — `G` is the greatest common divisor of `X` and `Y`.

```seam
test("gcd") <- gcd(12, 8, 4)
test("coprime") <- gcd(7, 13, 1)
```

### divmod_/4

`divmod_(X, Y, Quotient, Remainder)` — integer division and modulo in one step.

```seam
test("divmod") <- divmod_(17, 5, 3, 2)
```

---

## Patterns & Recipes

### Fibonacci with accumulator

```seam
fib(N, F) <- fib_acc(N, 0, 1, F)
fib_acc(0, A, _, A),
fib_acc(N, A, B, F) <- (
    N > 0,
    N1 == N - 1,
    C == A + B,
    fib_acc(N1, B, C, F)
)

test("fib 10") <- fib(10, 55)
```

### Collatz sequence length

```seam
collatz(1, 0),
collatz(N, STEPS) <- (
    N > 1,
    MOD == N % 2,
    MOD == 0,
    HALF == N // 2,
    collatz(HALF, S),
    STEPS == S + 1
)
collatz(N, STEPS) <- (
    N > 1,
    MOD == N % 2,
    MOD == 1,
    NEXT == 3 * N + 1,
    collatz(NEXT, S),
    STEPS == S + 1
)

test("collatz 6") <- collatz(6, 8)
```

### sum_ of digits

```seam
digit_sum(0, 0),
digit_sum(N, SUM) <- (
    N > 0,
    divmod_(N, 10, REST, DIGIT),
    digit_sum(REST, S),
    SUM == S + DIGIT
)

test("digit sum") <- digit_sum(123, 6)
```

---

## Gotchas

- **`==` posts a constraint** — `X == 3 + 4` constrains X to 7 and works even
  when X is unbound. Use `eval_/2` only when you need eager evaluation
  (units, catchable exceptions, accumulator recursion), and
  [`++`](python_integration.md) for arbitrary Python such as string operations.
- **Both sides of comparisons must be ground** — `X > 3` fails if `X` is
  unbound. Use [CLP(ℤ)](constraints.md) for constraints over unbound variables.
- **`plus/3` requires at least two bound arguments** — it cannot enumerate all
  solutions to `plus(X, Y, 10)`.
- **Integer division** — `//` floors like Python's (`-7 // 2` is -4); the
  quoted `'//'(A, B)` truncates like Prolog's (-3). `/` is a float in
  evaluation (`eval_(7 / 2, X)` is 3.5) and rational inside a constraint;
  `rdiv` is exact everywhere.

---

*See also: [CLP(ℤ)](constraints.md) — arithmetic constraints over integers, [Type Checking](type_checking.md) — integer, float_, number.*
