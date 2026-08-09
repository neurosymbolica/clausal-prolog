# Bug: two arities of one name in one file merge silently, padded with a wildcard

**Reported:** 2026-07-29, found while fixing
[`arity-mismatch-reports-a-missing-trail-argument.md`](done/arity-mismatch-reports-a-missing-trail-argument.md)

---

## Symptom

```clausal
-private([a, b])

foo(a, b),
foo(a),
```

`docs/predicates.md` says: *"Different arities define different predicates:
`foo/1` and `foo/2` are unrelated."*  They are not kept unrelated.  The module
ends up with

```
<Predicate foo/2, 2 clause(s), compiled, locked>
  Clause(head=foo(arg_0=_3, arg_1=_4), body=[Unify(_3, a), Unify(_4, b)])
  Clause(head=foo(arg_0=_5, arg_1=_0), body=[Unify(_5, a)])
```

`foo/1` is gone.  Its fact was absorbed into `foo/2` as `foo(a, _)` — a clause
that matches `foo(a, ANYTHING)`, which the author never wrote and which is not
what `foo(a)` means.  There is no `foo/1` in the database, no warning, and no
error at load.

The mechanism is the term-construction path: `PredicateMeta.__call__` *fills*
missing fields when given too few positional arguments (over-supply raises
`_term_arity_error`; under-supply does not).  That is defensible for building a
partial *term* — `citation(REF)` as an argument to `functor/3` relies on it —
but a clause **head** is not a partial term, and treating it as one silently
rewrites the program.

## Consequences

Both directions are wrong, and which one you get depends on file order:

- the shorter clause is padded and joins the longer predicate (above);
- and a caller that writes `foo(a)` gets the arity refusal added by the sibling
  fix, naming `foo/2` as the only definition — correct about the database, but
  the author is looking at a `foo(a),` clause in the file it says does not
  define `foo/1`.

That second one is the trap: the new diagnostic is *accurate and confusing at
the same time*, because the thing it is describing was already destroyed.

## Requested fix

Refuse at load time.  A clause head whose argument count differs from the class
already bound to that name in this module is not a partial term; it is either a
typo or a genuine second predicate, and Clausal supports the latter only under a
different name.  `_term_arity_error` in `clausal/logic/predicate.py` is the
house pattern for the message and already reports *registered at* / *constructed
at* sites, which is exactly what this needs.

Care needed on:

- **`-dynamic` and `assertz`.** Runtime assertion of a differing arity goes
  through the same `__call__`; decide whether it refuses too (probably yes — the
  padding is no better at runtime) and check `docs/database_ops.md`.
- **The atom-vs-predicate collision.** A 0-arity vocabulary atom imported and
  then defined as an /N predicate is exactly this shape and the corpus relies on
  it — the shape `tests/fixtures/impord_atom_then_pred.clausal` pins; two
  corpus modules rely on it in production. Any
  refusal must exempt the clause-free class, which is what
  `implementation_plans/dict-atom-keys-vs-predicates.md` calls Phenomenon A.
  `PredicateMeta._clause_arity()` (added by the sibling fix) is the existing
  test for "does this class have clauses, and at what arity".
- **Partial term construction must keep working.** `citation(REF)` in argument
  position is legal and used; only *heads* are in scope here.
