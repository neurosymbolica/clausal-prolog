# An importer that does not declare `-dynamic` locks a shared dynamic predicate — for its OWNER too

Filed 2026-09-05 during P3-3 Task 3 (mutation gate) fix-round re-review. Pre-P3-3 in
substance (the lock was per-CLASS and the class is shared); recorded here because the
gate now makes the symptom loud and names the wrong party.

## Repro (reviewer-verified on feat/p33-state-reloc @ f08a21d5)

Owner module declares `-dynamic(lp/1)` with one fact. An importer `-import_from`s `lp`
WITHOUT re-declaring `-dynamic`. After the importer loads, compile step 7 locks the
shared row (`row.locked == True`). Afterwards:

- the importer's `assertz(lp(2))` is refused —
  `permission_error(modify, static_procedure, lp/1)` (arguably correct), AND
- **the owner's own `PredicateMeta._assertz` is refused too** —
  `runtime-assert:<owner> may not write lp/1: it is a locked static procedure`.

The owner declared the predicate dynamic; a downstream module's load must not be able to
take that away.

## Direction

Step 7 (lock) should skip a row whose class is bound to another db's row and whose owner
declared it dynamic (the `-dynamic` flag lives on the OWNER's row — read it there via the
bound row, as `_home_db` does for runtime asserts). Related: P3-3 T3 fix round 1 step 4a
already leaves an imported `-dynamic` predicate alone; step 7 should follow the same rule
from the same policy predicate (do not add a third hand-copy of `_bind_row`'s police —
see ledger note on `_belongs_elsewhere`).

Pin: owner `_assertz` after importer load still succeeds; owner + importer both see the
new clause.
