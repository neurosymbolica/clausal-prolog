# An aliased/imported `assertz` no longer reaches the owner's row

**Status:** open (parked for the operator). Found 2026-09-20 during the P2
Task 4 sweep on `feat/predmeta-p2-head-cells-2026-09-19`. Two tests parked
`xfail(strict=True)` in `tests/test_mutation_gate.py`:
`test_an_aliased_import_asserts_ON_ITS_OWNER` and
`test_channel_4_the_assertz_builtin_from_a_non_owner_is_refused`.

**This is a SEMANTIC change, not a test-shape one.** It is the one finding of
the Task 4 sweep that changes what a program DOES, so it should be ruled on
before the P2 line lands.

## The mechanism, measured

`assertz(AliasS(X))` used to hand `assertz` a term INSTANCE. The instance's
CLASS was the exporter's own class, so the write could follow `type(term)` to
the owner's row no matter what the importer called the spelling.

Under P2 `AliasS(X)` builds a CELL. `PredicateMeta.__call__` keys the cell on
`cls.__name__`, so the cell is `('bo_p', X)` — the exporter's CANONICAL name,
correctly — but a cell carries **no module**. The functor is then resolved in
the CALLING module (R-P2-2, module locality), and the write lands there.

Measured on the branch, `tests/fixtures/gate_alias_{owner,user}.clausal`:

    owner row  id=...938784  clauses: 1
    user  row  id=...939648  clauses: 0
    SAME ROW?  False
    AliasS(X) builds: ('bo_p', 1)
    after the assert ->  owner row: 1 clause   user row: 1 clause

The clause landed on the IMPORTER's row. The owner's answers did not change.

The second test is the same cause seen from the other side: with no local
`-dynamic`, the importer's own `impclob_colour/1` row is static, so the
STATIC refusal fires ("is a static procedure — declare it -dynamic") where
the OWNERSHIP refusal should have ("may not write impclob_colour/1"). The
gate did not get the chance to speak, because nothing told it the goal named
the owner's predicate.

## What makes it a design question, not a bug to fix in passing

Measured: `-import_from` did NOT give the importer the exporter's row in
either fixture — `db.row(...)` answers a distinct local row in both, and in
the alias case the importer's own `-dynamic(bo_p/1)` mints one too. So this
sits across three pieces of work at once: P1's shared row
(`Database._adopted`), the P4-prerequisite rule that every fielded
declaration mints a row, and P2's module locality. Which of them should give
is not a call for the sweep.

## The options

* **(a) Adoption wins.** `-import_from` makes `db.row(name, arity)` in the
  importer BE the exporter's row, and a local `-dynamic` on an imported name
  is an error (or is ignored). The cell then resolves correctly by name with
  no new carrier. Closest to what the two tests already assert.
* **(b) The alias carries its module.** An aliased reference lowers to the
  qualified cell `(':', owner, ('bo_p', X))`, which `_resolve_named_goal`
  already understands. Explicit, and it keeps module locality intact — but it
  puts a module back into the term, which is the thing P2 took out.
* **(c) Module locality wins and the tests are wrong.** The importer declared
  `-dynamic(bo_p/1)`; writing to its own row is then correct, and
  `test_an_aliased_import_asserts_ON_ITS_OWNER` encodes a rule that P2
  deliberately retires. This still leaves the channel-4 refusal to fix, since
  a WRONG refusal message is a defect under any of the three.

**Engine-lane recommendation: (a).** It is what `-import_from` already means
elsewhere (the import relationship IS the shared row, per the §4 answer), it
needs no new term carrier, and it makes both tests pass as written. (b) is a
real option only if aliases must be able to shadow; (c) should not be adopted
without a corpus check, since it silently moves where a write lands.

## Not to be confused with

The other channels in `test_mutation_gate.py` pass unchanged — this is
specifically the IMPORTED/ALIASED write, not the gate itself.
