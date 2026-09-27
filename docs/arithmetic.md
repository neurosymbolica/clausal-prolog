# Arithmetic

Clausal supports Python's arithmetic operators directly in clause bodies, plus
relational arithmetic predicates that work in multiple directions.

---

## Quick Example

```clausal
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

```clausal
test("eval") <- (X == 3 + 4 * 2, X == 11)
```

Supported operators: `+`, `-`, `*`, `/`, `//` (integer division), `%` (modulo),
`**` (power), `abs()`, `min()`, `max()`.

### eval_/2 — eager evaluation

`eval_(EXPR, RESULT)` evaluates `EXPR` immediately and unifies the value with
`RESULT` (Prolog's `is/2`):

```clausal
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

Reach for `eval_/2` when you specifically need *eager* evaluation:

- **Unit-carrying values** — `eval_(20(metre), D)`, `eval_(D / T, V)`; CLP
  constraints don't operate on [`Quantity`](units.md) objects.
- **Catchable exceptions** — `catch(eval_(X // Y, R), _, ...)` sees the
  `ZeroDivisionError`; a constraint would not raise it.
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
runtime (`unpack(T, ['+', 1, 2])`) evaluate through **one** table, keyed by
name and arity. `eval_/2`, the ISO `'is'`/`'=:='`/`'<'`… builtins, `==`/`!=`/
`<`/`<=` (CLP(ℤ)), `clpq.rational/1`, `clpr.real/1` and `between/3` all accept
both spellings. The table is closed — there is no way to register a new
evaluable functor:

| Term | Source spelling | Meaning |
|---|---|---|
| `+(A, B)`, `-(A, B)`, `*(A, B)` | `A + B`, `A - B`, `A * B` | exact (a `Decimal` keeps its scale) |
| `/(A, B)` | `A / B` | exact division: `7 / 2` is the rational 7/2 |
| `div(A, B)` | `A // B` | division rounded toward negative infinity |
| `mod(A, B)` | `A % B` | modulo, sign of the divisor |
| `**(A, B)` | `A ** B` | power: `2 ** 3` is the integer 8 |
| `-(A)` | `-A` | negation |

The ISO spelling `//(A, B)` is **not** in the table: ISO `//` rounds toward
zero in Scryer and SWI, while Clausal's `//` floors, so a term `//(-7, 2)`
raises `type_error(evaluable, (//)/2)` instead of answering -4 where Scryer
answers -3. Use `div` (floored) or `prolog.TruncDiv` (toward zero). The
exact-number terms `rdiv(N, D)` and `decimal(M, S)` evaluate as the number they
denote.

### Comparison operators

```clausal
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

```clausal
test("plus forward") <- plus(3, 4, 7)
test("plus subtract") <- (plus(3, Y, 7), Y == 4)
test("plus other") <- (plus(X, 4, 7), X == 3)
```

### succ/2

`succ(X, Y)` — `Y = X + 1` for non-negative integers. Bidirectional.

```clausal
test("succ forward") <- succ(4, 5)
test("succ backward") <- (succ(X, 5), X == 4)
```

---

## Range Generation

### between/3

`between(Low, High, X)` — generate or test integers in a range (inclusive).

```clausal
test("generate") <- (between(1, 5, X), X == 3)
test("check") <- between(1, 10, 7)
```

`between` is nondeterministic in generate mode — it yields each integer on
backtracking.

---

## Numeric Functions

### abs_/2

`abs_(X, Y)` — `Y` is the absolute value of `X`.

```clausal
test("abs") <- abs_(-7, 7)
```

### sign/2

`sign(X, S)` — `S` is `-1`, `0`, or `1` depending on the sign of `X`.

```clausal
test("sign negative") <- sign(-42, -1)
test("sign zero") <- sign(0, 0)
test("sign positive") <- sign(99, 1)
```

### max_/3, min_/3

`max_(X, Y, Z)` / `min_(X, Y, Z)` — `Z` is the maximum/minimum of `X` and `Y`.

```clausal
test("max") <- max_(3, 7, 7)
test("min") <- min_(3, 7, 3)
```

### gcd/3

`gcd(X, Y, G)` — `G` is the greatest common divisor of `X` and `Y`.

```clausal
test("gcd") <- gcd(12, 8, 4)
test("coprime") <- gcd(7, 13, 1)
```

### divmod_/4

`divmod_(X, Y, Quotient, Remainder)` — integer division and modulo in one step.

```clausal
test("divmod") <- divmod_(17, 5, 3, 2)
```

---

## Patterns & Recipes

### Fibonacci with accumulator

```clausal
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

```clausal
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

```clausal
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
- **Integer division** — use `//` for integer division, `/` for float division.

---

*See also: [CLP(ℤ)](constraints.md) — arithmetic constraints over integers, [Type Checking](type_checking.md) — integer, float_, number.*
