# label/1 on a variable with no finite domain succeeds once, leaving it unbound (A06-D001)

**Status: open, needs a ruling.** Design decision A06-D001 of the
2026-07-05 audit, split out of
todo/done/investigate-A06-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/design-questions.md.

## Repro

`label([X])` with an `X` that has no `fd` attribute yields one solution and
leaves `X` unbound (probed 2026-10-20 through `clausal.logic.clpfd.label`),
while a variable with an `fd` attribute but an unbounded domain raises
ValueError. Characterisation guard:
tests/audit_2026_07_05/test_06_clpfd.py::TestLabeling::test_domainless_var_current_behaviour.

## Options (from the audit)

(a) raise for any variable without a finite domain, as SWI does
(`instantiation_error`-style; recommended: a wrong solution count is the
worst failure for an enumeration primitive); (b) documented silent skip;
(c) skip and warn.
