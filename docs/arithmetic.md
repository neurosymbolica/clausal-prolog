# Arithmetic

Clausal Prolog has ISO arithmetic: `is/2` evaluates an expression, the
comparisons `=:=`, `<`, `>=` ... compare two evaluated expressions, and
[CLP(ℤ)](constraints.md) (`library(clpz)`) adds `#=`, `#<` ... as relations
that work in every direction. A library of relational arithmetic predicates
(`plus/3`, `succ/2`, `between/3`, ...) completes it.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`): ISO Prolog syntax, where an operator means what it means
    in ISO and Scryer Prolog (`-7 // 2` is -3). The [seam](syntax.md),
    Clausal's Python-syntax surface, spells arithmetic differently: its
    bare `==` posts a constraint, its `is` is unification, and its bare
    operators keep Python's meaning (`-7 // 2` is -4 there). Where the
    difference matters, this page says which surface it describes.

---

## Quick Example

```clausal
:- use_module(library(clpz)).

factorial(0, 1).
factorial(N, F) :-
    N > 0,
    N1 #= N - 1,
    factorial(N1, F1),
    F #= N * F1.

test("fact 5") :-
    factorial(5, 120).
```

---

## Evaluation & Comparison

### The `#=` constraint

`#=` (from `library(clpz)`) posts an arithmetic constraint over integers
([CLP(ℤ)](constraints.md)) that works in all directions: `7 #= X + 4`
answers `X = 3`.

```clausal
:- use_module(library(clpz)).

test("eval") :-
    X #= 3 + 4 * 2,
    X == 11.
```

Inside a constraint, `abs`, `min` and `max` are constraints too:
`X #= max(Y, 3), Y = 5` answers `X = 5`. A term that is not a clpz
expression raises Scryer's `domain_error(clpz_expression, T)`; see
[below](#arithmetic-terms-built-at-runtime-the-evaluable-table).

In the seam the same constraint is the bare `X == 3 + 4 * 2`.

### eval_/2 — eager evaluation

`X is EXPR` (ISO `is/2`) evaluates `EXPR` immediately and unifies the value
with `X`. `eval_(EXPR, X)` is the library name for the same evaluation:

```clausal
test("eval") :-
    eval_(6 * 7, X),
    X == 42.

test("is") :-
    X is 6 * 7,
    X == 42.
```

Prefer `#=` for ordinary relational arithmetic — it works in all
directions. `EXPR` is evaluated the way ISO `is/2` evaluates:

- A **variable** is evaluated at runtime, whatever it is bound to — a number,
  or an arithmetic term such as `1 + 2` built by `=..` or `functor/3`.
  `T =.. [+, 1, 2], X is T` gives `X = 3`.
- An **unbound** variable raises `instantiation_error`.
- An **atom**, a **string** or a **compound that is not evaluable** raises
  `type_error(evaluable, Name/Arity)` — `eval_(foo(1), X)` raises
  `type_error(evaluable, foo/1)`, and `X is a` raises
  `type_error(evaluable, a/0)`. Before 2026-09-27 these were handed back
  unevaluated (`X = foo(1)`), a silent wrong answer.

Reach for `is/2` when you specifically need *eager* evaluation:

- **Catchable exceptions** — `catch(X is 1 // Y, E, ...)` sees
  `error(evaluation_error(zero_divisor), (//)/2)` when `Y` is 0. A
  constraint never raises it: over a zero divisor it simply fails.
- **Accumulator recursion** — an eagerly ground argument keeps
  tail-recursive predicates eligible for [tail-call
  optimisation](compiler.md).
- **Floats** — CLP(ℤ) is over integers; `X is sqrt(2)` is the way to a
  float.

Choosing an arithmetic idiom:

| Goal | Clausal Prolog | The seam |
|---|---|---|
| Relational arithmetic, any direction | `X #= EXPR` (`library(clpz)`) | `X == EXPR` |
| Eager arithmetic (ISO `is/2`) | `X is EXPR`, or `eval_(EXPR, X)` | `eval_(EXPR, X)` |
| Compare two evaluated expressions | `A =:= B`, `A < B`, ... | `'=:='(A, B)`, `'<'(A, B)`, ... |
| Structural unification (no evaluation) | `X = TERM` | `X is TERM` |
| Arbitrary Python expression | — | `X is ++(PYEXPR)` |

!!! note "In the seam: Python values and qualified calls"

    Only the seam escapes into Python; Clausal Prolog imports modules and
    never escapes. In the seam, `eval_/2` also evaluates Python values:

    - A Python value — a [`Quantity`](units.md), a `date`, a list, the result of a
      `++` escape or of a qualified Python call such as `math.sqrt(X)` — keeps
      Python's own operators: `eval_(L + [3], X)` concatenates and
      `eval_(++("%d") % 5, X)` formats.
    - A Python `str` that reaches `eval_` through a **variable** or a qualified
      **name** (`os.sep`) is an atom — an atom *is* its str — and raises like any
      atom: `F is ++("%d items"), eval_(F % N, X)` raises
      `type_error(evaluable, '%d items'/0)`. Do string work in the escape:
      `X is ++(F % N)`.
    - **Unit-carrying values** — `eval_(20(metre), D)`, `eval_(D / T, V)`; CLP
      constraints don't operate on [`Quantity`](units.md) objects.

    The seam's `X is TERM` builds TERM without evaluating it, but a qualified **Python
    call** in it is made (`X is math.sqrt(16)` binds 4.0, `M is
    torch.nn.Linear(10, 5)` a module). A qualified **predicate adapter** is not a
    Python call: `X is torch.tensor([1, 2])`, where `torch.tensor` is the
    adapter's `tensor/2` predicate, raises `type_error(evaluable,
    'torch.tensor'/1)` -- the term `eval_` gives for it -- instead of binding the
    compound `'torch.tensor'([1, 2])`. The same holds for an adapter call in an
    ARITHMETIC position of a side -- an operand of `+ - * / // % **` or unary
    `-`, or an argument of an evaluable function such as `abs/1` or `max/2`,
    at any depth: `X is 1 + torch.tensor_sum(L)` raises too. Anywhere else it
    still builds its compound: in a list (`X is [torch.tensor(L)]`), a tuple,
    or a data or goal term (`G is f(m.p(A))`). The comparisons `==`, `!=`,
    `<`, `<=`, `>`, `>=` check their sides the same way and name themselves in
    the error (`1 < 1 + torch.tensor_sum(L)` raises `type_error(evaluable,
    'torch.tensor_sum'/1)` with context `(<)/2`); so does the test of `if_/3`,
    and an `is` or comparison built as a goal term (`G is (X < m.p(A))`)
    raises where it is built. `eval_/2`, the quoted ISO forms (`'is'`, `'<'`
    ...) and `{...}` raised already. Call the predicate as a goal
    (`tensor([1, 2], X)`). The bare imported spelling, `G is match(P, S)` after
    `-import_from(py.re, [match])`, still builds a goal for `call/1`.

### Arithmetic terms built at runtime — the evaluable table

Arithmetic written in source (`1 + 2`) and arithmetic built as a term at
runtime (`T =.. [+, 1, 2]`) are both evaluable. `is/2`, `eval_/2`, the ISO
comparisons (`=:=`, `<`, ...), the CLP(ℤ) constraints (`#=`, `#<`, ...) and
`between/3` all accept both. A cell evaluates through **one** table, keyed
by name and arity; the table is closed — there is no way to register a new
evaluable functor. Its functors are builtins: in scope in every module
without a declaration (`X is rdiv(7, 2)`), and ordinary terms as data.

Operator rulings of 2026-09-28: the table is the **Scryer** meaning of each
functor. In Clausal Prolog that is what an operator written in source means.
In the seam it is what a quoted spelling (`'//'(-7, 2)`) and a runtime-built
cell mean, while a bare seam operator keeps Python's meaning; the two
differ for `//` and `**` (see [Operators](operators.md)). The last column
is the seam's bare operator.

| Term | Meaning (Scryer, and Clausal Prolog) | Seam bare operator (Python) |
|---|---|---|
| `A + B`, `A - B`, `A * B` | exact (a `Decimal` keeps its scale) | the same |
| `A / B` | division as a **float**: `7 / 2` is 3.5, `6 / 2` is 3.0 | Python true division, `7 / 2` is 3.5, `6 / 2` is 3.0 |
| `A rdiv B` | **exact** rational division: `7 rdiv 2` is `7 rdiv 2`, `6 rdiv 2` is 3 | — |
| `A // B` | integer division **truncating** toward zero: `-7 // 2` is -3 | `A // B` **floors**: `-7 // 2` is -4 |
| `A div B` | integer division rounded toward negative infinity: `-7 div 2` is -4 | — |
| `A mod B` | integer modulo, sign of the divisor: `-7 mod 2` is 1, `7 mod -2` is -1 | `A % B`: Python modulo (the same on integers) |
| `A ** B` | power as a **float**: `2 ** 3` is 8.0 | Python power, `2 ** 3` is the integer 8 |
| `A ^ B` | integer power: `2 ^ 3` is 8 | — (`A ^ B` is Python's XOR, for CLP(B)) |
| `-A` | negation | the same |
| `abs(A)` | absolute value, in the operand's own kind: `abs(-3)` is 3, `abs(-3.5)` is 3.5 | — |
| `min(A, B)`, `max(A, B)` | the smaller / larger operand, in its own kind (`max(2, 5)` is 5); beside a float the operands compare as floats and a tie answers the float (`max(1, 1.0)` is 1.0) | — |
| `+A` | the number itself | not evaluable (a Python unary plus) |
| `sign(A)` | -1, 0 or 1 in the operand's kind: `sign(-2.5)` is -1.0; an exact rational's sign is an integer | — |
| `A rem B` | the remainder of `//`, the sign of the **dividend**: `-7 rem 2` is -1; integers only | — |
| `truncate(A)`, `round(A)`, `ceiling(A)`, `floor(A)` | an **integer** from any number: `truncate(-3.7)` is -3; `round` halves away from zero (`round(-2.5)` is -3), exactly | — |
| `float(A)` | the operand as a float: `float(7 rdiv 2)` is 3.5 | — |
| `float_integer_part(A)`, `float_fractional_part(A)` | the integer part and the rest, as floats: -3.0 and -0.75 for -3.75 | — |
| `gcd(A, B)` | greatest common divisor, non-negative; integers only | — |
| `sqrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `exp`, `log` (arity 1) | a **float**; an exact operand is taken at its value. `sqrt(-1)`, `log(0)`, `log(-1)`, `asin(2)` are `evaluation_error(undefined)`; `exp(1000)` is `evaluation_error(float_overflow)` | — |
| `atan2(Y, X)`, `atan(Y, X)` | the angle of the point (X, Y), a float; `atan2(0, 0)` is `evaluation_error(undefined)` | — |
| `pi`, `e` | the constants, as floats (`X is pi`); no declaration needed in arithmetic position, ordinary atoms as data (see [Operators](operators.md#writing-a-quoted-arithmetic-cell)) | — |
| `A >> N`, `A << N` | arithmetic shifts; a negative count shifts the other way (`1 << -1` is 0); integers only | Python shifts, not evaluable |
| `A /\ B`, `A \/ B`, `\ A`, `xor(A, B)` | bitwise and, or, complement, exclusive or (two's complement: `\ 5` is -6); integers only | `&`, `\|`, `~`, `^`: Python's, for CLP(B); not evaluable |

`//`, `div` and `mod` take integers only (`type_error(integer, 7.0)` for
`7.0 // 2`), as in Scryer. `^` follows Scryer's rules for a negative
exponent: `2 ^ -1` is `type_error(float, 2)`, `1 ^ -1` is 1, and
`0 ^ -1` is `evaluation_error(undefined)`; an exact rational base stays
exact (`(1 rdiv 2) ^ 2` is `1 rdiv 4`, where Scryer answers 0.25). `rem`, `gcd`
and the bitwise functors take integers only, too (`type_error(integer, 1.0)`
for `xor(12, 1.0)`), and an integral rational counts as an integer
(`gcd(12 rdiv 1, 18)` is 6; Scryer keeps `12 rdiv 1` a rational and
refuses it). The table is ISO's evaluables (ISO 13211-1 9.1.7, 9.3, 9.4 and
Cor.2) with Scryer's kinds and errors, and two ISO readings where Scryer
differs: `log(0)` is `evaluation_error(undefined)` (Scryer:
`float_overflow`), and `atan/2` is evaluable, as `atan2/2` (Scryer has only
`atan2/2`). `integer/1` and `log/2` are not in the table (nor in ISO or
Scryer). The exact-number term `decimal(M, S)` evaluates as the number it
denotes (`decimal(314, 2)` is 3.14).

```clausal
test("rounding") :-
    A is round(-2.5),
    A == -3,
    B is truncate(3.7),
    B == 3.

test("rem and gcd") :-
    R is -7 rem 2,
    R == -1,
    G is gcd(12, 18),
    G == 6.

test("bitwise") :-
    X is 12 /\ 10,
    X == 8,
    Y is -7 >> 1,
    Y == -4.

test("float functions") :-
    S is sqrt(4),
    S == 2.0,
    P is pi,
    P > 3.14.

test("integer division") :-
    Q is -7 // 2,
    Q == -3,
    D is -7 div 2,
    D == -4.
```

**Division (ruling Q15, 2026-09-28).** In *evaluation* — `is/2`,
`eval_/2`, the ISO comparisons — `/` always answers a float: `7 / 2` is
3.5, `6 / 2` is 3.0, and `(1 rdiv 2) / 2` is 0.25. `rdiv` is the exact
spelling: `7 rdiv 2` is `7 rdiv 2` and `(1 rdiv 3) + 1` is `4 rdiv 3`, and
it never rounds. (In the seam, a *bare* `/` keeps exact kinds exact where
Python does: a `Fraction` over an int is a `Fraction`, a `Decimal` over an
int is Python's `Decimal` quotient; there the quoted `'/'` is the
always-float one.) **Inside a CLP(ℤ) constraint** `/` is integer division
that must be exact: `X #= 6 / 2` gives 3 and `X #= 7 / 2` fails. (In the
seam, `/` inside a constraint is rational: `X == 7 / 2` gives 7/2.)

A **zero divisor** in plain arithmetic raises
`evaluation_error(zero_divisor)` naming the operator: `eval_(1 / 0, X)`,
`X is 1 // 0` and `1 =:= 1 / 0` all raise it.

A **constraint** is a relation (ruling Q14, 2026-09-28): over an expression
with no value — a zero divisor, or `2 ^ -1` — it has no solutions and
**fails**, as Scryer's clpz does, in every goal order. `X #= 1 // 0`,
`(X #= 1 // Y, Y = 0)` and `X #\= 1 // 0` all fail; in a search
(`X #= 10 // Y, Y in 0..2, label([Y])`) the branch Y = 0 fails and
the search goes on to Y = 1 and Y = 2; reified, `B #<==> (X #= 1 // 0)`
gives `B = 0`. (So does the test of `if_/3`: the seam's
`if_(X == 1 // 0, ...)`, and in Clausal Prolog clpz's reified
`if_(X #= 1 // 0, ...)`, take the else branch.)

In a CLP(ℤ) constraint (`#=`, `#\=`, `#<`, ...), a term that is not
arithmetic raises Scryer's `domain_error(clpz_expression, T)`:
`X #= foo(1)` raises `error(domain_error(clpz_expression, foo(1)), (#=)/2)`.
So does the float power `**`, which is not a clpz expression, over a
CLP(ℤ) variable (`X #= Y ** 2`) or nested in a CLP(ℤ) expression
(`X #= Y + 2 ** 3`); use `^` there. A ground `2 ** 3` as a whole side of
the comparison is simply the float 8.0.

### Comparison operators

```clausal
test("compare") :-
    3 < 5,
    5 >= 5,
    10 =\= 7.
```

Both sides are evaluated, so both must be ground (bound to numbers or
arithmetic terms) at evaluation time; an unbound side raises
`instantiation_error`.

| Operator | Meaning | Seam spelling |
|----------|---------|---------------|
| `<`      | less than | `<` |
| `>`      | greater than | `>` |
| `=<`     | less than or equal | `<=` |
| `>=`     | greater than or equal | `>=` |
| `=:=`    | equal | `==` |
| `=\=`    | not equal | `!=` |

`==` is ISO term identity, not arithmetic: `1 + 2 =:= 3` succeeds, while
`1 + 2 == 3` fails. Over unbound variables use the CLP(ℤ) forms `#<`, `#>`,
`#=<`, `#>=`, `#=`, `#\=`.

---

## Relational Arithmetic Predicates

These work in multiple argument modes — give any two arguments and the third is
computed.

### plus/3

`plus(X, Y, Z)` — `Z = X + Y`. Any two arguments determine the third.

```clausal
test("plus forward") :-
    plus(3, 4, 7).

test("plus subtract") :-
    plus(3, Y, 7),
    Y == 4.

test("plus other") :-
    plus(X, 4, 7),
    X == 3.
```

### succ/2

`succ(X, Y)` — `Y = X + 1` for non-negative integers. Bidirectional.

```clausal
test("succ forward") :-
    succ(4, 5).

test("succ backward") :-
    succ(X, 5),
    X == 4.
```

---

## Range Generation

### between/3

`between(Low, High, X)` — generate or test integers in a range (inclusive).

```clausal
test("generate") :-
    between(1, 5, X),
    X == 3.

test("check") :-
    between(1, 10, 7).
```

`between` is nondeterministic in generate mode — it yields each integer on
backtracking.

---

## Numeric Functions

### abs_/2

`abs_(X, Y)` — `Y` is the absolute value of `X`.

```clausal
test("abs") :-
    abs_(-7, 7).
```

### sign/2

`sign(X, S)` — `S` is `-1`, `0`, or `1` depending on the sign of `X`.

```clausal
test("sign negative") :-
    sign(-42, -1).

test("sign zero") :-
    sign(0, 0).

test("sign positive") :-
    sign(99, 1).
```

### max_/3, min_/3

`max_(X, Y, Z)` / `min_(X, Y, Z)` — `Z` is the maximum/minimum of `X` and `Y`.

```clausal
test("max") :-
    max_(3, 7, 7).

test("min") :-
    min_(3, 7, 3).
```

### gcd/3

`gcd(X, Y, G)` — `G` is the greatest common divisor of `X` and `Y`.

```clausal
test("gcd") :-
    gcd(12, 8, 4).

test("coprime") :-
    gcd(7, 13, 1).
```

### divmod_/4

`divmod_(X, Y, Quotient, Remainder)` — integer division and modulo in one step.

```clausal
test("divmod") :-
    divmod_(17, 5, 3, 2).
```

---

## Patterns & Recipes

### Fibonacci with accumulator

```clausal
:- use_module(library(clpz)).

fib(N, F) :-
    fib_acc(N, 0, 1, F).

fib_acc(0, A, _, A).
fib_acc(N, A, B, F) :-
    N > 0,
    N1 #= N - 1,
    C #= A + B,
    fib_acc(N1, B, C, F).

test("fib 10") :-
    fib(10, 55).
```

### Collatz sequence length

```clausal
:- use_module(library(clpz)).

collatz(1, 0).
collatz(N, STEPS) :-
    N > 1,
    N mod 2 =:= 0,
    HALF #= N div 2,
    collatz(HALF, S),
    STEPS #= S + 1.
collatz(N, STEPS) :-
    N > 1,
    N mod 2 =:= 1,
    NEXT #= 3 * N + 1,
    collatz(NEXT, S),
    STEPS #= S + 1.

test("collatz 6") :-
    collatz(6, 8).
```

### sum_ of digits

```clausal
:- use_module(library(clpz)).

digit_sum(0, 0).
digit_sum(N, SUM) :-
    N > 0,
    divmod_(N, 10, REST, DIGIT),
    digit_sum(REST, S),
    SUM #= S + DIGIT.

test("digit sum") :-
    digit_sum(123, 6).
```

---

## Gotchas

- **`#=` posts a constraint** — `X #= 3 + 4` constrains X to 7 and works even
  when X is unbound (load `library(clpz)`). Use `is/2` only when you need
  eager evaluation (floats, catchable exceptions, accumulator recursion).
- **`==` is not arithmetic** — it compares terms: `1 + 2 == 3` fails. Use
  `=:=` to compare values, `#=` to constrain them. (In the seam, the bare
  `==` *is* the constraint.)
- **Both sides of comparisons must be ground** — `X > 3` raises
  `instantiation_error` if `X` is unbound. Use [CLP(ℤ)](constraints.md)
  (`X #> 3`) for constraints over unbound variables.
- **`plus/3` requires at least two bound arguments** — it cannot enumerate
  the solutions of `plus(X, Y, 10)`; that goal fails.
- **Integer division** — `//` truncates, as ISO's does (`-7 // 2` is -3);
  `div` floors (-4). In the seam the bare `//` floors like Python's.
  `/` is a float in evaluation (`X is 7 / 2` is 3.5) and exact integer
  division inside a CLP(ℤ) constraint; `rdiv` is exact everywhere.

---

*See also: [CLP(ℤ)](constraints.md) — arithmetic constraints over integers, [Type Checking](type_checking.md) — integer, float_, number.*
