# An aliased/imported `assertz` no longer reaches the owner's row

**Status:** **RULED 2026-09-20 by the operator — (a) ADOPTION WINS.**
`-import_from` makes `db.row(name, arity)` in the importer BE the exporter's
row; a local `-dynamic` on an imported name is an error or is ignored. The cell
then resolves correctly by name with no new carrier, and both `xfail(strict)`
tests pass as written — so when this is implemented, REMOVE those two xfail
markers rather than leaving them (strict, so they fail loudly if not).
The channel-4 wrong-refusal message is fixed by the same change: once the
importer's row IS the owner's, the ownership gate gets the chance to speak
before the static check.

Options (b) "the alias carries its module" and (c) "module locality wins, the
tests are wrong" are CLOSED. Do not re-open.

Originally filed as: Found 2026-09-20 during the P2
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

---

## 2026-09-21 — IMPLEMENTATION ATTEMPTED AND BACKED OUT. Read this first.

The ruling is clear; the implementation is not a small change, and four
routes were tried and measured. **Nothing landed** — the tree is exactly as
Task 7 left it, and the two `xfail(strict=True)` markers STAY until this is
finished.

### The chain, established by measurement

1. `AliasS(X)` builds the cell `('bo_p', X)` — the exporter class's
   `__name__`, correctly — and a cell carries no module.
2. `assertz__1` (`database_ops.py`) resolves the write's home through
   `_find_pred_cls(functor, arity, module_dict, head)` → `_home_db(db,
   pred_cls)` → `pred_cls._row.db`. **It is the CLASS, not the row, that
   decides where the clause lands.**
3. `_find_pred_cls`'s IDENTITY-RESOLVED leg settled the aliased case from
   `type(head)` — the head was an INSTANCE of the exporter's class. **Under
   P2 the head is a cell, `type(head)` is `tuple`, and that leg is dead.**
   Its docstring still describes the instance behaviour.
4. So resolution falls through to `module_dict.get("bo_p")`, which in the
   importer is the **local shadow class** that its own `-dynamic(bo_p/1)`
   minted. The clause lands there. Silently.

### The four routes, and exactly how each failed

* **(i) Plant the exporter's canonical spelling as an adopted row too**
  (`_plant_imported_rows` adopting under `orig_name` as well as
  `local_name`). Makes `db.row("bo_p", 1)` answer the owner's row — and
  **directly contradicts an existing named invariant**,
  `tests/shared_rows/test_import_plants_a_row.py::
  test_an_aliased_import_does_NOT_plant_the_exporter_s_spelling`. Caught by
  the full gate as NEW 1, not by the mutation-gate file.
* **(ii) Make `row()` prefer `_adopted` when the only local claim is a
  `-dynamic` marking.** Non-breaking but INERT: `row()` returns a cached
  `self._rows` entry before it ever consults `_adopted`, so once a local row
  exists it wins permanently.
* **(iii) Skip `mark_dynamic` for an imported name** (the ruling's "a local
  `-dynamic` on an imported name is ignored"). Breaks the two NON-aliased
  tests — `test_an_imported_dynamic_predicate_is_asserted_ON_ITS_OWNER` and
  `test_an_assert_through_a_shared_class_keeps_the_owners_namespace` — with
  "locked static procedure": those rely on the IMPORTER's own `-dynamic` to
  permit the write, because the permission gate reads `row.locked` on
  whichever row the write reaches.
* **(iv) Resolve the alias by scanning `module_dict.values()` for a class
  whose `__name__` is the cell's functor** (what `type(head)` used to do,
  without planting a row). Keeps `shared_rows` green — but **cannot fire for
  the fixture**: the importer's `-dynamic(bo_p/1)` makes
  `module_dict["bo_p"]` a valid arity-checked class, so `candidate` answers
  first. Guarding on "candidate is None" makes the leg dead code.

### The knot

Every route runs into the same question, which the ruling states but does not
resolve mechanically: **`gate_alias_user.clausal` declares BOTH
`-dynamic(bo_p/1)` AND `-import_from(..., [alias(bo_p, AliasS)])`.** Is
`bo_p` in that module its own predicate or the import? The ruling says the
import wins ("a local `-dynamic` on an imported name is an error or is
ignored") — but the permission gate reads `row.locked` on the reached row,
and the two non-aliased tests depend on the importer's own `-dynamic` to
unlock the write. **So "ignore the local `-dynamic`" and "the importer's
`-dynamic` is what permits the write" are both load-bearing today, and they
contradict.**

Resolving that is the actual work, and it is a design step, not a patch:

* If the local `-dynamic` is ignored, the permission gate must stop reading
  the importer's `_dynamic` and read the OWNER's row instead — which is
  `row.locked` on the adopted row, so adoption has to reach the gate first.
* An `-import_from`'d name may then need to be refused a local `-dynamic`
  outright (the ruling's "or is an error"), which makes `gate_dyn_user`
  and `gate_alias_user` both ILLEGAL as written and the fixtures change.

**Recommended next step:** decide whether a module may declare `-dynamic` on
a name it imports. If NO (error), the fixtures change and route (iii) plus a
row-reading gate is the implementation. If YES (ignored), the gate must read
the owner's row and route (iii) needs the gate fixed in the same commit.

### Cheap facts for whoever picks this up

* `--runxfail` shows the real failures behind the two markers; without it
  they read as a clean `2 xfailed`.
* Do NOT probe by `_load_module`-ing owner and user separately — that makes
  two copies of the owner and every row identity comparison lies. Load
  through the test's own `_load_fixture`.
* `tests/shared_rows/` is the invariant suite for adoption and is NOT in
  `test_mutation_gate.py`. Run both, and gate on the FULL house run: route
  (i) looked green on the mutation-gate file alone.
