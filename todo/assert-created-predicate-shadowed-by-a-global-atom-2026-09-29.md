# An assert-created predicate is shadowed by a same-named atom in the global pool

Found 2026-09-29 while landing the native `.pl` front end's slice 2: a test
passed alone and failed in the full suite.  Both `.pl` front ends are
affected (the translator too), so it is an engine issue, not a front-end one.

## Repro

```python
import clausal.import_hook as ih
ih.predicate_builtins['note'] = 'note'     # what an earlier module declaring
                                           # the atom `note` leaves behind
```

```prolog
% acd.pl -- assert_creates_dynamic is on for every .pl module
add(X) :- assertz(note(X)).
all(L) :- add(a), add(b), findall(X, note(X), L).
```

`all(L)` raises `existence_error(procedure, note/1)`: "atom 'note' is not
callable at arity 1 (resolved via a data reference ...)".  Without the pool
entry it answers `[[a, b]]`.

## Why

A body goal naming a predicate that has no clauses at compile time resolves
through `module_dict`, which is seeded from the process-wide atom pool
(`predicate_builtins`).  When another module has declared the same spelling as
an atom, the goal binds to that atom (a data reference) instead of a lazy
procedure reference that `assertz` would later fill.  The answer therefore
depends on what else the process loaded first.

## Next

Make a clause-body goal resolve to a procedure reference whenever the name is
not a procedure here, whatever the atom pool holds; pin with a test that seeds
the pool first.  The slice 2 tests use a distinctive name meanwhile.
