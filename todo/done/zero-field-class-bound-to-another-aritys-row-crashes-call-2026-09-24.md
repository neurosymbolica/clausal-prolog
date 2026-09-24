# A zero-field class bound to another arity's row crashes call/N with a Python TypeError

**Found:** 2026-09-24 by the name+arity-ruling lane; reproduced on canonical
main c68d6552 by the controller. **Pre-existing.** Related:
`todo/dynamic-at-another-arity-moves-the-class-2026-09-17.md`.

    -dynamic(ping/2)

    ping <- True

After load, `module.ping` is a class with `_fields == ()` bound to row
`('ping', 2)`. `call("ping", module=lm)` then raises

    TypeError: ping__2() missing 2 required positional arguments: 'arg1' and 'trail'

-- a raw Python error, not a Prolog error term. Expected: `ping/0` answers
(its clause is `ping <- True`) and `ping/2` is a separate, clause-less dynamic
predicate. The class is on the wrong row, so the arity-0 call dispatches the
arity-2 compiled function.

Likely resolves at the flip (no class to mis-bind); check it does, and pin it
with a test in both eras.

## Resolved (2026-09-24, branch fix/small-todos-batch-2026-09-24)

Same defect as `todo/done/dynamic-at-another-arity-moves-the-class-2026-09-17.md`;
fixed there too. It did NOT wait for the flip: the cause was
`compiler/predicate.py`'s resolve-`pred_cls`-by-NAME (four sites, all
arity-blind) feeding `_install`, which re-bound the name's class onto the
clause-less declared arity's row (step 5 compiles `ping/2` with no class) and
wrote `ping__2` onto the class. Fix is at the one choke point: `_install`
declines a class already bound to THIS database's row at ANOTHER arity (the
dispatch still lands on the db row). Covers the load and the lazy recompile
after a runtime `assertz(ping(1, 2))`.

Tests: `tests/test_dynamic_at_another_arity_both_eras.py` (class era and a
mangled handle from `mint_predicate_handle`); all 5 fail with the guard
disabled. `tests/predmeta_p1/test_find_pred_cls_arity_and_symmetry.py` pinned
the defect as its precondition; it now builds the misplaced state by hand.

Not fixed here: in the CLASS era `call("ping", X, Y)` still refuses with
`PredicateArityMismatchError` ("one name has one arity"); that is
`todo/wrong-arity-call-still-refuses-in-two-places-2026-09-24.md` (solve.call
Phase 5). The flipped era answers `ping/2` with 0 solutions.
