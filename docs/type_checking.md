# Type Checking

Clausal provides predicates for testing the type of a term at runtime. These
succeed or fail — they never bind variables.

---

## Quick Example

```clausal
# skip
describe(X, "variable")  <- var(X),
describe(X, "integer")   <- (nonvar(X), integer(X)),
describe(X, "string")    <- (nonvar(X), is_str(X)),
describe(X, "compound")  <- (nonvar(X), compound(X)),
describe(X, "other")     <- nonvar(X)
```

---

## Variable Tests

### var/1

`var(X)` — succeeds if `X` is an unbound logic variable.

```clausal
Test("unbound") <- var(X)
Test("bound fails") <- (not var(42))
```

### nonvar/1

`nonvar(X)` — succeeds if `X` is *not* an unbound variable. The complement of
`var`.

```clausal
Test("number") <- nonvar(42)
Test("string") <- nonvar("hello")
Test("list") <- nonvar([1, 2])
Test("unbound") <- (not nonvar(X))
```

---

## Atomic Type Tests

### atom/1

`atom(X)` — succeeds if `X` is a declared atom (a zero-arity PredicateMeta
class). Atoms are created by `-private([red])` or `-module(m, [red])` directives.

```clausal
-private([red, blue])

Test("declared atom") <- atom(red)
Test("string is not atom") <- (not atom("hello"))
Test("int is not atom") <- (not atom(42))
```

### is_str/1

`is_str(X)` — succeeds if `X` is a Python string. Does not match declared atoms.

```clausal
Test("str") <- is_str("hello")
Test("not str") <- (not is_str(42))
```

### integer/1

`integer(X)` — succeeds if `X` is an integer. Booleans are excluded (even though
Python's `bool` is a subclass of `int`).

```clausal
Test("int") <- integer(42)
Test("not float") <- (not integer(3.14))
Test("not bool") <- (not integer(True))
```

### float_/1

`float_(X)` — succeeds if `X` is a float.

```clausal
Test("float") <- float_(3.14)
Test("not int") <- (not float_(42))
```

### number/1

`number(X)` — succeeds if `X` is an int or float (but not bool).

```clausal
Test("int") <- number(42)
Test("float") <- number(3.14)
Test("not bool") <- (not number(True))
Test("not str") <- (not number("42"))
```

---

## Structural Tests

### compound/1

`compound(X)` — succeeds if `X` is a compound term with arity > 0. This
includes predicate instances, `Compound` terms, and `KWTerm` values.

```clausal
point(1, 2, 3),

Test("compound") <- compound(point(1, 2, 3))
```

### callable_/1

`callable_(X)` — succeeds if `X` is an atom (declared or string) or a
compound term. in_ Prolog terms, something that could appear as a goal.

```clausal
-private([red])

Test("declared atom") <- callable_(red)
Test("string") <- callable_("hello")
Test("not int") <- (not callable_(42))
```

### is_list/1

`is_list(X)` — succeeds if `X` is a Python list.

```clausal
Test("list") <- is_list([1, 2, 3])
Test("empty") <- is_list([])
Test("not str") <- (not is_list("hello"))
```

### is_chars/1

`is_chars(X)` — succeeds if `X` is a character sequence: either a string or a
list. Use this when you want to accept both strings and lists uniformly.

```clausal
Test("string") <- is_chars("hello")
Test("list") <- is_chars([1, 2, 3])
Test("not int") <- (not is_chars(42))
```

| Predicate | Strings | Lists | Purpose |
|-----------|---------|-------|---------|
| `is_list/1` | Fails | Succeeds | Exact type: Python list? |
| `is_str/1` | Succeeds | Fails | Exact type: Python str? |
| `is_chars/1` | Succeeds | Succeeds | union: character sequence? |

See [Strings as Lists](strings_as_lists.md) for the full story on string/list
interchangeability.

---

## Groundness

### ground/1

`ground(X)` — succeeds if `X` contains no unbound logic variables, anywhere
in its structure. Recursively checks lists, compound terms, and predicate
fields.

```clausal
Test("ground int") <- ground(42)
Test("ground list") <- ground([1, 2, 3])
Test("unbound fails") <- (not ground([1, X, 3]))
```

This is useful as a guard before [arithmetic](arithmetic.md) or [I/O](io.md) operations that require all
values to be determined:

```clausal
safe_print(X) <- (ground(X), writeln(X))
```

---

## Patterns & Recipes

### Type-dispatched processing

```clausal
process(X, R) <- (integer(X),    R == X * 2)
process(X, R) <- (is_str(X),    R is f"got: {X}")
process(X, R) <- (is_list(X),   length(X, R))
process(X, R) <- (var(X),    R == "unknown")
```

### Safe arithmetic guard

```clausal
safe_add(X, Y, Z) <- (
    number(X), number(Y),
    Z == X + Y
)
```

---

## Gotchas

- **`integer` excludes booleans** — Python's `True`/`False` are `int` subclasses
  but `integer(True)` fails. Use `nonvar` if you want to accept any non-variable.
- **`var` tests the current binding** — if `X` was unified earlier in the
  clause, `var(X)` will fail even though `X` started as a variable.
- **`is_list` checks for Python lists** — it does not recognize cons-cell chains
  (Clausal uses native Python lists, so this is rarely an issue).
- **Order matters** — put `var` checks first in multi-clause predicates,
  since they match the broadest case.

---

*See also: [Term Inspection](term_inspection.md) — decompose terms with functor,
arg, unpack; [Arithmetic](arithmetic.md) — number guards before computation.*
