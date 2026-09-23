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

1. **The error has the wrong SHAPE, not the wrong catchability.**
   **CORRECTION, 2026-09-23** — the first version of this todo said the error
   was *uncatchable*. That was wrong, and it was my error, caught by a review.
   `_compile_catch_impl` emits `except Exception` and converts anything that is
   not a `LogicException` through `python_error_term`
   (`clausal/logic/_trampoline_py.py:32`,
   `clausal/logic/compiler/control_constructs.py:762`); the comment there says
   routing every `Exception` is exactly "what makes the two routes agree". So
   `catch/3` DOES see `PredicateNotFoundError`.

   The real defect is that it arrives as an implementation-specific
   `python_error_term`, while the not-loaded case arrives as a proper ISO
   `existence_error(module, ..)`. Two spellings of one mistake, one of which a
   conforming program cannot pattern-match. Less severe than first filed;
   still wrong.
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
machinery and closes the wrong-error-shape path on its own.


## Review by a second model (2026-09-23) — three points that change the fix

**a. The discriminator may be unnecessary.** `\x1f` is reader-unwritable, so a
mangled functor in goal position is a handle BY CONSTRUCTION; the module-half
test only decides which error wording a mistake gets. Recommendation: always
qualify, never inspect the module half here, and let resolution raise. Simpler
than the two-conjunct test proposed above.

**b. Two concrete problems with the proposed `declared_kind` conjunct.**
   * A false negative: the measured message "json defines no predicates of its
     own" shows `_coerce_module` already wraps plain Python namespaces and
     scans them for predicates. If Python-hosted predicates are a real module
     kind, a handle into one has no `$module`, so the db test demotes a REAL
     handle to "data atom" — silently, into the untouched-atom path.
   * An arity mismatch: `-hide` would register `name/0`, but a data atom
     misused in goal position arrives as `(atom, X)` — arity 1. So
     `declared_kind(name, 1)` misses it even once `-hide` registration is built.

**c. The error should be `existence_error(procedure, Name/Arity)` as a
LogicException, for BOTH cases.** ISO 7.7.7: an atom or compound IS callable,
so `type_error(callable, ..)` is wrong for any mangled atom (that is for
integers and the like; an unbound functor gets `instantiation_error`).
`existence_error(module, ..)` is not ISO-core: Scryer answers `nomod:foo` with
`existence_error(procedure, foo/0)`, and Trealla likewise — neither
distinguishes "module missing" from "procedure missing" for a qualified call.
The program never wrote a module designator, it wrote a handle, so the fault is
"no such procedure" whichever way the module half fails. Culprit `Name/Arity`
to match Scryer (SWI's `M:N/A` is explicitly not a target); the module goes in
the context slot `existence_error/3` already has. Keep
`existence_error(module, ..)` only for an EXPLICIT `(":", M, G)` whose `M`
fails to resolve — there the user did name a module.

**d. An unnamed failure mode: the classification is TIME-DEPENDENT.**
`sys.modules` membership changes under a running program — test teardown
`del sys.modules[...]`, `importlib.reload`, the `.clausal` hook re-registering
— so the SAME handle flips between "qualified goal" and "untouched atom"
during one run. And a `-hide` data atom flips the other way the moment
unrelated code imports a Python module sharing its bare declared name (`csv`,
`json`, `types` are plausible domain names). NOT YET REPRODUCED; cheap to
reproduce, and it raises the severity if it holds.
