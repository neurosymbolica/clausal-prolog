# fix(A06-F009): boolean handling — C hook accepts, Python hook rejects, docs say reject

> **DEFERRED (2026-07-07):** intentionally not implemented — direction-sensitive
> and gated on the parked design decisions A06-D005 / A01-D001 (bool-int
> conflation policy), which per standing mandate are the USER's call and go to a
> todo, never asked interactively. All other A05–A06 audit findings in this pass
> are done; this one waits on the policy call before its two xfails can be
> flipped in the decided direction. See
> `todo/audit-2026-07-05/investigate-A06-parked-design-decisions.md` §5.

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md A06-F009
**Tests:** tests/audit_2026_07_05/test_06_clpfd.py::TestBooleanHandling (2 xfail — flip to pass)
**Gated by:** A06-D005 / A01-D001 (bool-int conflation policy) — see
todo/audit-2026-07-05/investigate-A06-parked-design-decisions.md §5.

## Bug

docs/constraints.md: "Booleans are explicitly rejected by CLP(ℝ) and CLP(ℤ)".
Actual:
- C `_fd_hook` (_clpfd_propagate.c:2836-2857): `PyBool_Check` correctly
  blocks the int fast path, but the Fraction fallback probes
  `bt.denominator` — bool IS int in Python, so `True.denominator == 1`
  converts it and the hook ACCEPTS, binding the var to `True`.
- Python `_fd_hook` (clpfd.py:1731-1737) rejects bool → C/Python divergence.
- Ground fast paths: `fd_eq(1, True)` → True, `fd_ne(0, False)` → False
  (`_both_ground` + Python `==`).
- `in_domain(X, True, True)` accepted (`isinstance(lo, int)`).

## Fix direction

Once D005/A01-D001 lands (recommended: reject):
- C hook: guard the denominator probe with `!PyBool_Check(bt)`.
- fd_* ground paths + `_both_ground`/`_resolve`: reject bool operands
  (there is an unused `_is_fd_candidate` at clpfd.py:1455 that already
  encodes the right predicate — wire it in).
- `in_domain`: `type(lo) is int` style checks.
If the decision is "coerce to 0/1" instead, normalise at every entry and
update docs/constraints.md.

## Acceptance

- Both xfails pass per the decided policy; float/string/Fraction guards stay
  green; document the policy in docs/constraints.md cross-domain notes.
