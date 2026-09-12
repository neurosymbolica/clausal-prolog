# Ground arithmetic should throw error(system_error(units_mismatch), Ctx)

**Filed 2026-09-12.** Ruled by the operator after discussion with Markus
Triska: units mismatches are thrown in the ISO 13211 `system_error` shape with
the code `units_mismatch`. The CLP side channel (clausal/logic/units_clp.py)
does this, so every COMPARISON already speaks ISO. The ground path — `Quantity.__add__`
and friends, reached through `is/2`, `eval_/2`, `sum_list/2`, `max_/min_`,
`divmod_/4` … — still raises the raw Python `UnitsMismatch`, which `catch/3`
cannot select.

Do: translate at the builtin boundary (one helper, applied where
`UnitsMismatch propagates` is documented in clausal/logic/builtins/arithmetic.py)
so the same term is thrown from both paths, with the same context text
(`_render_pair` in units_clp is the spelling). Keep the Python class as the
internal signal. Pin the term in a fixture next to
tests/fixtures/units_clp_side_channel.clausal. `tests/test_units.py`
`TestUnitMismatchErrors` pins the raw class today for the `is`/`++` paths and
flips with this change.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.
