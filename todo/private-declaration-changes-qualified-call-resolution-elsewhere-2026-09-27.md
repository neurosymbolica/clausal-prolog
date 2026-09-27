# `-private([nosuch])` in one module changes how `other_mod.nosuch(1)` fails in an UNRELATED module

**Status: OPEN. Found 2026-09-27 during Compound retirement slice 2; not fixed.**

## What happens

A qualified call to a predicate that does not exist fails with
`PredicateNotFoundError`. If some *other* module, one that neither the caller
nor the target imports, has declared the same name as an atom with
`-private([nosuch])`, the same call fails with a different error. That error is
a plain `existence_error` which says it was "resolved via a data reference".
So one module's declaration leaks into name resolution in unrelated modules,
and the outcome depends on load order.

## Minimal repro (main 03f70a71)

`other_mod.clausal`:

    -module(other_mod, [real(X)])
    real(1),

`caller_mod.clausal`:

    -module(caller_mod, [t(R)])
    -import_module(other_mod)
    t(R) <- (other_mod.nosuch(R)),

`decl_mod.clausal` (unrelated to both):

    -module(decl_mod, [])
    -private([nosuch])

Driver:

    import sys, importlib
    sys.path.insert(0, ".")
    if sys.argv[1] == "with":
        importlib.import_module("decl_mod")
    m = importlib.import_module("caller_mod")
    from clausal.logic.solve import solve
    from clausal.logic.variables import Var
    list(solve(("t", Var()), module=m))

Output:

    without: clausal.predicate_diagnostics.PredicateNotFoundError:
             nosuch/1 is not defined in module 'other_mod' (reached through a
             module-qualified handle)
    with:    clausal.logic.exceptions.LogicException: Uncaught logic exception:
             error(existence_error(procedure,nosuch/1),nosuch/1): atom 'nosuch'
             is not callable at arity 1 (resolved via a data reference; define
             or import the predicate, or call it by its local name)

## Likely area

Atoms are global by spelling (an atom IS its `str`). So a declared atom's
module-level binding, or whatever the qualified-call path reads to decide
"data reference", is probably found by spelling rather than in
`other_mod`'s own namespace. Start from where the "resolved via a data
reference" message is raised and check which namespace it consulted.

## Expected

The error for `other_mod.nosuch(1)` depends only on `other_mod` (and the
caller), never on what an unrelated module declared.
