# A seam clause body nested about 170 deep raises a raw RecursionError

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
