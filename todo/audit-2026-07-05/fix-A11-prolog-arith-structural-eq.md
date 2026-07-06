# fix(A11-F032): arithmetic vs structural comparison collapse; docs contradict code

Forward (prolog_to_clausal.py:83-84,316-323): `=:=`→`==` AND `\==`→`!=`,
`==`→`==`. Backward (clausal_to_prolog.py:833-837): `==`→`==` (structural),
`!=`→`\==`. Round trip: `X =:= Y+1` (arithmetic) returns as `X == Y+1`
(structural) — `1+1 =:= 2` true, `1+1 == 2` false. Docs contradict the code
both directions (prolog_translation.md and
iso_prolog_compatibility_report.md:236 say `Y == X*2` → `Y is X*2` and
`Y is X*2` → `Y == X*2`; code emits `==`/`:=`). Also:
`Dialect.string_type` ("string"/"chars"/"atom") is dead configuration — all
dialects emit identical Python-repr strings (a Scryer "abc" char-list
imported as a Python string changes semantics).

**Fix** (A11-D008): context-sensitive compare conversion (arithmetic operands
→ `=:=`/`is` on export; keep a dedicated arith-eq on import); implement or
remove string_type; align the two docs with whatever ships.

**Test**: test_F032_arith_eq_roundtrip (xfail).
