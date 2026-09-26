# `-dynamic`/arity-only declarations are invisible to `field_names_for` arm 3

**Found by:** the W4b-1 completeness census (`tools/w4b1_census`, deleted
2026-09-26 with the PredicateMeta class it measured; in the git history at
8b8135f0^), fix round 1,
2026-09-22. Not a defect in the census — the census did exactly its job by
surfacing it. Do not fix here; W4b-2 owns it.

## The measurement

A `-dynamic(functor/arity)` directive (and, separately, a plain `name/arity`
entry with no field list in a `-module(...)` export header, e.g.
`-module(gate_vocab, [gv_free/1, ...])`) declares an **arity**, never field
names. Measured directly, two independent cases:

```
-dynamic(dfact/3)                    (tests/test_predicate_arity_mismatch_diagnostic.py:613)

cls._row is None?              False      <- the row IS bound (not detached)
row.detached                   False
db.signature_for('dfact', 3)   None
db.declared_fields_by_name     None
field_names_for(cls)        -> ('arg_0', 'arg_1', 'arg_2')   # arm 2, synthesized placeholders
field_names_for('dfact', arity=3, db=<the real module db>)
                             -> None                          # arm 3
```

```
-module(gate_vocab, [gv_free/1, gv_owned(NAME)])   (tests/fixtures/gate_vocab.clausal)
# gv_free/1 names an ARITY only; gv_owned(NAME) alongside it DOES name a field.

cls._row is None?              True       <- never bound at all (no -dynamic, no clause)
db.declared_fields_by_name('gv_free')   None   (checked against the REAL module db, via
                                                 a sibling predicate's bound row -- not derived
                                                 from gv_free's own class)
db.signature_for('gv_free', 1)          None
field_names_for(cls)        -> ('arg_0',)   # arm 2, synthesized placeholder
```

No signature is ever registered for either — not on the class's own row,
and not on the module's real `Database` either (checked directly, via a
sibling bound predicate's `db`, not derived from the unbound class). This
is **not** a shadow-probe artifact: the declaration genuinely has no field
names anywhere, at any point, no matter which correctly-obtained `db` asks.

Contrast with a **field-named** clause-free declaration —
`-private([zonkish(X, Y)])` (`tests/predmeta_p1/test_p1_sites_rerouted.py`)
— which DOES register `('X', 'Y')` on the real module db
(`db.declared_fields_by_name('zonkish') == ('X', 'Y')`), just not
reachable from `zonkish`'s own class (`cls._row` there is a *detached*
private row, not the real module's). That case IS a probe-derivation
artifact, genuinely distinct from this one.  The census README's residue
section (deleted with the tool; `git show 8b8135f0^:tools/w4b1_census/README.md`)
told the two apart, and its point is carried here:

- **This todo (a real declaredness gap).** `-dynamic(functor/arity)` and a
  bare `name/arity` export entry declare an ARITY, never field names.
  Measured on the real module db for `-dynamic(dfact/3)` and
  `-module(gate_vocab, [gv_free/1, ...])`: `db.signature_for` and
  `db.declared_fields_by_name` both `None`, while the class answered
  synthesized `('arg_0', ...)`.  No signature was registered on any db.
- **Not this todo (a probe artifact).** A field-NAMED clause-free
  declaration such as `-private([zonkish(X, Y)])` DOES register its names
  on the compiling module's db; the census read `None` only because it
  derived the db from the class's detached private row.

## Why it matters

`field_names_for`'s docstring states its contract plainly: it is "first a
**declaredness** reader" — `None` means *not declared*. For an
arity-only declaration, arm 3 answers `None`, which is the WRONG answer:
the predicate IS declared (that's the entire point of `-dynamic`/an
arity-only export entry), just with no field names.

Today this is silent because arm 2 (`cls._fields`, synthesized) still
answers for every caller that has the class in hand. At **W4b-3**, when
`PredicateMeta` and arm 2 are deleted, every declaredness question about a
`-dynamic`-only or arity-only-exported predicate — "is `dfact/3` declared?"
— would get the wrong answer from the one surviving arm.

## Candidate fixes (not decided here — W4b-2's call)

1. **Register a signature for arity-only declarations too**, synthesizing
   the same placeholder names (`arg_0`, `arg_1`, ...) arm 2 already
   produces, at the point `-dynamic`/the export-list entry is processed —
   so arm 3 finds the same synthesized tuple arm 2 would have given.
   Keeps the accessor's contract (`tuple` = declared, arity = `len`)
   intact without changing its shape.
2. **Split the declaredness question off the field-names question.** Have
   "is this declared?" consult `db.declared_kind(functor, arity)` (already
   named as existing, in `implementation_plans/w4b-class-retirement-scope-2026-09-22.md`'s
   W4b-2 section) or row existence directly, and let `field_names_for`
   answer `None` for "declared, no names" as a THIRD state distinguishable
   from "not declared" — which needs a contract change (the doc-string's
   `tuple | None` union would need a third case, or the two questions need
   two separate accessors).

## Scope note

Not limited to `-dynamic`: any arity-only `name/arity` entry in a
`-module(...)` export list has the identical gap (confirmed for
`gv_free/1` above). The fix, whichever shape it takes, should cover both
spellings.
