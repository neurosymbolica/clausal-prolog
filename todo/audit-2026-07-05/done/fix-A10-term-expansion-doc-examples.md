# fix(A10-F008): term_expansion.md q()-pattern examples are non-functional

**Problem.** The TE engine matches patterns against whole `Predicate` nodes
(`clausal/logic/term_expansion.py` protocol: "TERM: runtime Predicate node"),
but three doc snippets (`tests/fixtures/docs/term_expansion_sigs.txt`:
quick_example, suppressing_items, quasi_quotation) match with bare
`q(fact(X))` Call patterns — which never unify with a Predicate item. Executed
verbatim: quick_example doesn't even load (`NameError: TermExpansion` — the
multi-line fact is missing its trailing comma); with the comma added, no
expansion happens (fact/1 stays 1, logged_fact/1 = 0); the suppression example
leaves `debug/1` in place. No in-tree test covers q()-in-head TE patterns —
the 25 passing tests all use the var-pattern idiom
(`TermExpansion(TERM, [TERM, TERM], S, S)`).

**Repro/test.** test_10_rewriting_import.py::test_F008_te_doc_quick_example,
::test_F008_te_doc_suppression_example (xfail);
guard ::test_F008_guard_te_var_pattern_one_to_many.

**Fix (two layers).**
1. Docs now: add the trailing comma; either rewrite the three snippets to the
   working var-pattern idiom or clearly mark q()-head matching as not yet
   functional. Snippets should be executed (doc_snippet_check.py) like the
   cheat-sheet's.
2. Engine (A10-D004, parked): make a non-Predicate pattern match `item.head`
   for fact items (option (a)) — or reify items into the reflection vocabulary
   (option (c), interacts with A03-D001/A01-D004). Engine file belongs to the
   compile pipeline, coordinate at the A12 seam.
