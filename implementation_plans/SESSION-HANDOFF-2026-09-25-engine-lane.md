# Engine-lane handoff, 2026-09-25 (final)

**Canonical main is 9673fe7f.** Box and GitLab are NOT pushed: the operator asked us to wait for stability. The release plan is `release-1.0.0-and-push-plan-2026-09-25.md`.

## Landed today (each: clean gate, roborev Lows only, clean downstream sweep)
| sha | change |
|---|---|
| e107929e | W4b-2d, the flip |
| 45ca3f41 | flip-era docs |
| a6c677f6 | the provenance package disabled |
| 47a2d8ce | Solutions solves a cell |
| 5bc70520 | W4b-3 slices 1-2 |
| 19ac4dda | slice 3: builtins are BuiltinTerm objects |
| 04af7029 | no implicit padding |
| 9049383d | seam follow-ups + the boolean-seam lint |
| 9fa2cfa0 | keyword-only partial construction refused; predicate names at the written arity |
| b175e329 | slice 4: specialize_mi returns a handle; term expansion is classless |
| 9673fe7f | q() quasi-quotation retired; a pooled atom applied as a functor gives the undeclared-functor error |

## Next
- **W4b-3 slice 5,** the rewriter stops emitting PredicateMeta class blocks. Awaiting the operator's go; the downstream answer-set A/B is ready.
- **Slices 6-8:** the Python-API arm, deleting the class, the C tail.

## Queued Lows
- `_undeclared_functor` kwargs collide with `functor=` / `arity=`.
- The term-expansion pre-mint changes what a bare atom means in TE rules.

## Parked todos
- A head variable named like a Python keyword crashes the load.
- A term_expansion body can't call a same-module helper.
- EDCG fact accumulator slots.

## Open questions
- Should a clause-less exported predicate stay a procedure (ISO) rather than data?

The rulings are recorded in the lane's memory notes.
