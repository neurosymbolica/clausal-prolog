# investigate(A09-F004/D001): maplist/foldl committed choice loses solutions — for Opus

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F004
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F004_* (xfail)
**Design:** A09-D001 in DESIGN-DECISIONS.md (parked). Recommendation: restore backtracking.

## Problem

maplist/2 (higher_order.py:69-75), maplist/3 (99-107), foldl/4 (180-188) pull
exactly ONE solution per element ("Got first solution — committed choice");
`maplist(pick,[1],[Y]), Y is "b"` with `pick(1,"a"),pick(1,"b")` yields
nothing (SWI: Y="b"). This is an implicit cut in a cut-free language; docs
only document commitment for include/exclude ("Lambdas are committed-choice").

## Investigation

1. Restoring backtracking means per-element choice points inside a
   trampoline builtin — re-yield into the element's StepGenerator on redo
   (pattern exists in `in_`'s enumerate loop; the difference is nesting N
   generators). Sketch the generator shape; measure cost on det goals (the
   99% case) — a "first try det, keep sg alive only if needed" scheme may
   keep the fast path.
2. Decide the include/exclude family separately (documented commit; keep).
3. Corpus impact: grep rulebases for maplist with nondeterministic goals.
4. If backtracking is rejected (D001 option b): document loudly in
   docs/higher_order.md + lint nondeterministic goals under maplist.
