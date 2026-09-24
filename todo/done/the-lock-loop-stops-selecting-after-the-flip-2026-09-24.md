# The static-predicate LOCK loop selects nothing after the flip — silently

**Found:** 2026-09-24, by the re-audit of the 18 deferred F1 sites
(`.superpowers/sdd/f1-reaudit-report.md`, row 25). Reproduced by the
controller before filing. **Blocks the flip.**

## The site — `compiler_v2.py:488-494`

    for obj in module_dict.values():
        if isinstance(obj, PredicateMeta) and hasattr(obj, '_fields'):
            key = (obj.__name__, len(obj._fields))
            if db.row(*key) is None:
                continue
            if not db.is_dynamic(*key):
                obj._lock()

## Measured

    TODAY   module_dict values the loop selects: ['holds', 'label', 'same']
    AFTER   the same loop selects              : []

After the flip a predicate's module-dict binding is a mangled ATOM (a `str`),
so `isinstance(obj, PredicateMeta)` is False for every one of them and **the
loop body never runs**.

## Why it matters, and why it is the bad kind of failure

`_lock()` is what stops runtime `assertz`/`retract` on a STATIC predicate:

    def _lock(cls) -> None:
        cls._state_row().locked = True

If the loop selects nothing, nothing is locked, and **every static predicate
silently becomes mutable at runtime**. No error, no failing test — the gate
that refuses the write is simply never armed. Same failure shape as the
`through=` bug: a guard that stops guarding without saying so.

## It is NOT "needs a row instead of a class"

`_lock` has an exact row equivalent (`row.locked = True`), so the *action*
migrates trivially. The problem is the **selector**: the loop finds its
population by filtering `module_dict` on `isinstance(..., PredicateMeta)`,
and that filter is what dies. Migrating `obj._lock()` to `row.locked = True`
would leave the loop selecting nothing and look like a clean migration.

## Fix shape (not yet designed)

Iterate a population that survives the flip — the db's own rows for this
module, or its declared functors — rather than filtering module-dict values
by Python type. Whatever is chosen, it needs a positive control asserting the
population is NON-EMPTY for a module known to have static predicates; a lock
loop that locks nothing must fail loudly, not pass quietly. (Compare the
census discipline: N==0 is a refusal, not a pass.)

## Owner

W4b-2d / the flip. Do not land the flip before this is fixed.

## Resolved 2026-09-24

Step 7 is now `_lock_static_predicates(db)`: it iterates
`Database.owned_keys()` (the containers `row()`'s `known` test reads, minus
`_adopted`) and sets `row.locked` on each non-dynamic key. It takes no module
dict, so a binding's Python type cannot empty it.

Measured against the old walk over the house suite (3641 module loads, probe
placed BEFORE the loop — an earlier probe placed after it read its own
writes and reported everything as "already locked"):

| population | n | old walk | new |
|---|---|---|---|
| imported static rows | 205 | re-locked (owner had already locked) | skipped, no change |
| imported `-dynamic` row (`test_cell_goals` `cg_imp` `lp/1`) | 1 | **locked the owner's dynamic predicate** | skipped |
| owned static row, module-dict class carries another row | 4 | own row left unlocked | locked |
| owned static row, name bound as an atom | 6 distinct | left unlocked | locked |

The second row was a live bug: importing a `-dynamic` predicate without
re-declaring `-dynamic` in the importer locked it on the OWNER, after which
the owner's own `assertz` raised `permission_error(modify, static_procedure)`.
The importer asked its own database `is_dynamic` about an adopted row.
`tests/fixtures/gate_dyn_user.clausal` re-declares `-dynamic`, which is why
nothing caught it.

Positive controls: `tests/test_lock_static_predicates.py`. Mutation-checked —
restoring the old walk fails the import test; an empty population fails
three of the four. Gate: 146 failed both sides, identical sets, +4 passed.
