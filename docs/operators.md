# Operators: Python meaning vs Prolog meaning

Many operator spellings exist in both worlds Clausal joins: Python and ISO
Prolog. Clausal decides which meaning applies by **how the operator is
written**, not by where it appears:

- **Bare** (`-7 // 2`, `2 ** 3`): today's source syntax, the Python-shaped
  syntax of `.clausal` and `.seam` files, clause bodies and `--` expressions
  alike. A bare arithmetic operator keeps **Python's** meaning.
- **Quoted, or built as a cell** (`'//'(-7, 2)`, `'**'(2, 3)`, or a term
  built at runtime with `unpack(T, ['//', -7, 2])`): the operator follows
  **Scryer Prolog**, and through it ISO 13211-1.
- **Future Clausal Prolog syntax** (planned, not built yet): the bare
  operator will follow Scryer, and Python's meaning will be reachable only
  inside `++(...)`.

The rule, in the operator's words: *operators in seam syntax follow Python
semantics unless quoted; quoted ones follow Scryer's.*

## Arithmetic

| Spelling | Bare, today's syntax: Python meaning | Quoted / cell: Scryer meaning | Future Clausal Prolog syntax |
|---|---|---|---|
| `+` `-` `*` | exact addition, subtraction, multiplication (a `Decimal` keeps its scale) | the same | the same |
| `/` | in evaluation (`eval_`, `'is'`, the ISO comparisons): Python true division — `7 / 2` is 3.5, `6 / 2` is **3.0**; a `Fraction` or `Decimal` operand stays exact as in Python. **Inside a constraint** (`==`, `<`, ...): exact rational, `X == 7 / 2` gives 7/2 and `X == 6 / 2` gives 3 (CLP(ℚ), like Scryer's `{X = 7/2}`) | Scryer's division, always a float: `'/'(7, 2)` is 3.5, `'/'(6, 2)` is 3.0; inside a constraint, rational as the bare one | Scryer: a float in evaluation; rational inside `{...}` |
| `rdiv` | (no bare spelling) | the **exact** rational division: `rdiv(7, 2)` is 7/2, `rdiv(6, 2)` is 3, everywhere | the same |
| `//` | Python floor division: `-7 // 2` is **-4** | ISO integer division, **truncating** toward zero: `'//'(-7, 2)` is **-3**; integers only | Scryer: truncates |
| `div` | (no bare spelling) | ISO floored division: `div(-7, 2)` is -4; integers only | the same |
| `%` | Python modulo, sign of the divisor: `-7 % 2` is 1 | (no quoted `%`; write `mod`) | Python's `%` only inside `++` |
| `mod` | (no bare spelling) | ISO modulo, sign of the divisor: `mod(-7, 2)` is 1; integers only | the same |
| `rem` | (none) | ISO remainder, the sign of the dividend: `rem(-7, 2)` is -1; integers only | the same |
| `**` | Python power: `2 ** 3` is the **integer 8**; `2 ** -1` is 0.5 | ISO power, always a **float**: `'**'(2, 3)` is **8.0** | Scryer: a float |
| `^` | Python bitwise XOR — as a CLP(B) formula in `sat(X ^ Y)`; not evaluable by `eval_` | ISO integer power: `'^'(2, 3)` is 8; `'^'(2, -1)` is `type_error(float, 2)`; `'^'(1, -1)` is 1 | Scryer: integer power |
| `&` `\|` `~` | Python bitwise AND / OR / NOT — CLP(B) formulas in `sat(...)`; not evaluable by `eval_` (`type_error(evaluable, (&)/2)`) | no ISO operator of these spellings; ISO's bitwise functors are the quoted `'/\\'(A, B)`, `'\\/'(A, B)`, `'\\'(A)` and `xor(A, B)`, integers only (`'/\\'(12, 10)` is 8) | Scryer: `/\`, `\/`, `\`, `xor` |
| `<<` `>>` | Python shifts; not evaluable by `eval_` | ISO shifts, integers only: `'>>'(-7, 1)` is -4; a negative count shifts the other way (`'<<'(1, -1)` is 0) | Scryer: the same |
| unary `-` | negation | the same: `'-'(5)` is -5 | the same |

A **zero divisor** in plain arithmetic is ISO's
`evaluation_error(zero_divisor)` on every spelling, naming the operator:
`eval_(1 // 0, X)` raises `error(evaluation_error(zero_divisor), (//)/2)`, and
so do `'is'` and the ISO comparisons (`'=:='`, `'<'`, ...). A bare
Python-semantics operator raises it too, never a raw Python
`ZeroDivisionError`: it is a logic-level error that `catch/3` sees.

A **constraint** (`==`, `!=`, `<`, ... — CLP(ℤ)'s `#=` family) is a relation,
and over an expression with no value it has no solutions: `X == 1 // 0`
**fails**, as in Scryer, in every goal order (`X == 1 // Y, Y is 0` fails too),
and a divisor that becomes 0 during a search fails that branch.

Inside `++(...)` the code is plain Python and every operator is Python's,
exceptions included.

## Comparison and unification

These spellings already differ from Python in today's syntax: a clause body
is logic, not Python.

| Spelling | Bare, today's syntax | Quoted: ISO / Scryer meaning |
|---|---|---|
| `==` | arithmetic equality posted as a constraint ([CLP(ℤ)](constraints.md), CLP(ℚ), CLP(ℝ)): Prolog's `#=` | `'=='(A, B)`: structural identity in the standard order of terms |
| `!=` | arithmetic disequality constraint: `#\=` | (ISO spells it `'=\\='` for arithmetic, `'\\=='` structurally) |
| `<` `>` `<=` `>=` | arithmetic ordering constraints: `#<` `#>` `#=<` `#>=`; ground dates, times and strings order too | `'<'`, `'>'`, `'=<'`, `'>='`: ISO arithmetic comparison, both sides evaluated (ISO spells `=<`, never `<=`) |
| `is` | **unification**, no evaluation: `X is 1 + 2` binds X to the term `1 + 2` | `'is'(X, E)`: ISO `is/2`, evaluates E |
| `=` | not a goal (Python assignment is a syntax error in a clause body) | `'='(A, B)`: unification |

A non-arithmetic term in an arithmetic constraint raises Scryer's clpz error
`domain_error(clpz_expression, T)`: `X == foo(1)` raises
`error(domain_error(clpz_expression, foo(1)), (==)/2)`.

## Writing a quoted arithmetic cell

The functors of the evaluable table (`+ - * / // div mod ** ^ rdiv rem`,
unary `-` and `+`, `abs min max sign gcd`, the rounding functors `truncate
round ceiling floor`, `float float_integer_part float_fractional_part`,
`sqrt sin cos tan asin acos atan atan2 exp log`, the bitwise `>> << /\ \/ \
xor`, and the constants `pi` and `e`; see [Arithmetic](arithmetic.md)) are
builtins: they are in scope in every module, strict or not, with no
declaration, so `rdiv(7, 2)`, `'//'(A, B)` and `'^'(2, 3)` are written as they
are in Prolog. As data, in a fact or a clause head, they are ordinary terms
(`f(rdiv(1, 2))` holds the term `rdiv(1, 2)`); they are evaluated only where
arithmetic is (`'is'`, `eval_`, a comparison, a constraint). A module's own
declaration of the same spelling answers first, with its usual arity checks.

```clausal
half_toward_zero(N, H) <- 'is'(H, '//'(N, 2))

test("toward zero") <- half_toward_zero(-7, -3)
test("bare floors") <- (eval_(-7 // 2, X), X == -4)
```

See [Arithmetic](arithmetic.md) for the evaluable table and `eval_/2`.
