# An exported decimal-string constant crosses as a STRING, not a number

Filed 2026-10-23, found while pinning the declared-pair export ruling
(todo/done/exported-constant-declaration-carries-the-base-magnitude-with-the-declared-unit-2026-10-22.md).
Severity: high for a program that uses one (the exported value is not a
number at all); not touched by that fix.

## What / Repro

```seam
-module(m, [pay/1])
-import_from(united_states, [usd])
-constant_number_currency(fee, "1550.00", usd)
pay(constant(fee)),
```

Engine: the decimal string is an exact `Decimal('1550.00')` (operator ruling
2026-09-12, tests/test_constant_decimal_strings.py); `pay(X)` gives the
quantity `Decimal('1550.00')` usd, and `constant_number_units(fee, N, U)` gives
`N = 1550.00, U = usd`.

Export (`Dialect.scryer()`, also iso):

    :- constant_number_currency(fee, "1550.00", usd).
    pay("1550.00").

The string is emitted verbatim at the declaration AND the use site, so the
exported `pay/1` holds a string (a char list under Scryer's default
`double_quotes`), not a number. docs/currency.md ("The scale does not survive
EXPORT, though the magnitude does") describes the intended behaviour: the
number crosses, as a float (or as `1_550_00/100` under
`decimal_repr="rational"`).

## Fix sketch

In `_collect_constant` (clausal/tools/clausal_to_prolog.py), for the
units/currency directives, read a numeric string in the number position as
`Decimal` (the engine's rule: only these directives, and only a finite
number), before the declaration is emitted and before the use-site fold.
The table forms take decimal strings too.
