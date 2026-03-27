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
    vary({"y": 99}, point(1, 2, 3), RESULT),
    RESULT == point(1, 99, 3)
)
```

---

## Partial Terms & Keyword Syntax

when you call a predicate with fewer arguments than it has fields, missing
fields are filled with fresh logic variables (partial terms):

```python
from my_module import point

p = point(x=10)        # point(10, Var(), Var())
p = point(y=20, z=30)  # point(Var(), 20, 30)
```

This is Python's native keyword syntax — no special Clausal syntax needed. See [Syntax](syntax.md) for the full language reference.

---

## Predicates

### vary/3

`vary(Overrides, Term, NewTerm)` — copy a term, replacing specified fields with
new values. `Overrides` is a Python dict mapping field names to new values.

```clausal
# skip
point(1, 2, 3),

Test("change one field") <- (
    vary({"x": 100}, point(1, 2, 3), R),
    R == point(100, 2, 3)
),

Test("change multiple") <- (
    vary({"x": 10, "z": 30}, point(1, 2, 3), R),
    R == point(10, 2, 30)
)
```

Works for both predicate-class terms and KWTerms.

### extend/3

`extend(Additions, Term, NewTerm)` — copy a KWTerm with additional fields.
Only works with open-world KWTerms (not fixed-schema predicate classes).

Raises an error if you try to override an existing key — use `vary` for that.

### unbound_keys/2

`unbound_keys(Term, Keys)` — list the field names that are still unbound
(contain logic variables).

```clausal
# skip
point(1, 2, 3),

Test("unbound") <- (
    unbound_keys(point(1, Y, Z), KEYS),
    in_("y", KEYS),
    in_("z", KEYS),
    length(KEYS, 2)
),

Test("fully bound") <- unbound_keys(point(1, 2, 3), [])
```

### signature/3

`signature(FunctorName, Arity, Names)` — reflect the registered signature of a
predicate. Given a functor name and arity, unifies `Names` with the tuple of
field names.

```clausal
# skip
point(1, 2, 3),

Test("signature") <- (
    signature("point", 3, NAMES),
    NAMES == ("x", "y", "z")
)
```

This is a database-dependent operation — the predicate must have been defined
(with a signature) before `signature` is called.

---

## Patterns & Recipes

### Default values via vary

```clausal
# skip
with_defaults(TERM, RESULT) <- (
    vary({"color": "black", "size": 12}, TERM, RESULT)
)
```

### Inspect which fields need filling

```clausal
# skip
needs_input(TERM) <- (
    unbound_keys(TERM, KEYS),
    length(KEYS, N),
    N > 0
)
```

### Reflect on predicate structure

```clausal
# skip
describe_predicate(NAME, ARITY) <- (
    signature(NAME, ARITY, FIELD_NAMES),
    writeln(f"Predicate {NAME}/{ARITY}"),
    writeln(f"Fields: {FIELD_NAMES}")
)
```

---

## Gotchas

- **`extend` is for KWTerms only** — predicate classes have fixed schemas and
  cannot grow new fields. Use `vary` to change existing fields.
- **`extend` does not override** — it raises an error if a key already exists.
  Use `vary` for updates.
- **`signature` requires the predicate to be registered** — if you call it
  before the predicate is defined (e.g., in a different module that hasn't been
  imported), it will fail.
- **Field names are strings** — override dicts use string keys like
  `{"x": 10}`, not variable names.

---

*See also: [Predicates](predicates.md) — defining predicate structures,
[Term Inspection](term_inspection.md) — functor, arg, unpack for generic term
analysis, [Dicts & Sets](dicts_sets.md) — DictTerm for general key-value data.*
