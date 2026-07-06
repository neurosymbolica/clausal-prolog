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
