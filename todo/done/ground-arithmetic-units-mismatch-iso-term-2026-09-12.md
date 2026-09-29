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

## Closed 2026-09-30

Fixed on fix/todo-batch-2-2026-09-30 at the one place every door meets:
`exceptions.python_error_term`, the transliteration `catch/3` (compiled and
trampoline) and the module-predicate wrapper use for a non-logic exception.
A `UnitsMismatch` now transliterates to `error(system_error(units_mismatch),
_)` (unbound context, the message as prose) instead of the TitleCase
`UnitsMismatch(Message)` cell no catcher can be written against, so the same
catcher selects it from `==` (the CLP channel, unchanged), `eval_/2`,
`sum_list/2`, `max_list/2` and a `++` escape. The Python class stays the
internal signal: uncaught, it is still `UnitsMismatch`, and a
`++UnitsMismatch(M)` catcher still matches (`_is_python_error_term_of` knows
the new shape, so the wrapper unwrap keeps working). Pinned by
tests/test_units_mismatch_iso_term.py.

Not done: a culprit indicator in the context (the Quantity operation does not
know which builtin reached it).
