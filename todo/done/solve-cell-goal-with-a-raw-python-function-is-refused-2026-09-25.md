# solve() refuses a raw Python function inside a cell goal (2026-09-25)

Pre-existing and not caused by the -meta_predicate branch; parked for the
operator. `solve(("c1", 2, fn, OUT), m)`, where `fn` is a simple-mode Python
goal function, raises `NotImplementedError: term_to_ast_expr: unsupported term
type function`, with or without a -meta_predicate declaration on `c1`. The same
function works through `call("c1", 2, fn, OUT, module=m)`. Pinned alongside in
`tests/test_meta_predicate_directive_both_eras.py` (Python-written closure
section).

## Closed 2026-09-30

Fixed on fix/todo-batch-3-2026-09-30: `_parameterize_opaque` passes a plain
Python function value (function, builtin, bound method, functools.partial --
nothing with `_get_dispatch`) in an ARGUMENT position by reference, as it
already did an opaque object; a cell's functor slot is never touched.
`solve(("c1", 2, fn, OUT), m)` now answers what `call("c1", 2, fn, OUT)`
answers. Pinned in tests/test_meta_predicate_directive_both_eras.py
(`test_a_python_written_closure_in_a_solve_cell_goal`, one and two meta hops,
library and importer).
