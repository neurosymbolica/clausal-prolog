# investigate(A10-F004) [Opus]: clause on an -import_from name silently replaces the source module's predicate

**Problem.** If module B does `-import_from(lib, [twice])` AND defines a
clause `twice(0, "zero") <- (1 is 1)`, then after B loads, `lib.twice` loses
its own solutions process-wide — `lib.twice(4, B)` goes from `[8]` to `[]`;
only B's clause survives (class `_clauses` shows 1 clause). Silent cross-module
corruption.

**Mechanics (as observed).** `EmbedTransformer.visit_Expr` derives the head
functor from the raw Name without consulting `_import_remap`, and the imported
class is already bound to that name in module globals, so `_make_functor_class_ast`'s
guard sees a matching `PredicateMeta` and skips minting a local class. The
compile pipeline then compiles B's clause list (only B's clauses) and installs
the dispatch on the SHARED imported class (compile_module / `$define_predicate`
sync — A03 territory).

**Repro/test.** test_10_rewriting_import.py::test_F004_local_clause_does_not_clobber_imported_predicate
(xfail); control ::test_F004_guard_plain_import_does_not_disturb_source.

**Decision needed (A10-D003, parked).** (a) load-time error on head/import
name collision (recommended — implicit cross-module mutation should not
exist; explicit `assertz` remains available and documented), (b) extend the
imported predicate (docs' assertz phrasing suggests class-owned clauses), or
(c) mint a distinct local shadow predicate.

**Investigate.** Where exactly the dispatch replacement happens in
compiler_v2 (whether B's db is missing lib's clauses or the class sync drops
them); whether `assertz/1` on an imported class takes a different (correct,
extending) path; interaction with `-dynamic` and locking; A11's module
semantics session should co-own the decision.

---

## RESOLVED — 2026-08-25

Fixed on branch `fix/imported-functor-clause-list-2026-08-25`, together with
the independently-filed `todo/imported-functor-clause-list-replaced-not-extended.md`
(same bug, found twice).

**A10-D003 answered: (a) load-time error.** Not (b) — extending the imported
predicate is unavailable, because `compiler_v2` step 5 compiles ONE dispatch
function from ONE clause list against ONE `globals_` mapping, so a merged list
would compile the exporter's clause bodies in the importer's scope. Not (c) —
a distinct local shadow would break the corpus idiom in which a *third* module
importing a clause-free vocabulary functor must reach the downstream
implementer's clauses (live in two downstream rulebase modules). Full reasoning and the
corpus sweep are in `todo/done/imported-functor-clause-list-replaced-not-extended.md`.

The refusal is narrowed to functors that already have clauses, so the
declare-here/implement-there idiom is untouched.

**Answers to the "Investigate" items:**

- *Where the dispatch replacement happens.* `compiler_v2.compile_module` step 4:
  `pred_cls._clauses[:] = db.clauses_for(functor, arity)` on the class
  `module_dict[functor]` — which, for an `-import_from`'d name, IS the
  exporter's class. The importer's `db` never held the exporter's clauses; the
  assignment (not the compile) is what destroys them, and step 5 then compiles
  a dispatch from the truncated list and installs it on the shared class. The
  refusal is therefore inserted as step 3c, *before* step 4 mutates anything.
- *Whether `assertz/1` takes a different path.* It does, and it is already
  safe: `permission_error(modify, static_procedure, F/N)` fires on an imported
  predicate, even when the exporter declares `-dynamic`. Now pinned by
  `tests/test_imported_functor_clause_clobber.py::TestRuntimeAssertzIsAlreadySafe`.
- *Interaction with `-dynamic` and locking.* None beyond the above; the check
  reads clause ownership, not lock state.

`tests/audit_2026_07_05/test_10_rewriting_import.py::test_F004_local_clause_does_not_clobber_imported_predicate`
is no longer `xfail` — it asserts the refusal and that the library keeps its
own solutions. The `::test_F004_guard_plain_import_does_not_disturb_source`
control is unchanged and still passes.
