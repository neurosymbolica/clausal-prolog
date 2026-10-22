# The exporter truncates a compound unit in a constant declaration

Filed 2026-10-22, found reviewing the unit-alias export fix. Severity: medium
(the declared unit crosses wrong, silently; the folded use sites are right).

## What / Repro

```seam
-module(sp, [v(X)])
-import_from(units, [metre, second])
-constant_number_units(speed, 3, metre / second)
v(X) <- (X == constant(speed) / (metre / second))
```

Exported (iso): `constant_number_units(sp, speed, 3, metre).`; (scryer):
`:- constant_number_units(speed, 3, metre).` The unit should be
`metre/second`. `v/1` folds correctly to `3`.

Cause: `_constant_declaration` lowers the unit with `_convert_expr`, which
sends `metre / second` through `_fold_term_over_unit` (a `/` whose divisor
resolves to a unit of factor 1 returns its left operand unchanged). That fold
is right for an arithmetic `A / usd` and wrong for a unit expression, which is
a TERM. The declaration's unit needs a lowering that emits the unit
expression as written (`metre/second`, `metre**2` as `metre^2`), not as
arithmetic.

## Also (nit, same area)

`_unit_vocabulary_names` (the unit-alias resolution) reads the `units`
module's bound names, so the deprecated TitleCase spellings
(`-import_from(py.units, [alias(Metre, d)])`) are not resolved as unit
aliases: a declaration in `d` is refused as unresolvable, as it was before
the alias fix. Ignorable while the TitleCase names are deprecated (see
`todo/remove-deprecated-TitleCase-unit-names-after-migration-2026-09-09.md`).
