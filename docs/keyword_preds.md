# Keyword Predicates

Keyword predicates let you work with named fields in terms — inspecting which
fields are bound, copying terms with overrides, and reflecting on predicate
signatures.

Field names come from the predicate's **declaration**:

```clausal
-private([point(x, y, z)])

point(1, 2, 3),
```

!!! note "The keyword CONSTRUCTION spelling was retired on 2026-09-19"

    A term used to be writable as `point(x=1, y=2, z=3)`, and the first clause
    written that way was what named the fields. A term is built positionally
    now, and a keyword argument in a term or a clause head is a load-time
    error. The spelling had no ISO Prolog reading, and it made a functor's
    field names depend on which of its clauses came first.

    Two keyword spellings are unaffected: a `-directive`'s options
    (`-specialize(solve, p, alias=q)`) and an EDCG hidden argument
    (`p(L, _edcg_counter_in=0)`).

    Everything on this page still works — the builtins address fields by
    NAME, and names now come from the declaration above.

---

## Quick Example

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:quick_example"
```

---

## Partial Terms

A term is never padded: a construction with fewer arguments than the declared
functor has fields is refused, not filled with fresh logic variables.  A field
you want to leave open is written as a variable -- which is what a partial
term is:

```clausal
-private([point(x, y, z)])

p(P) <- (P is point(10, _Y, _Z))        # point(10, _, _)
p(P) <- (P is point(_X, 20, 30))
```

See [Syntax](syntax.md) for the full language reference.

---

## Predicates

### vary/3

`vary(Overrides, Term, NewTerm)` — copy a term, replacing specified fields with
new values. `Overrides` is a Python dict mapping field names to new values.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:vary_examples"
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
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:unbound_keys_examples"
```

### signature/3

`signature(FunctorName, Arity, Names)` — reflect the registered signature of a
predicate. Given a functor name and arity, unifies `Names` with the tuple of
field names.

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_examples.clausal:signature_example"
```

This is a database-dependent operation — the predicate must have been defined
(with a signature) before `signature` is called.

---

## Patterns & Recipes

### Default values via vary

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_sigs.txt:default_values"
```

### Inspect which fields need filling

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_sigs.txt:inspect_fields"
```

### Reflect on predicate structure

```clausal
--8<-- "tests/fixtures/docs/keyword_preds_sigs.txt:reflect_predicate"
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
- **Field names come from the declaration** — `-private([point(x, y, z)])` or
  the `-module` export list. An undeclared predicate's fields are `arg_0`,
  `arg_1`, … , which `vary` and `unbound_keys` will happily use but nobody
  wants to read.

---

*See also: [Predicates](predicates.md) — defining predicate structures,
[Term Inspection](term_inspection.md) — functor, arg, unpack for generic term
analysis, [Dicts & Sets](dicts_sets.md) — DictTerm for general key-value data.*
