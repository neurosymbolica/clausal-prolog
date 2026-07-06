# fix(A06-F011): sum_/scalar_product silently ignore Python-spelled ops

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F011
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestSumOpStrings::test_python_style_ops_post (xfail — flip to pass)
**Gated by:** A06-D002 (op vocabulary) — recommendation: accept both, raise on unknown.

## Bug

`_FD_OPS` (clpfd.py:1983-1997) accepts Prolog spellings (`#=`, `=`, `#<`,
`=<`, `>=`, `\=` …) but NOT the language's own operator spellings: `"<="`,
`"=="`, `"!="` fall through `op_fn is None` (clpfd.py:2027-2029, :2084-2086)
into a bare `return` — the builtin yields nothing, indistinguishable from
"no solution":

    sum_([X, Y], "<=", 6)   # 0 solutions, no error

## Fix direction

Add `"<=": le, "==": eq, "!=": ne` to `_FD_OPS` and to
`_op_to_binary_constraint` (clpfd.py:2000-2013). Replace the silent
`return` on unknown op with `raise ValueError(f"unknown sum_ op {op_str!r}")`
— failure-as-no-op hides typos forever in a cut-free language.

## Acceptance

- xfail passes; Prolog-spelled guard stays green; unknown op ("=>") raises.
- docs/constraints.md builtins table documents the accepted set.
