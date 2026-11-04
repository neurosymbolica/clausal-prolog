# A seam clause body nested about 170 deep raises a raw RecursionError

**Status: FIXED 2026-11-04 (commit 7346fe76).** The deep copy in `_lower_dict_reads` is now an explicit-stack copy byte-identical to `copy.deepcopy` (`clausal/templating/ast_walks.py`), so a bracketed body loads up to CPython's own parser limit (197 levels of `('f', ...)`, 199 of `[...]`); what still recurses (the term rewriter, goal expansion, `compile()`/`ast.parse` of very long operator or `and`/`or` chains) is refused as a `SyntaxError` naming `resource_error(stack)` and the line. Pinned in tests/test_seam_deep_nesting.py::test_a_seam_body_nested_180_deep_loads_and_runs and ::test_a_seam_item_nested_too_deep_is_refused_with_its_line.

Found: 2026-11-04, while fixing the deep ground call-argument load failure
(`tests/test_deep_literals.py::test_a_deep_ground_call_argument_loads_and_runs`).
Severity: low. The seam cannot spell data much deeper than this anyway:
CPython's own parser refuses a source expression nested about 200 deep
(`MemoryError: Parser stack overflowed`).

## What / Repro

```seam
-module(m, [t])
t <- (X is ('f', ('f', ... 'a' ...)), X is X)      # ('f', ...) nested 170 deep
```

160 levels load and run; 170 levels raise `RecursionError: maximum recursion
depth exceeded` out of the import, with no source position, from
`copy.deepcopy` of the clause body in
`clausal/templating/term_rewriting.py::_lower_dict_reads`. The same depth in
a `.pl` or `.clausal` file (and up to 100k levels through `assertz/1`)
compiles, as a deep literal (`clausal/logic/compiler/deep_literals.py`).

Expected: either it loads, as below 160, or the item is refused with
`resource_error(stack)` and a position, as the ISO reader does for a term
nested too deep to read.
