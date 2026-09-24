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
