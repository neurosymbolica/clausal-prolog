# An aliased/imported `assertz` no longer reaches the owner's row

**Status:** **CLOSED 2026-09-21 — implemented; see the last section.**
Ruled 2026-09-20 by the operator — (a) ADOPTION WINS.
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

---

## 2026-09-21 — DONE. The knot was a false one; here is what dissolved it.

**The blocking question was "may a module declare `-dynamic` on a name it
imports?" It is answered by MEASUREMENT, not by a ruling: it already may, and
the non-aliased sibling has always relied on it.**

`gate_dyn_user.clausal` declares BOTH `-dynamic(gd_p/1)` and
`-import_from(..., [gd_p])`, and its test has always passed. Measured on the
branch, that is because **the import WINS the name binding**:
`user.__dict__["gd_p"] is owner.gd_p`. The shadow class the declaration mints
is simply overwritten, so there is no contradiction between "ignore the local
`-dynamic`" and "the importer's `-dynamic` permits the write" — those are two
DIFFERENT effects of the same directive, and only the second survives:

* the NAME resolves to the import (the shadow class loses), and
* the MARK stays on the importer's database — which is what keeps step 7
  ("lock non-dynamic predicates") from locking the shared class's row, since
  that loop walks `module_dict.values()` and an imported class's `_row` is the
  OWNER's row.

Route (iii) broke the two non-aliased tests because it removed the second
effect. Nothing ever required removing the first.

### What the aliased case was missing

Under an alias, only `AliasS` is bound, so the shadow class keeps the
canonical spelling `bo_p` and `_find_pred_cls` answers with it. That is the
whole defect. The fix is one rule, stated where the directive is processed:

> **A `-dynamic(f/N)` declaration in a module that imports a predicate whose
> own name is `f` at arity N NAMES THAT IMPORT.** The canonical spelling binds
> to the imported class, exactly as it already does when the import is not
> aliased.

`compiler_v2._imported_class_by_canonical_name` finds it by `__name__` among
the module's bindings (`_belongs_elsewhere` keeps it to imports, so a module's
own declaration is never rerouted), and step 4a binds it — unless this module
has clauses of its own under the name, which is a genuine clash the local
definition wins, the same rule `Database.adopt_row` states for rows.

Everything downstream then runs the PROVEN non-aliased path: `_find_pred_cls`
returns the shared class by its last leg, `_home_db` reaches the owner's row,
and the gate asks the ownership question against it.

### Channel 4 was a separate, smaller defect

The refusal came from `_check_cell_head_permission`, not from the gate at all:
a cell head whose row is not dynamic raises that function's OWN
static-procedure error, and it fires before `assertz__1` ever opens the gate.
Pre-P2 the head was an INSTANCE, `compound_cell_shape` said no, and the
function returned without checking anything — which is why the gate used to
speak. The check now asks the gate first **when the row belongs to another
database** (`home is not db`): that is exactly the case where its own remedy
("declare it `-dynamic(f/N)`") is advice the reader must not take. A row in
this module's own database is untouched, so no local refusal text moved.

### Measured after the fix

    user bo_p binding is the exporter class?   True
    user AliasS binding is the exporter class? True
    u.row(AliasS, 1) is the owner's row?       True
    u.row(bo_p, 1) is the owner's row?         False   # inert local row, as
                                                       # in the non-aliased
                                                       # case; nothing reads it

Note the ruling's literal wording — "`-import_from` makes `db.row(name,
arity)` in the importer BE the exporter's row" — is NOT what makes either case
work, and never was: the importer's own `-dynamic` mints a local row first
(`row()` answers `_rows` before `_adopted`), so `db.row("gd_p", 1)` is a local
row in the WORKING case too. The write reaches the owner through the shared
CLASS. The ruling's intent — the write lands on the owner — is met.

* Both `xfail(strict=True)` markers are REMOVED and both tests pass.
* `tests/shared_rows/` green, including
  `test_an_aliased_import_does_NOT_plant_the_exporter_s_spelling`: no row is
  planted under the exporter's spelling. That invariant is about a module that
  never wrote the name; `gate_alias_user` writes it, in its `-dynamic`.
* House gate NEW 0 / GONE 0 vs main `bd774c46`, extraction 146 = summary 146
  on both arms.
* Blast radius, censused: **1** file in the engine tree (the fixture) and
  **0** of 235,663 corpus `.clausal`/`.seam` files declare `-dynamic` on a
  name they import under an alias.

### The one judgement call, for the record

A module that declares `-dynamic(f/N)` while importing a DIFFERENT module's
`f/N` under an alias now has its declaration rerouted to the import rather
than minting a local predicate. That is ruling (a) applied consistently, and
the census says no such file exists. If a local predicate is wanted there, the
module should give it clauses (the local definition then wins) or not spell it
in the canonical name.

## Moved to done/ 2026-09-30

Its status line says CLOSED 2026-09-21 (implemented); it had stayed in todo/.
