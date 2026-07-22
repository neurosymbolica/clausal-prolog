# `is/2` does not unify a pre-bound LHS with the arithmetic result (non-ISO)

**Filed:** 2026-07-21 (query-taxonomy coverage sweep; hit by reach_registration and
clp_hazard while writing query predicates that check a caller-supplied numeric output).

## Confirmed behavior
```clausal
X is 5, X is 2 + 3      %% FAILS in Clausal
X is 5, X == 2 + 3      %% succeeds (== evaluates the RHS and compares)
Y is 2 + 3, Y == 5      %% succeeds (is binds an unbound LHS)
```
So Clausal's `is/2` is effectively **bind-only**: it works when the LHS is unbound but does
NOT unify a *pre-bound* LHS with `eval(RHS)`. ISO Prolog's `is/2` unifies (`5 is 2+3`
succeeds).

## Why it bites
A public query predicate that both computes a numeric value AND lets the caller pass it in for
checking (`pred(..., OUT)` used in check-mode with OUT bound) cannot use `is/2` for the final
step — it must use `==` (evaluate-and-compare). Domains discovered this empirically and switched
to `==`; a predicate binding a caller-checkable numeric output must use `==`, not `is`. The
reach agent also reported `REQ_ID == <atom>` guards throwing `type_error(evaluable)` on an
UNBOUND id (because `==` tries to arithmetic-evaluate) — the dual gotcha: use `is`/unification
for atoms, `==` for pre-bound numerics.

## Decision needed
Either (a) make `is/2` ISO-compliant (unify a ground LHS with the result) — a broad semantic
change, needs a careful audit of existing reliance on the bind-only behavior; or (b) treat it
as intended and DOCUMENT the idiom prominently (cheat-sheet + the query-coverage executor
prompt): "checking a pre-bound numeric output → `==`; binding a fresh numeric → `is`; matching
an atom → `is`/unification, never `==`." Recommend (b) first (low-risk, unblocks authors) with
(a) as a separate investigation.

## Repro
`/tmp/isprobe/t.clausal` (3 Tests; the pre-bound-LHS `is` case fails).
