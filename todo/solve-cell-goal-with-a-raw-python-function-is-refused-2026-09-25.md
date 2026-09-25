# solve() refuses a raw Python function inside a cell goal (2026-09-25)

Pre-existing and not caused by the -meta_predicate branch; parked for the
operator. `solve(("c1", 2, fn, OUT), m)`, where `fn` is a simple-mode Python
goal function, raises `NotImplementedError: term_to_ast_expr: unsupported term
type function`, with or without a -meta_predicate declaration on `c1`. The same
function works through `call("c1", 2, fn, OUT, module=m)`. Pinned alongside in
`tests/test_meta_predicate_directive_both_eras.py` (Python-written closure
section).
