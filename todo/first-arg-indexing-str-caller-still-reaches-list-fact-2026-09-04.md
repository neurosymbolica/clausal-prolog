# First-arg indexing: str caller still reaches a list-headed fact after cons-rule retirement

Found during P3-1 Task 5 (cons-rule retirement) while fixing
`tests/audit_2026_05_25/test_class_C15_first_arg_indexing.py::test_F095_first_arg_index_coalesces_str_and_charlist`.

## Observation

With a 5-fact predicate `TestPred(1), TestPred(2), TestPred(3), TestPred("abc"),
TestPred(['a','b','c'])`:

- `TestPred(['a','b','c'])` (list caller) -> 1 solution (correct: only the
  list-headed fact matches, now that `unify("abc", ['a','b','c'])` is
  retired).
- `TestPred("abc")` (str caller) -> **2 solutions** (the str-headed fact,
  same-type, PLUS the list-headed fact `['a','b','c']`). This is asymmetric
  with the list-caller case and should — under §1b ("lists unify with
  lists, str unifies with str") — also be 1.

Confirmed NOT caused by the `_variables.c` `do_unify` str<->list block this
task removes (verified directly: `unify("abc", ['a','b','c'], trail)` is
`False` in isolation, on the rebuilt extension).

## Hypothesis (unconfirmed)

`_normalize_dataclass_fact` (`clausal/logic/database.py:414`) hoists a fact
whose head is a *ground value* into a Var-headed clause + a body `Unify`
goal (`TestPred(V) <- Unify(V, "abc")`). If a ground LIST literal head
(`['a','b','c']`, no Vars/StarUnpack) is hoisted the same way, both the str-
and list-headed facts would compile to Var-headed clauses — which
first-arg indexing likely cannot bucket on caller type, so they land in
whatever "unindexable" bucket gets scanned unconditionally. That alone
doesn't explain the asymmetry (both callers should then see both clauses,
or neither) — needs an actual trace through `arg_index.py`'s bucket
construction to find why a STR caller's bucket scan differs from a LIST
caller's.

## Disposition

Parked, not fixed, by Task 5: this is a residual quirk in the
indexing/fact-elaboration layer (`database.py` / `arg_index.py`), not the
`_variables.c` cons rule Task 5 retires. It is over-permissive in one
direction only (str caller reaching a list fact) — never under-permissive
relative to the new §1b semantics — so it does not resurrect the retired
rule's main hazard (silent str~list identity in general unification); it's
scoped narrowly to first-arg-indexed ground-literal FACTS.

Follow-up: trace `arg_index.py`'s bucket-key construction for a ground str
vs ground list first-arg literal fact, and `_normalize_dataclass_fact`'s
hoisting behavior for ground list heads, to find the actual mechanism and
decide whether to fix (make str-caller symmetric with list-caller, i.e. 1
solution) or accept as documented behavior.
