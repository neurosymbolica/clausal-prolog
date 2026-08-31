# Prolog `catch/3` reverse-translates to `catch_error/3`, which doesn't exist

**Filed** 2026-08-01, flagged by roborev (job 271 on `ae703f04`) and verified.
**Status:** reproduced, not fixed. Pre-existing dialect-map defect; `ae703f04`
was merely the first commit to exercise it and bake the output into a golden.

## The behaviour

The reverse (Prolog→clausal) dialect map is name-only with no arity awareness
(`prolog_dialect.py`: `"catch_error": {"iso": "catch"}`), so Prolog `catch/3`
comes back as clausal `catch_error/3`. But the compiler's `catch_error`
metacall pattern takes exactly 2 args (`terms_to_goalop.py`, `args=[goal_arg,
error_var]`); 3-arg exception handling is `catch/3` / `catch_recover/3`. The
translated source would compile as an ordinary call to an undefined
`catch_error/3` predicate, not as exception handling.

Baked instance: `tests/fixtures/prolog_golden/iso_unification.clausal:67`
pins `catch_error((X != a, False), _, True)` — **that golden line is the bug's
output, not intentional round-trip design**. The full round-trip conformity
gate only stays green because the third leg maps the name straight back to
`catch`.

## Likely shape of the fix

Arity-aware reverse mapping: Prolog `catch/3` → clausal `catch/3` (and
`catch_error` reserved for the 2-arg form). Regenerate the reverse goldens
after — the iso_unification one above should then read
`catch((X != a, False), _, True)`, matching the hand-written conformity
fixture. Related but separate: the translator-fidelity divergence noted in
`ae703f04` (`X != a` → `X \== a` maps arithmetic-with-type-error semantics to
structural-success semantics; `==` has diverged the same way since A12-F002).

## Repro

`python -m clausal.tools.prolog_to_clausal
tests/fixtures/prolog_golden/iso_unification.pl` — see line 67 of the output.
Verified against clone main 2026-08-01 (post `ae703f04`).
