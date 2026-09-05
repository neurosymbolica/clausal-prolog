# P3-3 Task 3 — the mutation gate + per-write provenance

Commit: `67c0eb3f` "P3-3 Task 3: THE MUTATION GATE — one door, one policy,
provenance per write" (branch `feat/p33-state-reloc`, on `0b8c2937`).

Both parked todos are closed and moved to `todo/done/` with resolution notes.

---

## The gate design (one paragraph)

`Database.mutate(functor, arity, *, author, kind, detail=None, through=None)`
is a context manager that opens a WRITE TRANSACTION on the `PredRow` for
`(functor, arity)` and yields it. On entry it asks the one policy —
`write_refusal(row, author, kind)`, a module-level function beside it — and a
refusal raises `refusal_error(...)`, the one refusal: the ISO
`permission_error(modify, static_procedure, F/A)` the `assertz/1` family
already raised, with its context extended to lead with the channel and then
name the author, the row key and the reason. On a clean exit it stamps
`row.record_write(author, kind, detail)` and, if the clause list changed while
no new dispatch was installed, invalidates the row (guarded on an existing
`_dispatch` entry, per Task 2's pin) and abolishes its table — so no channel
carries invalidation code of its own. `through` is the `PredicateMeta` a write
will go THROUGH when that class is not (yet) reading this row: an
`-import_from` shares the exporter's class, so its current row is part of the
write's blast radius and is asked the same question — which is also how the
ALIASED import is caught, where `module_dict.get(functor)` finds nothing.
Transactions NEST: a `mutate` naming a row already inside one inherits that
transaction's authorization and stamp, so the gate authorizes an OPERATION,
not a call (a load's `define_predicate → db.assertz` is the load's write, not
an anonymous runtime one). Authors are `Database.load_author()` — the
canonical SOURCE PATH, never a module name — and `Database.runtime_author()` —
`runtime-assert:<module>`; `PredicateMeta._mutate`/`_runtime_author` are the
class-side spellings, and `PredRow.mutate` the row-side one.

**The policy**, in `write_refusal`, three rules in order:

1. the OWNER may always write (`author == row.source[1]`) — a re-compile of
   the same file under any module name, from any channel;
2. a RUNTIME write (`assert`/`retract`) is refused by the LOCK — the ISO
   static-procedure refusal, unchanged in meaning from the per-channel
   `_locked` checks it replaces, now covering `Database.assertz` too;
3. a LOAD write (`load-clauses`/`load-dispatch`) may not overwrite somebody
   else's predicate — refused when the row has an owner and has clauses (or is
   locked). Narrowed exactly as step 3c was: an unowned row (the clause-free
   vocabulary export) and an owned but empty one are free to write.

`recompile` is deliberately never refused: recompiling a dispatch from the
clause list the row already holds changes no answers and takes no authorship.
What the dispatch channel must refuse is a LOAD installing its own dispatch
onto another module's predicate — `load-dispatch`, rule 3, which is the
aliased-import clobber.

### The four channels' routing

| todo's channel | routed at | surface exception |
|---|---|---|
| `_clauses[:] = …` (compiler_v2 step 4) | `_load_gate(...)` around `define_predicate` + the class install | `SyntaxError` — the gate line appended to `describe_imported_predicate_redefinition` |
| `_dispatch_fn` (step 5 / `compile_predicate_*`) | `_load_gate` around step 5; `db.mutate` around step 6's table-wrap; `compiler._install`; `Database.set_dispatch` | `SyntaxError` at load; `RuntimeError` for a raw install outside any transaction |
| `_signature`, `_clauses_source` | written INSIDE step 4's transaction | as above |
| `assertz` | `Database.assertz/asserta/retract` (new `author=` kwarg, defaulted to `runtime_author()`); `PredicateMeta._assertz/_asserta/_retract` (via `_gated`); the `assertz/1`/`asserta/1`/`retract/1` builtins | `LogicException(permission_error(...))`; `RuntimeError` at the class surface |

The `import_hook` "two deferred paths" the brief names **no longer exist** —
they went with the v1 pipeline (`613f29da`, "Delete the dead v1 import
pipeline"); `compiler_v2` step 4 is the sole wholesale clause-install site
(`grep` for `record_clause_source` / `_clauses[:]`). `record_clause_source`'s
docstring, which still named them (flagged in task-2-report), is corrected.

---

## Per checkbox

**1. `Database.mutate(...)` context manager returning the row in a
transaction; locked rows refuse non-owner authors with the existing
`permission_error` text; the aliased-import clobber becomes impossible because
`dispatch_fn` writes outside a txn RAISE.** Done. `PredRow.dispatch_fn`'s
setter raises `RuntimeError` naming the channel (`"dispatch install for f/1
outside a mutation transaction (channel: PredRow.dispatch_fn) — write it
inside Database.mutate(...)"`) when `row._txn == 0`. Writing `None` routes to
`invalidate()` instead and needs no transaction — it is not a clobber (a
cleared dispatch recompiles from the OWNER's clause list, so it can lose no
answers), and that keeps every `x._dispatch_fn = None` spelling in the tree
working while the INSTALL door is shut. The second door — `PredicateMeta.
_dispatch_fn`, the class property `compiler._install` writes through — is
closed by the same setter and pinned separately
(`test_a_dispatch_install_through_the_class_property_outside_a_txn_raises`).

**2. All four channels route through it; `assertz` provenance is per-write.**
Done, per the table above. Provenance:
`test_the_owner_load_stamps_the_row_with_its_source_path` and
`test_assertz_records_its_own_author_not_the_loading_module` (the todo's
"attributed to the loading module" defect: a runtime assert stamps
`runtime-assert:<module>`, and the test asserts it differs from the load
stamp on the same row).

**3. The step-3c guard reimplements ON the gate; delete what it replaces; the
three alias scenarios pinned.** Done.
`_reject_redefinition_of_imported_predicates` is DELETED (both the pre-pass
and its call site); its ownership test is rule 3 of `write_refusal`.
`_import_from_origins` survives as a RESOLVER — that is what the identity
todo asked for — and is documented as such; `_imported_class(origins,
functor)` hands the gate the class an aliased import bound. The three
scenarios are pinned as `test_alias_scenario_1_one_file_under_two_module_names
_is_not_refused`, `..._2_an_aliased_import_cannot_clobber_the_exporter`,
`..._3_a_second_implementer_of_a_vocabulary_is_refused`, and the eight older
tests in `tests/test_imported_functor_clause_clobber.py` are green UNCHANGED
through the gate.

**4. Acceptance (verbatim): each of the four channels attempted from a
non-owner load → refused with the same diagnostic; owner writes stamped;
`assertz` records its own author.** Done —
`test_channel_1_low_level_db_assertz_from_a_non_owner_is_refused`,
`test_channel_2_the_compiler_from_a_non_owner_is_refused_with_the_same_text`,
`test_channel_3_the_class_mutator_from_a_non_owner_is_refused`,
`test_channel_4_the_assertz_builtin_from_a_non_owner_is_refused`, each
asserting the same `"may not write <f>/<n>"` line through its own surface
exception; plus the two provenance tests above.

**5. Full suite: diff == ledger.** The failure-NAME set is BYTE-IDENTICAL to
the task-3 baseline (145 names, `comm` empty in both directions). Every
deliberate inversion was adapted in place rather than left failing, and each
is listed below.

---

## Diagnostic rewords (ledger)

The brief expects "the clobber-refusal diagnostics may reword — ledger them".

1. **`PredicateMeta._assertz/_asserta/_retract`.** Was `"Predicate f/1 is
   locked. Use dynamic() to allow runtime assertion."` Now the gate's text,
   e.g. `"_assertz: runtime-assert:m may not write f/1: it is a locked static
   procedure owned by /path/m.clausal — declare it -dynamic to assert against
   it"`. The exception CLASS is unchanged (`RuntimeError`); the word "locked"
   is deliberately kept in the reason, so the two tests that match on it
   (`test_builtin_classes`, `test_directives`) pass unedited.
2. **The `assertz/1`-family builtins.** The ISO term is unchanged
   (`error(permission_error(modify, static_procedure, f/N), Ctx)`); only `Ctx`
   grew, from `"assertz/1"` to `"assertz/1: <author> may not write f/N:
   <reason>"`. It still LEADS with the channel, which is the part of the old
   context a reader was using. One test asserted equality —
   `tests/audit_2026_07_05/test_09_builtins.py::_assert_static_procedure_error`
   — and now asserts `startswith`. **This is the only assertion in the tree
   reworded for the new text.**
3. **The load channel.** `describe_imported_predicate_redefinition`'s message
   is UNCHANGED and still raised as `SyntaxError`; the gate's one line is
   appended to it. Every existing assertion on that message (`"2 clause"`,
   `"-import_from"`, `"->"`, module names) passes untouched.
4. **The dispatch-install refusal** is new text with no predecessor
   (`RuntimeError`, naming the channel and `Database.mutate`).

---

## Full-suite gate

```
$ /workspace/clausal/venv/bin/python -m pytest tests -q \
      --continue-on-collection-errors -p no:cacheprovider
144 failed, 12150 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 101.33s
```
(run from the worktree; `clausal.__file__` asserted to contain
`p33-state-reloc` in-process before the run — the assertion is the `&&` guard
in the command)

```
$ grep -E "^(FAILED|ERROR) " task-3-full.txt \
    | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u > task-3-failed-names.txt
$ wc -l < task-3-failed-names.txt        # 145
$ comm -13 task-3-base-failed-names.txt task-3-failed-names.txt   # (empty)
$ comm -23 task-3-base-failed-names.txt task-3-failed-names.txt   # (empty)
```

**Gate diff: EMPTY, both directions.** The ledger of deliberate inversions is
therefore a ledger of tests I CHANGED so they keep passing, not of tests left
failing:

| test | what changed | brief line that mandates it |
|---|---|---|
| `tests/test_predrow.py::test_low_level_db_assertz_now_bypasses_the_static_lock_completely` | **FLIPPED and renamed** to `test_low_level_db_assertz_is_refused_on_a_locked_static_predicate`: `db.assertz` on a locked static predicate now raises the gate's refusal and the answers stay `[1]` (they became `[1, 2]` under Task 2). | "All four channels route through it: … `db.assertz/asserta/retract`" + Task 2's carry-forward note naming this test |
| `tests/test_predrow.py` ×5, `tests/test_predicate_meta.py` ×5, `tests/test_compiler_optimizations.py` ×1, `tests/test_predicate_arity_mismatch_diagnostic.py` ×1 | **ADAPTED**: a test-side dispatch INSTALL now opens a transaction (`db.mutate(...)` / `cls._mutate(...)`). Nothing else in them changed. | "`dispatch_fn` writes outside a txn RAISE … the property setter from Task 2 now requires an open txn" |
| `tests/audit_2026_07_05/test_09_builtins.py::_assert_static_procedure_error` | **REWORDED**: `==` → `startswith` on the `permission_error` context. | "the clobber-refusal diagnostics may reword — ledger them" |
| `tests/test_import.py::test_runtime_assertz_adds_clause` | **ADAPTED**: a deliberate low-level write to a LOCKED static predicate now names itself as the owning load (`author=db.load_author()`). | "each of the four channels attempted from a non-owner load → refused" — this caller is the owner, and now says so |
| `clausal/logic/builtins/_registry.py` ×2 | production, not a test: the builtin registry's dispatch install opens a transaction. | same as the dispatch-door line |

One flake was observed and is NOT in the final set: on the first full run
`tests/audit_2026_05_25/test_class_C17_perf_memory.py::test_F026_multi_star_
splits_bounded_for_moderate_input` failed and passed in isolation
(3.09s) — the known C17-perf timing flake family that is already in the
baseline's composition. It did not recur on the final run.

## TDD evidence

Tests first, in `tests/test_mutation_gate.py`, before any of
`Database.mutate` / the policy / the channel routing existed:

```
RED   $ pytest tests/test_mutation_gate.py -q     →  17 failed, 1 passed
```
(the one passing test was `test_alias_scenario_1_one_file_under_two_module_
names_is_not_refused` — the scenario that must KEEP working, so passing at RED
is the correct result for it.)

```
GREEN $ pytest tests/test_mutation_gate.py tests/test_imported_functor_clause_clobber.py -q
      →  30 passed
```

Intermediate RED evidence that the gate really bites, collected while wiring:
the builtin registry, `compiler._install`, `compiler_v2` steps 4/5/6 and ten
test sites each announced themselves with `RuntimeError: dispatch install for
<f>/<n> outside a mutation transaction` — i.e. the door was found closed by
the code that was writing through it, which is the property the task exists to
establish.

## Files changed

* `clausal/logic/database.py` — `PredRow._txn`, the `dispatch_fn` install
  guard, `invalidate` as the sole invalidation write, `PredRow.mutate`,
  `write_refusal`, `refusal_error`, the write-kind constants,
  `Database.module_name/load_author/runtime_author/mutate`, and
  `assertz/asserta/retract/set_dispatch` routed through the gate.
* `clausal/logic/predicate.py` — `PredicateMeta._mutate/_runtime_author/
  _gated`; `_assertz/_asserta/_retract` rewritten onto the gate;
  `record_clause_source` docstring corrected; a note on `_get_dispatch`'s
  deliberate direct dict write.
* `clausal/logic/compiler_v2.py` — step 3c's guard deleted; `origins` computed
  as a resolver; `_imported_class`, `_load_gate`, `_redefinition_error`,
  `_LOAD_SITES`; steps 4, 5 and 6 routed through the gate.
* `clausal/logic/compiler/predicate.py` — `_install`'s class writes inside a
  transaction (the second door).
* `clausal/logic/builtins/database_ops.py` — `_find_pred_cls` arity-checked;
  the three builtins routed through the gate; `retract/1` restructured so the
  transaction CLOSES BEFORE the yield (see concerns) with the search extracted
  as `_remove_first_match`; its channel-local invalidation deleted.
* `clausal/logic/builtins/_registry.py` — builtin dispatch installs gated.
* tests: `tests/test_mutation_gate.py` (new, 18 tests) + the seven files in
  the inversion ledger.
* `todo/done/a-shared-predicate-has-no-single-mutation-gate.md`,
  `todo/done/predicate-identity-is-keyed-on-spelling-not-on-the-class.md` —
  `git mv` + a `## Resolution (2026-09-05)` note each; the commit stat shows
  54% / 58% similarity, i.e. the notes are IN (a 100% rename would mean they
  were dropped).

## funnel-lint re-pin

Re-pinned once, as predicted: `AllowEntry("clausal/logic/database.py", (742,
774))` → `(1011, 1043)`. `head_key` is byte-identical; only its line number
moved, pushed down by the gate's policy block and `Database.mutate` earlier in
the file. The comment above the entry records the shift, as the four previous
ones do.

## `_find_pred_cls`

Fixed, and it did fall out of routing the builtins through the gate. It now
takes the arity and returns a class only when `len(cls._fields) == arity`, so
a `p/1` assert can no longer hand `p/3`'s class to the recompile — which,
since Task 2 made `_install` re-bind, would have MOVED `p/3`'s class onto
`p/1`'s row. The lock question it used to answer is the gate's now, and the
gate is asked about the ROW, so losing the wrong-arity class loses no check.

## Self-review

* **Completeness vs the five checkboxes** — walked above; all five done. The
  one brief item that could not be done as written is `import_hook`'s "two
  deferred paths", which no longer exist (evidenced by `git log -S`).
* **YAGNI** — the new public surface is `Database.mutate`, two author helpers,
  `module_name`, `PredRow.mutate`, `PredicateMeta._mutate/_gated/
  _runtime_author`, `write_refusal`, `refusal_error` and five kind constants.
  `PredRow.mutate` and `PredicateMeta._mutate` exist because a class knows the
  row it faces but not the `(db, functor, arity)` that names it (an alias
  binds a class under a name that is not its own) — both have real production
  callers (`_install` with `db=None`, `_registry`), not only tests.
* **Tests assert real behavior** — each channel test loads or builds the
  actual shape and asserts the ANSWERS did not move as well as the exception;
  the alias tests use the existing fixtures, so they exercise the real
  `-import_from` machinery.
* **Output pristine** — no debug prints, no skipped/xfail additions; the suite
  emits no new warnings (748, unchanged).
* **Hot path** — nothing added to `_get_dispatch` or the dispatch closures;
  the gate is entirely on the write path. The dispatch-plan 4-tuples are
  untouched, and `_get_dispatch`'s call signature and semantics are unchanged
  (the frozen duck type).
* **Checked and found sound**: nested transactions on partially-overlapping
  blast radii (only rows this call OPENED are checked, stamped and unwound);
  a `return` inside a `with` still runs the gate's exit (contextlib resumes
  the generator on `__exit__`); `Database("some-string")` callers (the author
  helpers read `module_dict` defensively — found by the suite, fixed).

## Concerns

1. **`retract/1` no longer holds the transaction across its yield.** The
   builtin is a generator; leaving a transaction open across a solution the
   caller may abandon would leak `_txn` and skip the exit invalidation. The
   search is now `_remove_first_match`, called inside the transaction, and the
   pattern-binding + `yield` happen after it closes. Behaviour is otherwise
   identical, and `test_retract_builtin_of_the_last_clause_leaves_no_answers`
   (Task 2's F4 pin) is green.
2. **`retract/1` now abolishes a tabled predicate's answers**, because the
   gate's exit does it for every clause-list change. It did not before (it
   deleted straight out of `db._clauses`). This is a correctness improvement
   consistent with `Database.retract`, but it is a behaviour change nothing
   pinned in either direction.
3. **The gate checks every step-4 predicate, not only imported ones.** Step 3c
   only looked at names in `origins`. A class that reaches `module_dict` by
   some route other than `-import_from` and is owned, with clauses, by another
   file would now be refused with the gate's line and no rich diagnostic
   (`_redefinition_error` falls back to the bare gate text when the functor is
   not in `origins`). Nothing in the suite hits it; it is a widening in the
   safe direction, but it is a widening.
4. **`_get_dispatch` still writes `db._dispatch[key]` directly** on the lazy
   recompile fallback. Deliberate and commented: it is the once-per-goal path,
   and what it stores is the row's own recompiled function — a `recompile`,
   which the policy never refuses.
5. **An author is a claim, not a credential.** `db.assertz(..., author=<the
   owner's path>)` is accepted, as `tests/test_import.py` now does on purpose.
   The gate is a structural guard against a load or a runtime assert
   clobbering a predicate it does not own by ACCIDENT, not a security
   boundary; nothing in the design pretends otherwise.
6. **Two classes bound to one row still share `locked`** (carried from
   task-2-report). Unchanged here; the gate consults the row, so it inherits
   the same limitation.

---

# Fix round 1 (2026-09-05)

Commit `f08a21d5` "P3-3 Task 3 fix round 1: the gate asks first, cleans up
always, and does not move a predicate". Three Important findings, all
reproduced as a failing pin BEFORE the fix, all in `tests/test_mutation_gate.py`.

## Important 1 — a refused load left another module's class half-written

**What was wrong.** The gate was consulted INSIDE step 4's write loop, so the
ordering property the deleted step-3c pre-pass carried was dropped. New
fixtures `tests/fixtures/gate_vocab.clausal` (exports a clause-free `gv_free/1`
and an owned `gv_owned/1`) and `gate_rival.clausal` (implements `gv_free`,
then redefines `gv_owned`) reproduce it: `gv_owned` is refused, the load
aborts, and `gvocab.gv_free` was left at 1 clause with `_clauses_source`
naming a module that never finished loading.

**What changed.** `write_refusal` is pure, so the load asks it about every key
it is going to write before writing any:

* `Database._write_rows(functor, arity, through, create)` — ONE definition of
  a write's blast radius, shared by the gate and the dry run, so a dry run
  cannot ask about a different set of rows than the write would touch.
* `Database.refusal_for(...)` — the dry run: returns the exception `mutate`
  would raise, or `None`. Opens no transaction, mints no rows.
* `compiler_v2` step 3d (`_refuse_foreign_writes`) — one `refusal_for` per
  distinct `(functor, arity)`, translated by the same `_redefinition_error`,
  before step 4's loop.

**Pin.** `test_a_refused_load_writes_nothing_at_all` — after the refused load,
`gv_free` has 0 clauses and `_clauses_source is None`, and `gv_owned` still
has its one clause.

## Important 2 — an exception inside a transaction skipped the exit

**What was wrong.** `_txn` was unwound in `finally`, but `record_write` and
the invalidation ran only on the clean path: a body that appended a clause and
then raised left the clause behind with the dispatch compiled from the old
list, and no stamp. Reachable through `assertz/1`, whose recompile runs inside
the transaction. Second symptom, same root: change detection compared clause
COUNTS, so one transaction that removed a clause and added another skipped
invalidation.

**What changed.** Both moved into the unwind. The stamp is written whatever
the outcome, with the detail marked `(failed)` when the body raised.
Invalidation is now driven by the KIND: `_CLAUSE_KINDS` (`load-clauses`,
`assert`, `retract`) invalidate unconditionally unless the transaction
installed a dispatch of its own on the way out (which is how the assert
channels' in-transaction recompile survives). No clause-list copy is taken on
the write path; the cost of invalidating a transaction that turned out to
write nothing is one lazy recompile.

**Pins.** `test_a_raise_inside_a_transaction_still_invalidates_and_stamps`
(dispatch cleared, stamp present and marked failed) and
`test_a_same_length_clause_edit_still_invalidates`.

## Important 3 — `recompile` moved predicate identity

**What was wrong.** `compiler._install` ran `pred_cls._bind_row(db, ...)`
inside a `recompile` transaction, and `recompile` is never refused. So an
importer's `assertz` against a shared `-dynamic` predicate moved the class
onto the IMPORTER's row: the owner's own query answered from the importer's
clause list while the owner's row still held its clause. Origin: Task 2's
`_bind_row` call in `_install`; my first closure note wrongly presented this
class of defect as closed.

**What changed** (per the controller's binding ruling):

* `PredicateMeta._bind_row(db, functor, arity, authorized=False)` is a POLICED
  write. A class already reading another Database's REAL row is left where it
  is; a class on its private DETACHED row is unbound, not foreign, so its
  first bind is always allowed; a re-bind within the same database (a name at
  two arities) is not a move and stays open. The one authorized caller is
  `compiler_v2` step 4's clause install — the write the gate has just cleared
  for this author — which is what keeps the clause-free vocabulary idiom
  working. `PredRow.detached` (set by `PredicateMeta._detached_row`) and
  `PredRow.db`/`key` are the accessors this needs.
* `compiler_v2` step 4a: a `-dynamic` declaration naming an IMPORTED
  predicate no longer binds that class or takes it into `pending`. The
  declaration still marks this database (so this module does not lock the
  shared class at step 7), but the predicate is not this module's to compile —
  binding it would have handed the owner's class this module's empty clause
  list and its always-fail trampoline. This is the third site the ruling's
  rule covers; it is `_bind_row` policing, not a widening into
  solve/module-resolution code.
* `builtins/database_ops.py`: `_home_db(db, pred_cls)` resolves an
  assert/retract to the row the CLASS is bound to (falling back to `db` when
  there is no class or the class is detached), so a write through a shared
  class lands in the owner's clause list — pre-P3-3 semantics.

**Pin.** `test_an_imported_dynamic_predicate_is_asserted_ON_ITS_OWNER` with
new fixtures `gate_dyn_owner.clausal` / `gate_dyn_user.clausal`: after the
importer's `assertz(gd_p(2))`, the owner answers `[1, 2]`, the importer
answers `[1, 2]`, the class is still bound to the owner's row, and the write
stamp on the owner's row names `runtime-assert:…gate_dyn_user`. Plus
`test_an_unauthorized_rebind_leaves_the_class_where_it_is` in
`tests/test_predrow.py` for the police itself.

## Commands and output

Covering tests (all green):

```
$ pytest tests/test_mutation_gate.py tests/test_predrow.py \
      tests/test_imported_functor_clause_clobber.py tests/test_import.py \
      tests/test_predicate_meta.py tests/test_directives.py \
      tests/test_builtin_classes.py tests/audit_2026_07_05/test_09_builtins.py \
      tests/test_funnel_lint.py -q -p no:cacheprovider
→ 360 passed, 8 xfailed   (before the two _bind_row adaptations below)
$ pytest tests/test_funnel_lint.py tests/test_mutation_gate.py tests/test_predrow.py \
      tests/test_imported_functor_clause_clobber.py tests/test_import.py -q
→ 137 passed
```

RED evidence: the four new pins failed together before the fixes
(`4 failed, 18 passed`), and each failed for its finding's reason — the
identity one raised the owner's `permission_error`/wrong-row symptom rather
than an assertion mismatch.

Full suite, once, foreground:

```
$ /workspace/clausal/venv/bin/python -m pytest tests -q \
      --continue-on-collection-errors -p no:cacheprovider
144 failed, 12155 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 110.04s
```
Saved as `task-3-fix1-full.txt` / `task-3-fix1-failed-names.txt` (145 names).
**Gate diff vs `task-3-base-failed-names.txt`: EMPTY both directions.**

## Fix-round inversions

| test | what changed | why |
|---|---|---|
| `tests/test_predrow.py::test_rebinding_carries_dynamic_arities_locked_and_source` | **ADAPTED**: its cross-database re-binds pass `authorized=True` — it stands in for the load-time clause install, and pins the carry-over, which is unchanged. | the `_bind_row` police (Important 3) |
| `tests/test_predrow.py::test_rebinding_leaves_the_old_rows_clauses_where_they_were` | **ADAPTED**, same one-word reason. | same |

Nothing else in the tree changed outcome.

## Files changed (fix round)

`clausal/logic/database.py` (`_write_rows`, `refusal_for`, exit hygiene,
`_CLAUSE_KINDS`, `PredRow.db/key/detached`), `clausal/logic/predicate.py`
(policed `_bind_row`, detached marker), `clausal/logic/compiler_v2.py` (step
3d, `_refuse_foreign_writes`, `_belongs_elsewhere`, step 4/4a binds),
`clausal/logic/compiler/predicate.py` (stale tabling comment refreshed),
`clausal/logic/builtins/database_ops.py` (`_home_db` for the three runtime
channels), `tests/test_mutation_gate.py` (+4 pins), `tests/test_predrow.py`
(2 adaptations, +1 pin), `tests/test_funnel_lint.py` (re-pin), four new
fixtures under `tests/fixtures/`, and both `todo/done/` closure notes
corrected.

## Remaining concerns after this round

* **An importer that does NOT declare `-dynamic` still locks a shared dynamic
  predicate at step 7** (`obj._lock()` over `module_dict`), so an assert
  through it is refused as a static procedure. That is pre-P3-3 behaviour
  (`_locked` was per-CLASS and the class is shared), not something this task
  changed, and it is why `gate_dyn_user.clausal` declares `-dynamic(gd_p/1)`.
  Worth a todo of its own; not in this round's scope.
* **`_home_db` compiles the owner's clause list against the ASSERTING
  module's globals** on the recompile, exactly as the pre-P3-3 code did. Only
  facts reach `assertz/1` (`_build_clause` rejects rules), so the bodies are
  Unify goals only — but it is the same "one dispatch, one globals_" tension
  the clause-clobber refusal exists to avoid, now visible on the runtime path.

---

# Fix round 2 (2026-09-05)

Three findings from the scoped re-review of fix round 1: two Important
defects introduced BY that fix (N1, N2) and one pre-existing defect of the
same family the controller ruled in scope (N3). All three reproduced as a
failing pin first. Nothing else touched: the whole round is
`clausal/logic/builtins/database_ops.py`, `tests/test_mutation_gate.py` and
four new fixtures.

## N1 — the recompile ran the OWNER's clauses in the ASSERTER's namespace

**What was wrong.** Fix round 1 resolved a runtime write through a shared
`-import_from`'d class to the owner's row (`_home_db`) and made `home`
supply both the clause list and the install target — but left
`globals_=module_dict` pointing at the ASSERTING module. So an importer's
`assertz` re-lowered the owner's whole predicate against the importer's
namespace and installed the result on the owner's row. A rule body calling
a helper the importer happens to redefine started answering from the
importer's helper: the owner's answers changed with nothing having been
written to them.

**What changed.** `database_ops.py:173-192` — new `_home_globals(db,
module_dict, home)`: the caller's `module_dict` when the write lands in
`db` itself, otherwise `home.module_dict` (the namespace the home
database's clauses were compiled in), falling back to the caller's only
when the home database has no module dict of its own (a bare
`Database()`, where it is the only namespace on offer). Threaded through
all three builtins: `assertz/1` (`:230, :236`), `asserta/1` (`:263, :269`),
`retract/1` (`:325, :334`).

## N2 — a NO-OP `retract/1` dropped the dispatch, the table and a stamp

**What was wrong.** The retract transaction opened BEFORE the search, and
fix round 1 made the gate's exit invalidate on the write KIND rather than
on what the body did. So a `retract/1` that matched nothing cleared the
compiled dispatch, abolished the tabled answers and stamped a `retract`
write that never happened. `Database.retract` (`database.py:678-681`) has
always pre-checked for a match and opened no transaction — the two retract
doors disagreed.

**What changed.** `database_ops.py:304-313` — the search runs first and
the transaction opens only when it found something. `_remove_first_match`
is split into a pure `_first_match_index` (`:348-383`, returns the index or
`-1`, removes nothing, leaves no bindings) and a `clause_list.pop(index)`
inside the transaction (`:329`). The length-only change detection fix round
1 removed is NOT reintroduced — the gate's kind-driven invalidation and its
`(failed)` stamp for a transaction that DID open are untouched.

## N3 — the ALIASED `-import_from` spelling still moved the owner's answers

**What was wrong.** The canonical functor a write is keyed on is the
CLASS's own name, which is not the spelling the goal used.
`-import_from(m, [alias(bo_p, AliasS)])` binds the exporter's class under
`AliasS` only, so `_find_pred_cls("bo_p", 1, module_dict)` found either
nothing (no `-dynamic` in the importer) or a local shadow class minted by
the importer's own `-dynamic(bo_p/1)`. Either way `_home_db` fell back to
the importer's database and the clause landed there under `('bo_p', 1)`,
while `compiler._install` still wrote the dispatch onto the shared class —
the OWNER's row. Owner answered `[5]` instead of `[1]`.

**What changed.** `database_ops.py:110-149` — `_find_pred_cls` takes the
goal's `head` term and resolves the class by IDENTITY: `AliasS(5)` is an
instance of the exporter's class, so `type(head)` IS the predicate whatever
it is spelled here. Accepted only when that class is reachable from this
module dict under some spelling (`any(v is own for v in
module_dict.values())`), so a term that merely passed through the module
cannot redirect a write to a predicate the module cannot see. The scan runs
only when the name lookup did not already agree (`named is not own`), so
the common path is unchanged and costs nothing extra. Call sites: `:219`,
`:260`, `:299`. 40 lines including docstring; `compile_predicate_trampoline`'s
signature untouched, so no BLOCKED condition was hit.

No new "is this row foreign" check was added — `_home_db` (fix round 1)
already answers it, and nothing here hand-copies `_bind_row`'s police.

## The three pins — RED then GREEN

New fixtures under `tests/fixtures/`, following the `gate_dyn_owner` /
`gate_dyn_user` pattern: `gate_shared_owner` / `gate_shared_user` (N1) and
`gate_alias_owner` / `gate_alias_user` (N3). N2's module is written by the
existing `_write_module(tmp_path, ...)` helper.

RED (the three pins against `f08a21d5`, i.e. with the production file at
HEAD and only the tests added — verified twice: once before any production
edit, and once again at the end by checking the production file out to HEAD
and restoring it, so the RED evidence matches the FINAL pin text):

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
      tests/test_mutation_gate.py -q -p no:cacheprovider \
      -k "shared_class_keeps or noop_retract or aliased_import_asserts"

E       AssertionError: the owner's rule still resolves the OWNER's shared_helper
E       assert ['user_value', 9] == ['owner_value', 9]
E         At index 0 diff: 'user_value' != 'owner_value'

E       AssertionError: no match, so no invalidation
E       assert None is <function make_tabled_wrapper_trampoline.<locals>.tabled_dispatch at 0xe19afd260f40>
E        +  where None = PredRow(backend='python', locked=False, source=('gate_noop_retract', …),
E            writes=[…, WriteStamp(author='runtime-assert:gate_noop_retract', kind='retract',
E            detail='retract/1')], dynamic_arities={1}, detached=False).dispatch_fn

E       AssertionError: the owner keeps its clause and sees the new one
E       assert [1] == [1, 5]
E         Right contains one more item: 5

FAILED tests/test_mutation_gate.py::test_an_assert_through_a_shared_class_keeps_the_owners_namespace
FAILED tests/test_mutation_gate.py::test_a_noop_retract_is_not_a_write
FAILED tests/test_mutation_gate.py::test_an_aliased_import_asserts_ON_ITS_OWNER
3 failed, 22 deselected, 2 warnings in 0.43s
```

Each failed for its own finding's reason: N1 on the owner's ANSWERS moving
to the importer's helper, N2 on the dispatch being `None` after a retract
that matched nothing (with the phantom stamp visible in the row repr), N3
on the owner's clause list not having grown.

GREEN:

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
      tests/test_mutation_gate.py -q -p no:cacheprovider \
      -k "shared_class_keeps or noop_retract or aliased_import_asserts"
3 passed, 22 deselected, 2 warnings in 0.49s

$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
      tests/test_mutation_gate.py -q -p no:cacheprovider
25 passed, 2 warnings in 0.44s
```

Neighbourhood, all green and unedited:

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest \
      tests/test_mutation_gate.py tests/test_predrow.py \
      tests/test_imported_functor_clause_clobber.py tests/test_import.py \
      tests/test_predicate_meta.py tests/test_directives.py \
      tests/test_builtin_classes.py tests/audit_2026_07_05/test_09_builtins.py \
      tests/test_funnel_lint.py -q -p no:cacheprovider
367 passed, 8 xfailed, 3 warnings in 2.92s
```

One assertion inside the N2 pin was corrected after its first GREEN run:
the "a matching retract still invalidates" half originally asserted
`row.dispatch_fn is None`. That is wrong — when clauses remain, the
builtin recompiles inside the transaction, so the row carries a NEW
dispatch rather than no dispatch. The pin now asserts the real behaviour
(`row.dispatch_fn is not dispatch_before`, the table abolished, one
`retract` stamp, one clause left, answers `[2]`), and the RED run above is
of that final text.

## funnel-lint re-pin

None needed. `tests/test_funnel_lint.py` pins line ranges in
`clausal/logic/database.py`, which this round does not touch (the working
tree shows only `database_ops.py` and the tests modified); that file's
test is green in the neighbourhood run above.

## Full suite

```
$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -c \
      "import clausal; assert clausal.__file__.startswith('$PWD')"
engine OK: /workspace/clausal-bug-fix/.claude/worktrees/p33-state-reloc/clausal/__init__.py

$ PYTHONPATH=$PWD /workspace/clausal/venv/bin/python -m pytest tests -q \
      -p no:cacheprovider --continue-on-collection-errors \
      | tee .superpowers/sdd/p33-state-relocation/task-3-fix2-full.txt
…
FAILED tests/test_clpsat.py::TestErrorPaths::test_tseitin_unsupported_node - …
FAILED tests/test_clpsat.py::TestErrorPaths::test_expr_to_literal_bad_int - I…
FAILED tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks - Asse…
ERROR tests/test_clportools.py - NameError: name '_CpSolverSolutionCallback' …
144 failed, 12158 passed, 56 skipped, 39 xfailed, 748 warnings, 1 error in 106.28s (0:01:46)
```

(`-x0` was dropped — pytest rejects it. Passed count is 12158 vs fix round
1's 12155: the three new pins.)

```
$ grep -E '^(FAILED|ERROR) ' …/task-3-fix2-full.txt \
    | sed -E 's/^(FAILED|ERROR) //; s/ - .*//' | sort -u \
    > …/task-3-fix2-failed-names.txt
$ wc -l < …/task-3-fix2-failed-names.txt
145
$ comm -3 <(sort …/task-3-base-failed-names.txt) …/task-3-fix2-failed-names.txt
[END OF COMM OUTPUT]
```

The `comm` produced NO lines — the failure-name set is byte-identical to
the 145-name baseline in both directions.

## Files changed

* `clausal/logic/builtins/database_ops.py` — `_find_pred_cls` takes the
  goal's head and resolves by class identity; new `_home_globals`;
  `retract/1` searches before it opens a transaction, with
  `_remove_first_match` split into the pure `_first_match_index`.
* `tests/test_mutation_gate.py` — three pins appended
  (`test_an_assert_through_a_shared_class_keeps_the_owners_namespace`,
  `test_a_noop_retract_is_not_a_write`,
  `test_an_aliased_import_asserts_ON_ITS_OWNER`).
* `tests/fixtures/gate_shared_owner.clausal`,
  `tests/fixtures/gate_shared_user.clausal`,
  `tests/fixtures/gate_alias_owner.clausal`,
  `tests/fixtures/gate_alias_user.clausal` — new.

No inversions: nothing in the tree changed outcome.

## Self-review

* **Completeness** — all three findings fixed, each with a pin that
  asserts the behaviour named in the finding: the owner's ANSWERS (N1, N3),
  the table-store SIZE and the `row.writes` LIST (N2). No mocks; every pin
  loads real modules through the real `-import_from` machinery and calls
  real goals.
* **Scope** — one production file, three functions plus three call sites.
  No new "foreign row" predicate (the ruling's one policy is `_bind_row`'s,
  and `_home_db` from fix round 1 already answers the home question); no
  change to `_get_dispatch`, to the 4-tuple dispatch plans, to
  `eval_harness`, or to `compile_predicate_trampoline`'s signature; no new
  runtime namespace names, so no `STRICTNESS_EXEMPT_RUNTIME_NAMES` entry.
* **Hot path** — `_find_pred_cls`'s new scan runs only when the name lookup
  disagrees with the term's own class, i.e. only on the aliased/shadowed
  path; the common assert short-circuits on `named is own`. The suite ran
  106s against fix round 1's 110s.
* **Checked and found sound**: `clause_list.pop(index)` pops the SAME list
  object the row reads (`home._clauses[key]`, which `PredRow.clauses`
  re-reads live), and nothing runs between the search and the pop;
  `_find_pred_cls(head=None)` — `type(None)` is not a `PredicateMeta`, so
  every existing caller shape still resolves by name; a refusal raised on
  `mutate`'s entry can no longer reach the old unbound-`removed` path
  because the search now happens first.
* **Output pristine** — no debug prints, no skips, no xfails, warning count
  unchanged at 748.

## Concerns

1. **An aliased import with NO `-dynamic` in the importer now RAISES where
   it used to silently move the owner's answers.** Probed: an importer with
   only `-import_from(m, [alias(bo_p, AliasS)])` doing `assertz(AliasS(X))`
   now gets `permission_error(modify, static_procedure, bo_p/1)` —
   "runtime-assert:gau may not write bo_p/1: it is a locked static
   procedure owned by …/gate_alias_owner.clausal". The lock is the
   PRE-EXISTING round-1 concern (an importer that does not declare
   `-dynamic` locks the shared predicate for its owner at step 7, already
   parked as
   `todo/importer-without-dynamic-locks-shared-dynamic-predicate-for-its-owner-2026-09-05.md`),
   now visible because the write finally resolves to the owner's row. The
   refusal is the right side of the trade — the owner's answers stop
   moving — and `gate_alias_user.clausal` declares `-dynamic(bo_p/1)` for
   exactly the reason `gate_dyn_user.clausal` does. Nothing in the suite
   hit it.
2. **`_home_globals` falls back to the caller's `module_dict` when the home
   database has no module dict.** That is the shape a bare `Database()`
   presents, and there is no other namespace on offer, so the fallback is
   the only option that keeps the bodies resolvable — but it is the one
   corner where N1's defect could still be reached. No production path
   reaches it (a module database always has its dict).
3. **Identity resolution is scoped by reachability from `module_dict`,
   not by the import graph.** A class bound in the module dict under ANY
   spelling wins over a same-named local class. That is the intended
   ruling for the alias case, but it also means a module holding both its
   own `p/1` and an imported `p/1` class under different names now routes
   a `p/1` assert by which class BUILT the term rather than by which name
   is bound. That is the "one predicate = one class" semantics the task is
   establishing; it is nonetheless a widening.
4. **`_belongs_elsewhere` in `compiler_v2.py` is still a second hand-copy
   of `_bind_row`'s police**, as the reviewer flagged. Ledgered for later,
   deliberately untouched here; nothing in this round adds a third.
