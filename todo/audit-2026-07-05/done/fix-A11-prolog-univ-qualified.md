# fix(A11-F033): =.. and Module:Goal emit invalid Clausal; docs promise unpack/2 and lists.in_

`_INFIX_MAP` passes `=..` through verbatim (`T =.. L` — SyntaxError as
Python); `:` has no handling (`lists:member(X,L)` → `:(lists, member(X, L))`,
SyntaxError). iso_prolog_compatibility_report.md:201-238 documents
`X =.. L` → `unpack(X, L)` (the BUILTIN_NAME_MAP even contains "unpack") and
`lists:member(X,L)` → `lists.in_(X, L)`.

**Fix**: implement both documented mappings in prolog_to_clausal.

**Test**: test_F033_univ_and_qualified_emission (xfail).
