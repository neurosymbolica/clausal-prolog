# P3-3 Task 2 — inversion ledger

Format: `<test id> | <what changed> | <citation>`

## Inversions: NONE

The full-suite failure-NAME set is byte-identical to
`baseline-failed-names.txt` (144 names, `diff` exit 0 — see
`task-2-failed-names.txt` and the gate section of `task-2-report.md`). No
existing test changed outcome in either direction, so this ledger has no rows.

That is not the shape the brief predicted, so the absence is evidenced rather
than merely asserted. The brief expected three families of inversion; each is
accounted for below, with the probe that shows the behavior really did change
even though no test was pinning it.

| Predicted inversion | Did the behavior change? | Was any test pinning it? |
|---|---|---|
| dual-store shape pins (`cls._clauses is not db._clauses[key]`) | YES — for a BOUND class the two are now the same list object. Probe (`scratchpad/red_probe.py`) run against the reverted tree prints `cls._clauses IS db._clauses[key]: False`; the same probe on a bound class after the change prints `True` (new test `test_bound_class_clauses_is_the_database_row_list_itself`). | NO. Nothing in the 12 323 collected items asserted the two stores were distinct — unsurprising, since the separation was an implementation accident nobody would want to pin. |
| `_pred_cls_for` behavior pins | YES — the method is deleted and the arity-blind mirror with it. Probe against the reverted tree: `has _pred_cls_for: True`, and `db.assertz` of a `p/1` clause leaves `p/3`'s class holding **1** clause. After: the method is gone and the count is **0** (new tests `test_assertz_no_longer_appends_onto_an_arity_mismatched_class`, `test_retract_no_longer_reaches_into_an_arity_mismatched_class`, `test_database_no_longer_has_pred_cls_for`). | NO. `grep -rn "_pred_cls_for"` over the whole repo returned only `clausal/logic/database.py` — the method was never named by a test. The arity-blind append it performed was a latent defect (identity todo instance 3), not an asserted behavior. |
| `_clauses_source` load-attribution shape pins | NO CHANGE in value or shape — only in storage. `record_clause_source` still writes `pred_cls._clauses_source = (module_name, path)`; the property now lands it on `row.source`, and step 3c reads back the identical tuple from the identical class. Verified end to end on a real load: `db.row("pfn_greeting", 1).source == ('tests_pfn_sync', '/tmp/.../pfn_sync.clausal')`. | N/A. |

Two further deliberate semantic changes are recorded here because they are real
even though nothing inverted; both are argued and evidenced in
`task-2-report.md` under "Deliberate semantic changes":

1. `retract/1` (builtin, `builtins/database_ops.py`) now invalidates the ROW's
   dispatch after a removal instead of only the class's, and does so
   unconditionally rather than only when an identity match was found in the
   class's parallel list. Without this the deleted mirror would have silently
   dropped the invalidation the old loop performed.
2. The low-level `Database.assertz`/`asserta`/`retract` no longer skip LOCKED
   predicates when propagating to the class. Every lock ENFORCEMENT point is
   unchanged (`PredicateMeta._assertz/_asserta/_retract` and the
   `assertz/1`-family builtins all still raise before touching anything); what
   is gone is only the old skip's side effect of leaving a locked class's
   in-memory list disagreeing with `db.clauses_for`, which a recompile already
   resolved in the Database's favor.

---

# Fix round 1 — inversions

Four rows, all of them tests I own (three from Task 1, one from Task 2), all
caused by the ONE ruling that changes read semantics: **F2 — `PredRow.clauses`
loses its `setdefault`; reading mints nothing; `ensure_clauses()` is the single
promotion point.** No test outside `tests/test_predrow.py` changed outcome:
the full-suite failure-NAME set is still byte-identical to
`baseline-failed-names.txt` (`diff` exit 0, 144 names —
`task-2-fix1-failed-names.txt`).

`<test id> | <what changed> | <citation>`

| test id | what changed | citation |
|---|---|---|
| `tests/test_predrow.py::test_row_clauses_first_read_lazily_vivifies_is_defined` | **INVERTED, renamed to `test_row_clauses_read_does_not_vivify_is_defined`.** Task 1 pinned that a plain `row.clauses` read `setdefault`s the entry into existence and flips `is_defined` False→True, documenting it as an accepted narrow side effect *because only `PredRow` read the property*. Task 2 routed every `PredicateMeta._clauses` read through it, so `__repr__`, `_clause_arity`, `_declared_arity` and the compiler's inspections all became minting sites. The test now pins the opposite — three repeated reads leave `is_defined` False and the key absent — plus that the same list object comes back each time. | fix-round ruling F2; `PredRow.clauses` docstring; task-1-report.md's original "intentional, narrow side effect" note, now retracted |
| `tests/test_predrow.py::test_row_clauses_append_visible_via_clauses_for` | **ADAPTED.** Was `row.clauses.append(c)` then `clauses_for == [c]`; that now appends to an unminted per-row list the Database cannot see. Rewritten onto `row.ensure_clauses().append(c)`. Split so nothing is lost: two NEW tests pin the other half — `test_appending_to_an_unminted_read_is_invisible_until_promotion` (invisible until promoted, and the promotion is identity-preserving so the append survives) and `test_ensure_clauses_is_idempotent_and_keeps_the_existing_entry`. | fix-round ruling F2 |
| `tests/test_predrow.py::test_row_self_heals_across_wholesale_backing_dict_wipe` | **ADAPTED.** Its post-wipe assertion `row.clauses is db._clauses[("f", 2)]` only ever held because the read itself re-created the entry; it now raises `KeyError`. Replaced with `("f", 2) not in db._clauses` plus the unchanged `row.clauses == []` / `row.dispatch_fn is None`, and the re-aliasing claim moved to where it is now true — after the subsequent `db.assertz`, where `row.clauses is db._clauses[("f", 2)]` is asserted. The property under test (no stale clause survives a wipe; the row self-heals) is pinned exactly as before. | fix-round ruling F2 ("after a wipe, next ensure/mutation re-aliases; plain reads on a wiped key return the cached list without minting") |
| `tests/test_predrow.py::test_bound_class_clauses_is_the_database_row_list_itself` | **ADAPTED** (Task 2's own). Asserted `p._clauses is db._clauses[("p", 1)]` straight after `_bind_row`; binding mints nothing, so the subscript raises `KeyError`. Now asserts class/row agreement pre-mint (`p._clauses is db.row("p", 1).clauses`, key absent), then does the `db.assertz` and re-asserts the full three-way identity. The "one list, not two" claim is unweakened — it is made where a clause list exists to make it about. | fix-round ruling F2 |

## Fix round 1 — behavior restored, not changed

`F1` (the instance face) is a **restoration**, not an inversion: before Task 2
an instance resolved the seven names by the ordinary MRO walk onto the plain
class attribute, and the metaclass-property move silently broke that (7/7
`AttributeError` on the reviewer's probe). The plain class-level properties
injected into every predicate class's namespace put it back, LIVE. Nothing was
pinning it — hence no inversion, and hence the new pins
`test_instances_still_resolve_all_seven_relocated_attributes`,
`test_instance_reads_of_all_seven_are_live_through_the_class`,
`test_instance_writes_to_the_relocated_names_still_refuse` (writes raised
`AttributeError` at base too, so the instance face is read-only on purpose) and
`test_a_field_named_like_a_relocated_attribute_stays_a_field`.

## Fix round 1 — carry-forward for Task 3

Deliberate semantic change #2 in the list above is now **pinned and named** by
`test_low_level_db_assertz_now_bypasses_the_static_lock_completely`:
`Database.assertz` on a LOCKED static predicate is a COMPLETE static-lock
bypass (it was a PARTIAL one — the dual store accidentally kept solve()
answering the old clause set), and it is ANSWER-CHANGING: `[1]` becomes
`[1, 2]`. Task 3's mutation gate (`Database.mutate` — "checks lock/permission
once, stamps provenance per-write") is where the door gets closed; that test is
the one to flip when it does.
