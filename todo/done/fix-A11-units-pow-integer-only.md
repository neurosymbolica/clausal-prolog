# fix(A11-F057): _UnitsPredicate.__pow__ accepts float exponents

`modules/units.py:113-118` (annotation `int | float` invites it):
`Metre ** 0.5` builds a Quantity with fractional dims `{Metre: 0.5}` —
contradicting docs/units.md:568 ("integer-only exponents in Pow") and
`Quantity.__pow__`, which raises UnitsMismatch for non-int exponents on
dimensioned values. Fractional-dim quantities can't be produced/consumed
consistently anywhere else.

**Fix**: mirror Quantity — raise/NotImplemented for non-int exponents; fix
the annotation.

**Test**: test_F057_unit_pred_pow_integer_only (xfail).
