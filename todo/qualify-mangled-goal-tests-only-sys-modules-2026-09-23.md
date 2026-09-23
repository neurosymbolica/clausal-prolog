# `qualify_mangled_goal` tests only `sys.modules`, so a mangled name into a
# real PYTHON module raises an UNCATCHABLE error

**Found by:** the W4b-2 open-questions analysis, 2026-09-23; reproduced
independently by the controller before filing. Live on main `ad882878`.
Introduced with pieces 1-2 of the Python boundary (`f73ccc65`).

## The code

`clausal/logic/cells.py:530` `qualify_mangled_goal` decides whether a
mangled functor is a handle by asking ONLY:

    if module_name in sys.modules:
        return (QUALIFIED_GOAL_FUNCTOR, module_name, (name, *goal[1:]))

`sys.modules` contains every imported PYTHON module, not just Clausal ones.

## Reproduced

    from clausal.logic.atoms import mangle
    import json                       # an ordinary Python module

    qualify_mangled_goal((mangle("json", "whatever"), 1))
      -> (':', 'json', ('whatever', 1))        # qualified into a non-Clausal module

    list(solve((mangle("json", "whatever"), 1)))
      -> PredicateNotFoundError, MRO: PredicateNotFoundError, KeyError, LookupError
         isinstance(e, LogicException) is FALSE
         "Predicate whatever/1 not found / json defines no predicates of its own.
          -> define whatever/1 in json, or import it"

Contrast, the SAME shape whose module is not loaded at all:

    list(solve((mangle("no_such_module_zz", "whatever"), 1)))
      -> LogicException: existence_error(module, ...)      # the correct shape

## Why it matters

1. **The error is not catchable by a Clausal program.** `PredicateNotFoundError`
   is a `KeyError` subclass, not a `LogicException`, so `catch/3` cannot see
   it — where the not-loaded case correctly raises `existence_error(module, ..)`.
   Two spellings of one mistake, and the more surprising one is the one that
   escapes the language's error handling.
2. **The advice is nonsense**: "define whatever/1 in json".
3. **W4b-2 makes it reachable by accident.** Today it needs a hand-built
   mangled atom. Once module attributes for predicates ARE mangled atoms, any
   Clausal module whose name collides with an imported Python module
   (`string`, `types`, `operator`, `time`, `json`, ...) takes this path.

## The fix, as proposed by the analysis (not yet ruled)

Test that the module is a CLAUSAL one and that the name is a predicate, not
data:

    _db_for_module_name(module_name) is not None
      and db.declared_kind(name, arity) != "data"

`_db_for_module_name` landed with W4b-1 (`clausal/logic/predicate.py`) and
reads `mod.__dict__["$module"].db`. **Caveat recorded by the analysis:** the
second half is INERT until `-hide` also calls `db.declare_functor(name, ())`,
which is unbuilt — so today nothing marks a `-hide` data atom as `"data"`.
That knock-on was flagged but not exhaustively checked, including its effect
on `field_names_for` answering `None` vs `()`.

## Owner

W4b-2. Fix the `sys.modules` test at minimum — that half needs no new
machinery and closes the uncatchable-error path on its own.
