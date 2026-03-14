# Clausal — Syntax Design

Clausal does not follow ISO Prolog syntax. It uses Python syntax throughout — all clausal code is valid Python, acceptable to the Python parser without modification. No separate parser is needed. This was a fundamental design decision: Python programmers should not have to learn a foreign syntax to use logic programming.

The tradeoffs this creates (mainly around the unification operator and some operators) are documented below, with the reasoning behind each choice.

---

## The key rule

**Expression statements ending in `,` are interpreted as logical terms (facts or goals).**

In standard Python, an expression statement that produces a tuple has no effect whatsoever. This means trailing commas can be used as delimiters without disturbing any existing Python code. It also means logic terms are easy to cut, copy, paste, and indent — they don't require `.` terminators that would conflict with Python's attribute access syntax.

---

## Escape operators

Three double-prefix operators demarcate the boundary between Python and logic code. They must not be split with spaces (e.g. `- -` would be parsed as double negation).

| Operator | Meaning |
|---|---|
| `--expr` | Python expression embedded inside a logic term |
| `++expr` | Logic term embedded inside a Python expression |
| `~~expr` | Capture expression as a `simple_ast` AST node (works anywhere) |

`--` was chosen because:
- it doesn't introduce a new keyword or clobber any identifier
- double negation is rare in Python code (and where it occurs, spacing makes it legible)
- it is visually prominent and quick to type

Example:
```python
# Logic term containing a Python value:
point(--x_coord, --y_coord),

# Python expression containing a logic term:
my_term = ++foo(X, bar(Y))

# Capture Python code as AST without running it:
ast_node = ~~(x + y * z)

# Capture a block of statements as AST:
with ... as block:
    result = f(x)
    return result
```

---

## Logic variables

Two conventions are recognised:

**Trailing single underscore** — any identifier whose last character is `_`, excluding dunders (`__`) and the bare anonymous variable `_`:

```python
X_, HEAD_, rest_   # logic variables (trailing-underscore style)
```

**ALL-CAPS** — any identifier where every cased character is uppercase and there is at least one cased character (underscores and digits are allowed inside):

```python
X, HEAD, REST, N1, MAX_OF   # logic variables (ALL-CAPS style)
```

Both styles may be used in the same file. ALL-CAPS is the preferred style for new code; trailing-underscore remains valid.

A single `_` is the anonymous variable — it never stores a value, and unification against it always succeeds (matching Python's existing convention).

Logic variables are not declared; they come into existence by appearing in logical context. They work differently from Python variables: they can be unbound, and their bindings are undone on backtracking. This difference warrants a clear visual marker.

Why not titlecase (the Prolog convention)?
- Python programmers associate titlecase with class names — static, global, noun-like. This is actually close to how atoms behave, not variables.
- ALL-CAPS is used in many languages for constants and distinguished names; here it marks the variable role in the logic sense.
- Single letters like `X`, `Y`, `N` are universally understood as logic variables from mathematics.

---

## Atoms

Inside a logical term:
- identifiers in `TitleCase` or `lowercase` that are not logic variable names are atoms
- string literals are atoms (except those prefixed with `u"..."`)

```python
# These are equivalent:
Atom is 'Atom',
(x is not 2) is 'is not'(x, 2),
```

Atoms that conflict with Python built-ins or that use non-identifier characters are written as strings: `'+'`, `'is not'`, `'max'`.

---

## Unification

Unification is written with `is`:

```python
X is 42,
X is Y,
X is not Y,   # disequality constraint (dif/2)
```

Why `is` rather than `=`?
- `=` is Python's assignment operator and cannot appear in expressions
- `is` expresses the same concept in English — two things being the same — and Python programmers understand it

`X is not Y` posts a disequality constraint (`dif/2`): X and Y must end up with different values. This is lazily checked — the constraint is re-evaluated each time either variable gets bound. If they become equal, the constraint fails and the search backtracks. If they remain different, the constraint is satisfied and dropped. See [constraints.md](constraints.md) for details.

`not (X is Y)` is the immediate check (Prolog `\=/2`): it fails if X and Y *can* unify right now, regardless of future bindings. Use this when you want point-in-time semantics.

The corresponding AST node is `Unify(left, right)`. Disequality is `DoesNotUnify(left, right)`.

---

## Arithmetic binding

To evaluate an arithmetic expression and bind the result to a variable, use the walrus operator `:=`:

```python
fib(N, RESULT) <- (
    N > 1,
    N1 := N - 1,
    N2 := N - 2,
    fib(N1, A),
    fib(N2, B),
    RESULT := A + B
)
```

`N1 := N - 1` evaluates `N - 1` as Python arithmetic and unifies the result with `N1`. This is equivalent to Prolog's `is` operator. No extra parentheses are needed: clause bodies are already inside `(...)`, and `:=`'s RHS is a `test` expression in Python's grammar so it does not consume the comma that follows.

The distinction from `is`:
- `X is Y` — pure structural unification; neither side is evaluated arithmetically
- `(X := expr)` — `expr` is evaluated as arithmetic before unification; `X` should be unbound

The corresponding AST node is `Evaluate(left, right)`. The compiler applies `arith_to_ast_expr` to the right side, producing native Python arithmetic that is evaluated before `unify` is called.

---

## Comparison operators (CLP(FD))

The comparison operators `==`, `!=`, `<`, `>`, `<=`, `>=` are CLP(FD) (Constraint Logic Programming over Finite Domains) operators. They post constraints on integer variables rather than performing immediate checks.

```python
bounded(X) <- (
    in_domain(X, 1, 10)
    and X > 3
    and X < 8
    and label([X])
)
```

When both sides are ground (no unbound Vars), the operators fall back to direct Python comparison — `3 == 3` is True, `3 < 2` is False — so existing ground arithmetic code works unchanged.

When at least one side is an unbound Var, a CLP(FD) constraint is posted:
- `X == 5` narrows X's domain to `{5}` (and binds it)
- `1 <= X` and `X <= 10` constrain X's domain to `[1, 10]`
- `X != 3` removes 3 from X's domain
- `X < Y` narrows X's upper bound and Y's lower bound

| Operator | CLP(FD) meaning |
|---|---|
| `==` | Arithmetic equality constraint |
| `!=` | Arithmetic disequality constraint |
| `<` `>` `<=` `>=` | Comparison constraints (narrow domain bounds) |

The old structural-equality behaviour of `==` is available as the builtin `equivalent(X, Y)`. Use `equivalent` when comparing non-integer terms where CLP(FD) semantics are not appropriate.

See [constraints.md](constraints.md) for the full CLP(FD) design, including domain representation, propagation, and labeling.

---

## Horn clauses

```python
Head <- Body,
```

The `<-` operator denotes a Horn clause (rule). It will never be added to Python's expression grammar because it conflicts with `x < -y` (less-than applied to a negated value) — but only when there is no surrounding whitespace. With whitespace, it is unambiguous and parseable.

### Body style

The body after `<-` must be one of:

- **A single call** — no parentheses needed:
  ```python
  sorted_asc([_]),
  palindrome(XS) <- reverse(XS, XS),
  ```

- **A bare name** — no parentheses needed:
  ```python
  always_true <- true,
  ```

- **Anything else** — parenthesized:
  ```python
  safe_max(X, Y, X) <- (X >= Y),
  fib(N, RESULT) <- (
      N > 1,
      N1 := N - 1,
      N2 := N - 2,
      fib(N1, A),
      fib(N2, B),
      RESULT := A + B
  )
  ```

This rule exists because Python's parser sees `<-` as `<` followed by unary `-`. When the body contains operators (`+`, `<`, `and`, `or`, `not`, etc.), the `-` gets absorbed into the body expression and the AST is silently mangled. Parentheses force Python to treat the body as a single grouped expression, keeping the `-` at the top where the term rewriter can find it. Calls and bare names are safe without parentheses because they bind tighter than unary `-`.

Attempting to write an unparenthesized operator body produces a clear error:

```
SyntaxError: clause body must be parenthesized or a single call:
    write  head <- (body)  or  head <- goal(X)
```

### Conjunction style

Multiple goals in a body are separated by commas, with each goal on its own line:

```python
is_permutation(XS, YS) <- (
    length(XS, N),
    length(YS, N),
    sort(XS, S),
    sort(YS, S)
)
```

Inside sub-expressions like `not (...)` or `... or ...`, use `and` instead of commas — commas inside these would be parsed as Python tuples:

```python
test("fails") <- (not (X is 1 and X is 2)),
test("either") <- (X is 1 or X is 2),
```

Facts (trivially true rules) are written without a body:

```python
parent(tom, bob),
parent(bob, ann),
```

Grammar rules (Definite Clause Grammars):

```python
Rule > ListDescription,
```

---

## Lists

```python
[]               # empty list (singleton)
[a, 1, X]        # a simple list
[FIRST, *REST]   # head/tail decomposition
[*BEFORE, PIVOT, *AFTER]  # multiple spread patterns
```

Partial lists (Prolog `[H|T]` where `T` is a variable) use Python's `*` spread syntax rather than `|`. The empty list is a singleton — unlike Python, two `[]` literals are the same object.

---

## Strings

Strings prefixed with `u""` are lists of character atoms:

```python
u"ABC" is [A, B, C] is ['A', 'B', 'C'],
```

All list operations apply to strings. Plain string literals (without `u`) are atoms.

---

## Compound terms and goals

```python
goal(A, B),            # compound goal
A.goal(B),             # equivalent infix form (syntactic sugar)
A .goal,               # postfix form of goal(A)
not goal,              # negation as failure
```

The infix and postfix forms allow natural English-style reading of predicates that take a "subject" argument.

---

## Immediate goals

```python
+ goal,     # assert/call immediately ('+' distinguishes from a fact)
- term,     # retract term
```

---

## Module qualification

```python
module/(Terms),
```

---

## Lambdas

Lambdas are anonymous clauses — goal closures passed as arguments to higher-order predicates. They use the same `head <- body` arrow syntax as clause definitions:

```python
# One-arg lambda — X_ is a parameter, Result_ is captured
apply(Result_, Val_) <- call_goal((X_ <- (Result_ := X_ + 1)), Val_)

# Two-arg lambda
apply_add(A_, B_, R_) <- call_goal(((X_, Y_) <- (R_ := X_ + Y_)), A_, B_)

# Zero-arg lambda
run_goal(Result_) <- call_goal((() <- (Result_ is 42)))

# Captured variable from enclosing clause
add_z(Z_, R_) <- call_goal((X_ <- (R_ := X_ + Z_)), 10)

# Conjunction body — parenthesize each := subgoal
transform(R_) <- call_goal(((X_, Y_) <- ((T_ := X_ + 1) and (Y_ := T_ * 2))), 5, R_)
```

Parameters are lambda arguments; captured variables share the enclosing clause's `Var` objects. Body-local variables (first appearing inside the lambda) get fresh `Var()` allocations. Lambdas are called via the `call_goal/1,2,3` builtins.

See [lambdas.md](lambdas.md) for the full design, compilation details, and examples.

---

## Constraint logic programming

Arithmetic operators inside a constraint domain imply constraints, not evaluation. The domain is applied using the `--` escape:

```python
(--clpz)(
    X < 43,
    42 <= X,
)
```

Shorthand constraint operators (usable in single goals):

| Operator | Meaning |
|---|---|
| `==+`, `!=+`, `>+`, `<+`, `>=+`, `<=+` | numeric comparison |
| `==~`, `!=~`, `>~`, `<~`, `>=~`, `<=~` | standard order of terms |

Note: `<=` always means less-than-or-equal in constraint context. Implication uses `implies` or the `<-` arrow.

---

## Why not allow free intermingling of Python and logic namespaces?

Three main reasons:

1. **Ambiguity.** It is impossible at compile time to distinguish a Python global from an atom without tracking all imports. Old compiled code could silently become wrong when a new name is imported. With explicit `--` escaping, the boundary is always visible.

2. **Term representation efficiency.** Compound terms are most efficiently represented as instances of generated classes (enabling `match`/`case` to work directly on them). Atoms need to be class objects for structural matching. Allowing arbitrary Python objects as functors requires a boxing wrapper, which is heavier.

3. **Logic variables must be visually distinct.** They are declared implicitly, work differently from Python names, and their bindings are reverted on backtracking. A clear syntactic marker (ALL-CAPS or trailing underscore) avoids confusion without requiring explicit `declare` statements.

The escape mechanisms (`--`, `++`) cover all cases where interop is genuinely needed. Explicit is better than implicit.

---

## Python functions as predicates

Any Python function that contains logical terms is treated as a predicate. Python code within the body becomes embedded and backtrackable. An implicit `backtracking` flag allows cleanup on backtrack:

```python
def head(ARG1, ARG2):
    goal(...),
    if not backtracking:
        # forward path: acquire resource, open file, etc.
        ...
    else:
        # backtrack path: release resource, etc.
        ...
    another_goal(...)
```

This gives a symmetric and concise way to integrate Python side effects with Prolog-style backtracking. The programmer takes responsibility for correctness.

---

## Syntax cheat sheet

```python
# Variables (ALL-CAPS preferred; trailing-underscore also valid)
X, HEAD, REST          # ALL-CAPS logic variables
X_, head_, rest_       # trailing-underscore style (also valid)
_                      # anonymous variable (always unifies, stores nothing)

# Atoms
Atom, 'an atom', '+'   # atoms (titlecase or quoted string)
--python_obj           # any Python object used as an atom

# Lists
[]                     # empty list
[a, 1, X]              # simple list
[FIRST, *REST]         # head/tail

# Strings
u"hello"               # list of character atoms

# Unification
X is Y,                # unify
X is not Y,            # dif constraint (must stay different)
not (X is Y),          # immediate check (don't unify right now)

# Arithmetic
(N := X + 1),          # evaluate RHS, unify with LHS

# CLP(FD) constraints (V2-6)
X == Y,                # arithmetic equality constraint
X != Y,                # arithmetic disequality constraint
X < Y,                 # less-than constraint
X <= Y,                # less-or-equal constraint
in_domain(X, 1, 10),   # post finite domain
all_different([X,Y,Z]), # pairwise disequality
label([X, Y, Z]),      # enumerate solutions (first-fail)
equivalent(X, Y),      # structural equality (old == behavior)

# Rules and facts
Head <- call(X),       # single-call body (no parens needed)
Head <- (Body),        # operator body (parens required)
Fact,                  # fact (trivially true)
Rule > ListDescription,    # DCG rule

# Goals
goal(A, B),            # compound goal
A.goal(B),             # infix sugar
not goal,              # negation as failure
+ goal,                # immediate goal
- term,                # retract

# Module qualification
module/(Terms),

# Escaping
--python_expr          # Python inside logic term
++logic_term           # logic term inside Python expression
~~python_expr          # capture as AST node

# Constraint domains
(--clpz)(X > 0, X < 10),

# Lambdas (anonymous clauses)
call_goal((X_ <- (R_ := X_ + 1)), 5)                            # R_ = 6
call_goal(((X_, Y_) <- (R_ := X_ + Y_)), A_, B_)                # multi-param
```
