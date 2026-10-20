# sum_/3 and scalar_product/4 silently post nothing for `<=`, `==`, `!=` or an unknown operator (A06-F011, A06-D002)

**Status: open, gated on design decision A06-D002 (unruled).** Triaged
2026-10-20, moved from the 2026-07-05 audit folder (was
`fix-A06-sum-op-strings.md`). Re-probed: the operator is now an atom
(`mint("<=")`), and `fd_sum([X, Y], Op, 6)` over `X, Y in 1..5` still yields
0 solutions, with no error, for `<=`, `==`, `!=` and the unknown `=>`. The
pinning test was renamed with its class:
tests/audit_2026_07_05/test_06_clpfd.py::TestSumOpAtoms::test_python_style_ops_post
(XFAIL). The code moved: `_FD_OPS` is at `clausal/logic/clpfd.py:3218`,
`_op_to_binary_constraint` at :3273, and the silent returns at :3303/:3307
(`sum_`) and :3376 (`scalar_product`).

The original audit text follows.

> **DEFERRED (2026-07-07):** intentionally not implemented — gated on the parked
> design decision A06-D002 (op-string vocabulary), which per standing mandate is
> the USER's call and goes to a todo, never asked interactively. The
> recommendation ("accept both spellings + raise on unknown") is clear and the
> fix is low-risk/additive, but the direction is still a policy call. Flip once
> D002 is answered. See
> `todo/done/investigate-A06-parked-design-decisions.md` §2.

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
