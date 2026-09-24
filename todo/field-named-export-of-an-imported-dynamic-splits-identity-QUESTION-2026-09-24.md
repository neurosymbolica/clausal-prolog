# DECISION NEEDED: field-named export beside -import_from of a -dynamic predicate

Companion to `todo/field-named-export-of-an-imported-dynamic-splits-identity-2026-09-24.md`
(filed on `feat/drop-vocabulary-implements-2026-09-24`, not on main yet;
separate file so the two branches do not add/add-conflict). Any fix lands in
`compiler_v2`'s declaration/import processing (step 3d/4), which that branch
is changing -- so not attempted here.

## Reproduced on main a5c4fab8 (2026-09-24) -- pre-existing, not the drop

```
# rx_field.clausal
-module(rx_field, [fnm_verdict(STATUS, CITATIONS), rx_add(S), rx_chk(R)])
-import_from(tests.fixtures.fnmismatch_schema, [fnm_verdict])
rx_add(S) <- assertz(fnm_verdict(S, []))
rx_chk(R) <- fnm_verdict(R, C_UNUSED)

# rx_indicator.clausal: identical except the export entry is fnm_verdict/2
```
```
                         binding                           rx_add(ok); rx_chk   schema's fnm_verdict
rx_field       'fnm_verdict' (the ATOM)                          []                  []    <- write lost, no error
rx_indicator   <Predicate fnm_verdict/2, 0 clause(s)>            ['ok']              ['ok']
```

## Candidate behaviours

**A -- the import wins** (as it already does against a DEFINING exporter,
`impord_declare_then_import`): the field-named entry is read as a re-export
of the imported predicate; its field names only document it.
```
rx_field       <Predicate fnm_verdict/2>   ['ok']   ['ok']
```

**B -- load error** naming both lines:
```
SyntaxError: rx_field declares fnm_verdict(STATUS, CITATIONS) (no clauses: a
DATA functor) and -import_from's the PREDICATE fnm_verdict/2 from
tests.fixtures.fnmismatch_schema -- one name, two meanings.
  -> export it as fnm_verdict/2 to re-export the predicate, or drop the import.
```

Recommendation: A, for consistency with the defining-exporter case (and the
`/2` spelling already behaves as A). Either way the silent split goes.
