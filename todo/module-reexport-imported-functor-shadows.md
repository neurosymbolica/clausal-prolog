# Re-exporting an imported functor "shadows" it with a fresh empty class — NON-BUG (resolved 2026-07-22)

**Status:** RESOLVED — investigation showed the engine already does the right
thing. Closed with regression tests, no code change. Kept as a note because
both `tests/test_functor_reexport.py` and
`todo/statement-context-tuple-goals-silently-discarded.md` reference it.

## Original report
A module that BOTH `-import_from`'s a functor and lists it in its own `-module`
export list appeared to get a fresh, distinct predicate class — silently
shadowing the import — so a downstream `-import_from` of the "re-exported"
functor found nothing (a query returned **0 solutions**).

## Investigation (2026-07-22) — not a shadowing bug
The engine already preserves identity. `compiler_v2._process_declarations`
only mints a fresh module-local class when no class exists *or* the existing
binding is the process-global default (`existing is global_cls`). An imported
functor is module-local — never the global default — so it is preserved, and
listing it in `-module` re-exports it with **shared class identity**.

The pre-existing `test_atom_shadowing.py` suite exercises the narrowed
shadowing *warning* by running `_process_declarations` in isolation, so it never
binds a real imported class and cannot observe the identity outcome. The new
`tests/test_functor_reexport.py` closes that gap: it loads real modules through
the import hook and asserts identity is shared and solutions flow across a
`kit → queries → downstream` re-export chain.

## What the "0 solutions" symptom actually was
The re-export chain was a red herring. The real cause of the observed
"re-exported functor finds 0 solutions" was an **unparenthesised multi-goal
clause body written at statement level** — `fact(R), other(R)` parses as a bare
Python tuple that is evaluated and silently discarded, so the intended goals
never became a clause. That footgun is filed and fixed separately:

→ **See `todo/statement-context-tuple-goals-silently-discarded.md`** for the
root cause and the fix (statement-level arrow-less multi-goal tuples now raise a
`SyntaxError` instead of silently no-op'ing).

## Guard against regression
If someone ever changes the narrowed shadowing trigger to re-mint predicate
functors (believing it should match the atom-shadowing behaviour),
`tests/test_functor_reexport.py` fails loudly.
