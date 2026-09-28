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
| `/` | exact division: `7 / 2` is the rational 7/2 (not Python's float 3.5; [ruled 2026-09-17](arithmetic.md)) | the same: `'/'(7, 2)` is 7/2 | the same |
| `//` | Python floor division: `-7 // 2` is **-4** | ISO integer division, **truncating** toward zero: `'//'(-7, 2)` is **-3**; integers only | Scryer: truncates |
| `div` | (no bare spelling) | ISO floored division: `div(-7, 2)` is -4; integers only | the same |
| `%` | Python modulo, sign of the divisor: `-7 % 2` is 1 | (no quoted `%`; write `mod`) | Python's `%` only inside `++` |
| `mod` | (no bare spelling) | ISO modulo, sign of the divisor: `mod(-7, 2)` is 1; integers only | the same |
| `rem` | (none) | not evaluable in Clausal: `type_error(evaluable, rem/2)` | — |
| `**` | Python power: `2 ** 3` is the **integer 8**; `2 ** -1` is 0.5 | ISO power, always a **float**: `'**'(2, 3)` is **8.0** | Scryer: a float |
| `^` | Python bitwise XOR — as a CLP(B) formula in `sat(X ^ Y)`; not evaluable by `eval_` | ISO integer power: `'^'(2, 3)` is 8; `'^'(2, -1)` is `type_error(float, 2)`; `'^'(1, -1)` is 1 | Scryer: integer power |
| `&` `\|` `~` | Python bitwise AND / OR / NOT — CLP(B) formulas in `sat(...)`; not evaluable by `eval_` (`type_error(evaluable, (&)/2)`) | no ISO operator of these spellings (ISO writes `/\`, `\/`, `\`) | — |
| `<<` `>>` | Python shifts; not evaluable by `eval_` | not in Clausal's evaluable table | — |
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

A quoted operator applied to arguments is a functor construction like any
other, so a module with strict functors must declare it (or use
`-implicit_functors`); a cell built at runtime with `unpack/2` needs no
declaration:

```clausal
-implicit_functors

half_toward_zero(N, H) <- 'is'(H, '//'(N, 2))

test("toward zero") <- half_toward_zero(-7, -3)
test("bare floors") <- (eval_(-7 // 2, X), X == -4)
```

See [Arithmetic](arithmetic.md) for the evaluable table and `eval_/2`.
