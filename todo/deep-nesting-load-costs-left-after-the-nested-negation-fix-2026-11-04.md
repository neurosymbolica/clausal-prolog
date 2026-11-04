# Deep nesting: load costs left after the nested-negation fix

**Found:** 2026-11-04, while closing
`todo/done/load-time-doubles-per-nested-negation-mark-undo-invariant-2026-10-16.md`.
The compiler passes are now linear in the size of the code they make (about
11-22 us per generated AST node at every depth measured, 4 to 96). These
costs remain. None is exponential.

## 1. CPython compiles a deep constant `source_body` tuple in cubic time

`iso_l3._source_body_kw` stores the clause body as read (for `clause/2`) as a
nested tuple display. A run of 32 or more goals joined by the same operator (`_FLAT_CHAIN`) becomes
a `$right_nested(...)` call, but a body that nests deep through
`\+`/`findall`/`->` with shorter runs at each level is one constant tuple that
deep. CPython's constant folding of nested tuples is about cubic in the
depth: a bare 1000-deep `(',', g, (',', g, ...))` constant takes 2.5 s to
`compile()`, 250-deep takes 0.05 s.

Measured: `c :- \+ \+ (g(1) x 20, \+ \+ (...))` 64 levels deep (about 1400
nested tuples): 7.5 s of its 9.5 s load is that one `compile()` of the module
code; the predicate itself compiles in about 2 s.

Possible fix: when the constant depth passes a bound (a few hundred),
build the term with a call (like `$right_nested`) instead of a display, so
no constant is that deep. It changes the module code of such clauses only.

## 2. Nested catch/3 code is quadratic in size

Each `catch/3` keeps a `_catch_inN` flag, and every answer yielded inside
`k` nested catches clears and resets all `k` flags, so `catch(catch(...))`
`d` deep makes O(d^2) statements: 586 AST nodes at depth 4, 23944 at 64,
48160 at 96 (1.1 s). A linear scheme (for example one depth counter
compared by each handler) would change the generated code.

## 3. A long conjunction inside another long conjunction is never segmented

`body_segments.fold_sequence` folds a sequence plain, and refolds it in
segments only when it nests too deep. Segments that a nested sequence made
during the discarded plain fold are never reached, so `hoist_segments`
always refused such a predicate and it was rebuilt without segments (by
`codegen.split_deep_nesting`). The fold now refuses as soon as it sees this,
instead of first refolding (which was exponential), and the code is the same
as before. But such a clause still goes through the outliner, whose
`localise` remains quadratic in the size of one function's scope (`can_own`
scans the scope's statement lists per name).

**Status of this item: FIXED 2026-11-04 (commit 10c60d0b).** The refold now
calls the chain the nested conjunction's own fold made instead of lowering
it again, so such a body is cut into segments (no refusal, no outliner) and
every conjunction is folded at most twice. Pinned in
tests/test_body_segments.py::test_a_long_conjunction_in_a_refolded_one_is_cut_too,
::test_nested_long_goals_on_the_production_path and
::test_a_nested_catch_in_a_body_too_long_for_the_outliner. Items 1 and 2
remain open.
