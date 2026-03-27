# Keyword Predicates

Keyword predicates let you work with named fields in terms — inspecting which
fields are bound, copying terms with overrides, and reflecting on predicate
signatures. They use Python's native keyword argument syntax.

---

## Quick Example

```clausal
# skip
point(1, 2, 3),

Test("vary") <- (
    Vary({"y": 99}, point(1, 2, 3), RESULT),
    RESULT == point(1, 99, 3)
)
```

---

## Partial Terms & Keyword Syntax

When you call a predicate with fewer arguments than it has fields, missing
fields are filled with fresh logic variables (partial terms):

```python
from my_module import point

p = point(x=10)        # point(10, Var(), Var())
p = point(y=20, z=30)  # point(Var(), 20, 30)
```

This is Python's native keyword syntax — no special Clausal syntax needed. See [Syntax](syntax.md) for the full language reference.

---

## Predicates

### Vary/3

`Vary(Overrides, Term, NewTerm)` — copy a term, replacing specified fields with
new values. `Overrides` is a Python dict mapping field names to new values.

```clausal
# skip
point(1, 2, 3),

Test("change one field") <- (
    Vary({"x": 100}, point(1, 2, 3), R),
    R == point(100, 2, 3)
),

Test("change multiple") <- (
    Vary({"x": 10, "z": 30}, point(1, 2, 3), R),
    R == point(10, 2, 30)
)
```

Works for both predicate-class terms and KWTerms.

### Extend/3

`Extend(Additions, Term, NewTerm)` — copy a KWTerm with additional fields.
Only works with open-world KWTerms (not fixed-schema predicate classes).

Raises an error if you try to override an existing key — use `Vary` for that.

### UnboundKeys/2

`UnboundKeys(Term, Keys)` — list the field names that are still unbound
(contain logic variables).

```clausal
# skip
point(1, 2, 3),

Test("unbound") <- (
    UnboundKeys(point(1, Y, Z), KEYS),
    In("y", KEYS),
    In("z", KEYS),
    Length(KEYS, 2)
),

Test("fully bound") <- UnboundKeys(point(1, 2, 3), [])
```

### Signature/3

`Signature(FunctorName, Arity, Names)` — reflect the registered signature of a
predicate. Given a functor name and arity, unifies `Names` with the tuple of
field names.

```clausal
# skip
point(1, 2, 3),

Test("signature") <- (
    Signature("point", 3, NAMES),
    NAMES == ("x", "y", "z")
)
```

This is a database-dependent operation — the predicate must have been defined
(with a signature) before `Signature` is called.

---

## Patterns & Recipes

### Default values via Vary

```clausal
# skip
with_defaults(TERM, RESULT) <- (
    Vary({"color": "black", "size": 12}, TERM, RESULT)
)
```

### Inspect which fields need filling

```clausal
# skip
needs_input(TERM) <- (
    UnboundKeys(TERM, KEYS),
    Length(KEYS, N),
    N > 0
)
```

### Reflect on predicate structure

```clausal
# skip
describe_predicate(NAME, ARITY) <- (
    Signature(NAME, ARITY, FIELD_NAMES),
    Writeln(f"Predicate {NAME}/{ARITY}"),
    Writeln(f"Fields: {FIELD_NAMES}")
)
```

---

## Gotchas

- **`Extend` is for KWTerms only** — predicate classes have fixed schemas and
  cannot grow new fields. Use `Vary` to change existing fields.
- **`Extend` does not override** — it raises an error if a key already exists.
  Use `Vary` for updates.
- **`Signature` requires the predicate to be registered** — if you call it
  before the predicate is defined (e.g., in a different module that hasn't been
  imported), it will fail.
- **Field names are strings** — override dicts use string keys like
  `{"x": 10}`, not variable names.

---

*See also: [Predicates](predicates.md) — defining predicate structures,
[Term Inspection](term_inspection.md) — Functor, Arg, Unpack for generic term
analysis, [Dicts & Sets](dicts_sets.md) — DictTerm for general key-value data.*
