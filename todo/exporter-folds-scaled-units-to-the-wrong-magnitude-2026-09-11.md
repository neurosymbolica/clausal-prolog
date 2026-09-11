# `clausal_to_prolog` folds a scaled-unit constant to the wrong magnitude

Filed 2026-09-11, found while landing minor currency units (`cent`).

**Today.** `_collect_constant` (`clausal/tools/clausal_to_prolog.py`, ~1633) converts the
declared MAGNITUDE and discards the unit, so a constant declared in a unit that is not the
base of its own dimension exports as a number the engine never held. Measured on this tree:

    -import_from(united_states, [dollar, cent])
    -constant_number_units(sga_monthly, 155000, cent)
    pay(constant(sga_monthly)),

    exports as:   pay(155000).        /* engine holds Quantity(Decimal('1550.00'), dollar) */

The output carries `/* LOSSY: unit discarded: ... folds to its magnitude only */`, which is
accurate and is not a guard: the exported program computes with a number 100x too large and
nothing refuses to run it.

**This is pre-existing and general, not new with `cent`.** `-constant_number_units(w, 30, day)`
exports as `30` while the engine stores `Quantity(2592000, second)`; the same holds for
`kilometre`, `gram`, `tonne` — every non-base unit in `clausal/modules/units.py`. Minor units
only made it point at money, where the error is a wrong legal answer rather than a wrong
number of seconds.

Pinned by `test_the_exporter_folds_a_minor_unit_to_its_declared_magnitude` in
`tests/test_currency_minor_units.py`, so it cannot move silently in either direction. The
warning in `docs/currency.md` §"Known divergence" points here.

**Ask.** Export the BASE magnitude, the one the engine actually holds.

The obstacle usually stated — "the translator must never execute the file it is translating"
— does not block this. The exporter already reads the import directives it is converting to
`use_module`, so for `-import_from(united_states, [dollar, cent])` it knows the name `cent`
resolves in `clausal.modules.countries.united_states`, and the factor is available as static
data (`_data.py`'s `scale` for a minor unit; the `Quantity` factor literal for a physical
unit). Resolving a NAME to a known unit is not executing the file.

Three options, cheapest first:

1. **Refuse, don't fold.** Raise on a constant whose declared unit is not a base unit, the
   way `-constants` files are already refused (~1170). Loud, and correct until someone needs
   the export. Cost: any corpus file declaring `30 day` stops translating — measure that
   count before choosing this.
2. **Fold to the base magnitude for units the exporter can resolve**, refuse for those it
   cannot. Correct for the cases that matter, and the LOSSY note becomes true ("unit
   discarded; magnitude converted to `second`") rather than misleading.
3. **Emit the pair**, leaving the scale visible in the exported program. Largest change,
   and Prolog has no unit system to receive it.

Option 2 is the one worth costing. Whichever is chosen, delete the pinning test and the
docs warning as part of it.

**Do not export a rulebase that declares constants in minor units until this is settled.**
