# A dimensionless quantity compares as its number but is not equal to it (A01-D002)

**Status: open, needs a ruling.** Design decision A01-D002 of the
2026-07-05 audit, split out of
todo/done/investigate-A01-parked-design-decisions.md on 2026-10-20. Full
statement: docs/superpowers/audits/2026-07-05-fable-partition/01-term-layer/design-questions.md.

## Repro

```python
q = Quantity(5, {})
q <= 5 and q >= 5     # True: ordering accepts a plain number
q == 5                # False
unify(q, 5, trail)    # False
```

Still so on 2026-10-20: the characterisation test
tests/audit_2026_07_05/test_01_term_layer.py::TestPriorArtAndCharacterization::test_d002_quantity_dimensionless_characterization
passes, asserting exactly this.

## Options (from the audit)

(a) a dimensionless quantity behaves as its number everywhere (Liskov);
(b) strict everywhere (ordering also refuses a plain number); (c) status
quo, documented. Related: todo/strict-units-directive-2026-09-09.md, which
treats a dimensionless value as distinct from a bare number in its strict
mode.
