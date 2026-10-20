# circuit([]) and circuit([X]) both fail (A06-D004)

**Status: open, needs a ruling.** Design decision A06-D004 of the
2026-07-05 audit, split out of
todo/done/investigate-A06-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/design-questions.md.

## Repro

`fd_circuit([], T)` and `fd_circuit([X], T)` yield no solution
(probed 2026-10-20). SWI: `circuit([])` succeeds and `circuit([X])` gives
`X = 1`. Characterisation guard:
tests/audit_2026_07_05/test_06_clpfd.py::TestGlobalConstraintGuards::test_circuit_degenerate_current_behaviour.

## Options (from the audit)

(a) SWI in full (`[X]` gives `X = 1`); (b) both fail, documented; (c) `[]`
succeeds, `[X]` fails (recommended: vacuous truth for `[]`, and a one-node
self-loop contradicts the n >= 2 self-loop exclusion).
