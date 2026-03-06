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

Logic variable identifiers begin with a single underscore and must not end with one:

```python
_X, _Head, _rest   # logic variables
```

A single `_` is the anonymous variable — it never stores a value, and unification against it always succeeds (matching Python's existing convention).

Logic variables are not declared; they come into existence by appearing in logical context. They work differently from Python variables: they can be unbound, and their bindings are undone on backtracking. This difference warrants a clear visual marker.

Why underscore-prefix rather than titlecase (the Prolog convention)?
- Python programmers associate titlecase with class names — static, global, noun-like. This is actually close to how atoms behave, not variables.
- Underscore-prefix is a well-known Python convention signalling "internal/special".
- There are no existing Python names that start with `_` and are used as variables in normal code, so there is no ambiguity.

---

## Atoms

Inside a logical term:
- identifiers in `TitleCase` are atoms
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
_X is 42,
_X is _Y,
_X is not _Y,   # disunification
```

Why `is` rather than `=`?
- `=` is Python's assignment operator and cannot appear in expressions
- `is` expresses the same concept in English — two things being the same — and Python programmers understand it
- Standard Prolog uses `is` for arithmetic evaluation; this is a deliberate departure, because we want arithmetic to read naturally as constraint logic (see below)

Note: `not _X is _Y` means "unification fails" with bindings discarded; `_X is not _Y` means disunification (a constraint that the two must never unify).

---

## Horn clauses

```python
Head <- Body,
```

The `<-` operator denotes a Horn clause (rule). It will never be added to Python's expression grammar because it conflicts with `x < -y` (less-than applied to a negated value) — but only when there is no surrounding whitespace. With whitespace, it is unambiguous and parseable.

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
[]           # empty list (singleton)
[a, 1, _X]  # a simple list
[_First, *_Rest]             # head/tail decomposition
[*_Before, _Pivot, *_After]  # multiple spread patterns
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
goal(_A, _B),            # compound goal
_A.goal(_B),             # equivalent infix form (syntactic sugar)
_A .goal,                # postfix form of goal(_A)
not goal,                # negation as failure
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

Logic lambdas use Python's `lambda` syntax. Variables that escape the lambda (shared with outer scope) are declared with `in`:

```python
_Y in (lambda _X: _Y is -_X),
map(_Y in (lambda _X: _Y is -_X), [1, 2, 3]),
```

Inside a lambda, parameters and locally-created logic variables are local. Variables that need to be shared with the outer scope are named with `in`. This mirrors Python's closure semantics without requiring explicit `nonlocal` declarations.

---

## Constraint logic programming

Arithmetic operators inside a constraint domain imply constraints, not evaluation. The domain is applied using the `--` escape:

```python
(--clpz)(
    _X < 43,
    42 <= _X,
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

3. **Logic variables must be visually distinct.** They are declared implicitly, work differently from Python names, and their bindings are reverted on backtracking. A clear syntactic marker (underscore prefix) avoids confusion without requiring explicit `declare` statements.

The escape mechanisms (`--`, `++`) cover all cases where interop is genuinely needed. Explicit is better than implicit.

---

## Python functions as predicates

Any Python function that contains logical terms is treated as a predicate. Python code within the body becomes embedded and backtrackable. An implicit `backtracking` flag allows cleanup on backtrack:

```python
def head(_Arg1, _Arg2):
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
# Variables
_X, _head, _rest           # logic variables
_                          # anonymous variable (always unifies, stores nothing)

# Atoms
Atom, 'an atom', '+'       # atoms (titlecase or quoted string)
--python_obj               # any Python object used as an atom

# Lists
[]                         # empty list
[a, 1, _X]                 # simple list
[_First, *_Rest]           # head/tail

# Strings
u"hello"                   # list of character atoms

# Unification
_X is _Y,                  # unify
_X is not _Y,              # disunify

# Rules and facts
Head <- Body,              # Horn clause
Fact,                      # fact (trivially true)
Rule > ListDescription,    # DCG rule

# Goals
goal(_A, _B),              # compound goal
_A.goal(_B),               # infix sugar
not goal,                  # negation as failure
+ goal,                    # immediate goal
- term,                    # retract

# Module qualification
module/(Terms),

# Escaping
--python_expr              # Python inside logic term
++logic_term               # logic term inside Python expression
~~python_expr              # capture as AST node

# Constraint domains
(--clpz)(_X > 0, _X < 10),

# Lambdas
_Y in (lambda _X: _Y is -_X)
```
