# Type Checking

Clausal provides predicates for testing the type of a term at runtime. These
succeed or fail — they never bind variables.

---

## Quick Example

```clausal
# skip
describe(X, "variable")  <- IsVar(X),
describe(X, "integer")   <- (IsBound(X), IsInt(X)),
describe(X, "string")    <- (IsBound(X), IsStr(X)),
describe(X, "compound")  <- (IsBound(X), IsCompound(X)),
describe(X, "other")     <- IsBound(X)
```

---

## Variable Tests

### IsVar/1

`IsVar(X)` — succeeds if `X` is an unbound logic variable.

```clausal
Test("unbound") <- IsVar(X)
Test("bound fails") <- (not IsVar(42))
```

### IsBound/1

`IsBound(X)` — succeeds if `X` is *not* an unbound variable. The complement of
`IsVar`.

```clausal
Test("number") <- IsBound(42)
Test("string") <- IsBound("hello")
Test("list") <- IsBound([1, 2])
Test("unbound") <- (not IsBound(X))
```

---

## Atomic Type Tests

### IsAtom/1

`IsAtom(X)` — succeeds if `X` is a declared atom (a zero-arity PredicateMeta
class). Atoms are created by `-private([red])` or `-module(m, [red])` directives.

```clausal
-private([red, blue])

Test("declared atom") <- IsAtom(red)
Test("string is not atom") <- (not IsAtom("hello"))
Test("int is not atom") <- (not IsAtom(42))
```

### IsStr/1

`IsStr(X)` — succeeds if `X` is a Python string. Does not match declared atoms.

```clausal
Test("str") <- IsStr("hello")
Test("not str") <- (not IsStr(42))
```

### IsInt/1

`IsInt(X)` — succeeds if `X` is an integer. Booleans are excluded (even though
Python's `bool` is a subclass of `int`).

```clausal
Test("int") <- IsInt(42)
Test("not float") <- (not IsInt(3.14))
Test("not bool") <- (not IsInt(True))
```

### IsFloat/1

`IsFloat(X)` — succeeds if `X` is a float.

```clausal
Test("float") <- IsFloat(3.14)
Test("not int") <- (not IsFloat(42))
```

### IsNumber/1

`IsNumber(X)` — succeeds if `X` is an int or float (but not bool).

```clausal
Test("int") <- IsNumber(42)
Test("float") <- IsNumber(3.14)
Test("not bool") <- (not IsNumber(True))
Test("not str") <- (not IsNumber("42"))
```

---

## Structural Tests

### IsCompound/1

`IsCompound(X)` — succeeds if `X` is a compound term with arity > 0. This
includes predicate instances, `Compound` terms, and `KWTerm` values.

```clausal
point(1, 2, 3),

Test("compound") <- IsCompound(point(1, 2, 3))
```

### IsCallable/1

`IsCallable(X)` — succeeds if `X` is an atom (declared or string) or a
compound term. In Prolog terms, something that could appear as a goal.

```clausal
-private([red])

Test("declared atom") <- IsCallable(red)
Test("string") <- IsCallable("hello")
Test("not int") <- (not IsCallable(42))
```

### IsList/1

`IsList(X)` — succeeds if `X` is a Python list.

```clausal
Test("list") <- IsList([1, 2, 3])
Test("empty") <- IsList([])
Test("not str") <- (not IsList("hello"))
```

### IsChars/1

`IsChars(X)` — succeeds if `X` is a character sequence: either a string or a
list. Use this when you want to accept both strings and lists uniformly.

```clausal
Test("string") <- IsChars("hello")
Test("list") <- IsChars([1, 2, 3])
Test("not int") <- (not IsChars(42))
```

| Predicate | Strings | Lists | Purpose |
|-----------|---------|-------|---------|
| `IsList/1` | Fails | Succeeds | Exact type: Python list? |
| `IsStr/1` | Succeeds | Fails | Exact type: Python str? |
| `IsChars/1` | Succeeds | Succeeds | Union: character sequence? |

See [Strings as Lists](strings_as_lists.md) for the full story on string/list
interchangeability.

---

## Groundness

### IsGround/1

`IsGround(X)` — succeeds if `X` contains no unbound logic variables, anywhere
in its structure. Recursively checks lists, compound terms, and predicate
fields.

```clausal
Test("ground int") <- IsGround(42)
Test("ground list") <- IsGround([1, 2, 3])
Test("unbound fails") <- (not IsGround([1, X, 3]))
```

This is useful as a guard before [arithmetic](arithmetic.md) or [I/O](io.md) operations that require all
values to be determined:

```clausal
safe_print(X) <- (IsGround(X), Writeln(X))
```

---

## Patterns & Recipes

### Type-dispatched processing

```clausal
process(X, R) <- (IsInt(X),    R == X * 2)
process(X, R) <- (IsStr(X),    R is f"got: {X}")
process(X, R) <- (IsList(X),   Length(X, R))
process(X, R) <- (IsVar(X),    R == "unknown")
```

### Safe arithmetic guard

```clausal
safe_add(X, Y, Z) <- (
    IsNumber(X), IsNumber(Y),
    Z == X + Y
)
```

---

## Gotchas

- **`IsInt` excludes booleans** — Python's `True`/`False` are `int` subclasses
  but `IsInt(True)` fails. Use `IsBound` if you want to accept any non-variable.
- **`IsVar` tests the current binding** — if `X` was unified earlier in the
  clause, `IsVar(X)` will fail even though `X` started as a variable.
- **`IsList` checks for Python lists** — it does not recognize cons-cell chains
  (Clausal uses native Python lists, so this is rarely an issue).
- **Order matters** — put `IsVar` checks first in multi-clause predicates,
  since they match the broadest case.

---

*See also: [Term Inspection](term_inspection.md) — decompose terms with Functor,
Arg, Unpack; [Arithmetic](arithmetic.md) — IsNumber guards before computation.*
