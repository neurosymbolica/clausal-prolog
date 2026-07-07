# fix(A09-F027): functor/3 & unpack/2 non-atom functor handling (repr-strings, no roundtrip)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F027
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F027_functor_numeric_roundtrip, ::test_F027_unpack_numeric_functor (xfail — flip to pass)

## Bug

- `_functor_name_py` (_helpers.py:44-45) returns `repr(term)` for numbers/
  bool/None → `functor(3,N,A)` gives N="3" (str). ISO: N=3 (the constant
  itself). Roundtrip broken: `functor(T,"3",0)` → T="3" ≠ 3. (C twin in
  _variables.c must match.)
- Construction: `functor(T, f(1), 2)` builds functor string "f(1)"
  (inspection.py:202 `str(name_val)`); `unpack(T,[3,1,2])` silently builds
  `Compound("3",(1,2))` (inspection.py:292). ISO raises type_error(atomic/
  atom, …).

## Fix direction

Inspection: return the constant itself for atomic terms (arity 0) — N unifies
with 3, roundtrips. Construction: require an atom-shaped name (str /
zero-arity PredicateMeta) when arity > 0; else typed error or failure per
A09-D002. Update the C `_functor_name` twin in the same change.

## Acceptance

- Both xfails pass; existing functor/unpack tests (Compound/KWTerm/list/str
  cons semantics) stay green.
