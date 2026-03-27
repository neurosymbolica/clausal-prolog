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

Test("fact 5") <- factorial(5, 120)
```

---

## Evaluation & Comparison

### The `==` operator

`==` posts an arithmetic constraint ([CLP(ℤ)](constraints.md) or [CLP(ℝ)](clpr.md)) that works in all directions:

```clausal
Test("eval") <- (X == 3 + 4 * 2, X == 11)
```

Supported operators: `+`, `-`, `*`, `/`, `//` (integer division), `%` (modulo),
`**` (power), `abs()`, `min()`, `max()`.

### Comparison operators

```clausal
Test("compare") <- (3 < 5, 5 >= 5, 10 != 7)
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
Test("plus forward") <- plus(3, 4, 7)
Test("plus subtract") <- (plus(3, Y, 7), Y == 4)
Test("plus other") <- (plus(X, 4, 7), X == 3)
```

### succ/2

`succ(X, Y)` — `Y = X + 1` for non-negative integers. Bidirectional.

```clausal
Test("succ forward") <- succ(4, 5)
Test("succ backward") <- (succ(X, 5), X == 4)
```

---

## Range Generation

### between/3

`between(Low, High, X)` — generate or test integers in a range (inclusive).

```clausal
Test("generate") <- (between(1, 5, X), X == 3)
Test("check") <- between(1, 10, 7)
```

`between` is nondeterministic in generate mode — it yields each integer on
backtracking.

---

## Numeric Functions

### abs_/2

`abs_(X, Y)` — `Y` is the absolute value of `X`.

```clausal
Test("abs") <- abs_(-7, 7)
```

### sign/2

`sign(X, S)` — `S` is `-1`, `0`, or `1` depending on the sign of `X`.

```clausal
Test("sign negative") <- sign(-42, -1)
Test("sign zero") <- sign(0, 0)
Test("sign positive") <- sign(99, 1)
```

### max_/3, min_/3

`max_(X, Y, Z)` / `min_(X, Y, Z)` — `Z` is the maximum/minimum of `X` and `Y`.

```clausal
Test("max") <- max_(3, 7, 7)
Test("min") <- min_(3, 7, 3)
```

### gcd/3

`gcd(X, Y, G)` — `G` is the greatest common divisor of `X` and `Y`.

```clausal
Test("gcd") <- gcd(12, 8, 4)
Test("coprime") <- gcd(7, 13, 1)
```

### divmod_/4

`divmod_(X, Y, Quotient, Remainder)` — integer division and modulo in one step.

```clausal
Test("divmod") <- divmod_(17, 5, 3, 2)
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

Test("fib 10") <- fib(10, 55)
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

Test("collatz 6") <- collatz(6, 8)
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

Test("digit sum") <- digit_sum(123, 6)
```

---

## Gotchas

- **`==` posts a constraint** — `X == 3 + 4` constrains X to 7 and works even
  when X is unbound. Use `:=` only when you need eager Python-side evaluation
  (e.g., with [`++`](python_integration.md) for string operations).
- **Both sides of comparisons must be ground** — `X > 3` fails if `X` is
  unbound. Use [CLP(ℤ)](constraints.md) for constraints over unbound variables.
- **`plus/3` requires at least two bound arguments** — it cannot enumerate all
  solutions to `plus(X, Y, 10)`.
- **Integer division** — use `//` for integer division, `/` for float division.

---

*See also: [CLP(ℤ)](constraints.md) — arithmetic constraints over finite
domains, [Type Checking](type_checking.md) — integer, float_, number.*
