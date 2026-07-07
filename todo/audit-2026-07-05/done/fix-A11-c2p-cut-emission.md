# fix(A11-F036): clausal_to_prolog exports Cut() as !

`BUILTIN_NAME_MAP["Cut"] = {"iso": "!"}` (prolog_dialect.py:258) +
zero-arity compound emission (clausal_to_prolog.py:114-118): `P() <- (Q(),
Cut())` → `p :- q, !.` — Clausal has no Cut predicate (per the A10-F001
investigation), yet the exporter emits the one construct the design forbids.
Combined with A10-F001, a .pl-with-cut → .clausal → .pl pipeline launders cut
through "cut-free" Clausal.

**Fix**: drop the "Cut" map entry and reject unknown control names arriving
from source in `_convert_call` — do it in the same change as
fix-A10-pl-cut-emitted-as-dead-goal.md.

**Test**: test_F036_no_cut_emission (xfail).
