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

---

## RESOLVED (partly) 2026-09-11: option 1 landed — it REFUSES

The operator ruled option 1 the same day, after three independent censuses agreed the cost is
zero today:

* **corpus source** (iso-export-lane, corpus b6f2c367, 74 roster domains / 931 files): the
  only unit-bearing literals are `euro` 34, `baht` 7, `dollar` 5 — all BASE currencies. Zero
  occurrences of `cent`, `satang`, `penny`, `day`, `hour`, `minute`, `week`, `month`, `year`,
  `kilometre`, `km`, `gram`, `kg`, `tonne`. `-constant_number_units` appears zero times in
  the corpus and zero times in kit.
* **corpus exports** (same lane, the `% Clausal units:` comments across 754 staged `.pl`):
  `euro` 23, `baht` 9, `dollar` 4, nothing else. The two censuses agree, which is the point
  of running both — a scaled unit reaching the exporter by an ungrepped path would show in
  the second.
* **engine tree** (me): the only exporter test declaring a united constant uses `euro`.

`_collect_constant` now raises `NotImplementedError` when any leaf of the declared unit
expression is not a base unit. `_base_unit_names()` is the `_UnitsPredicate` names in
`clausal/modules/units.py` (base dimensions AND factor-1 derived units like `newton`) plus
every currency name — precisely the units whose declared magnitude IS the stored magnitude.
An unknown name is refused rather than assumed base.

Tests in `tests/test_currency_minor_units.py`; the characterisation test that pinned the old
100× fold is deleted, as its own message instructed.

**Option 2 is still the fix and this is still open.** corpus-lane's framing is the one to
keep: the refusal costs nothing *today* and stops being free the moment the constants
migration starts, because that migration is exactly what creates the first corpus constant.
A domain that is both on the migration list and on the ISO publish list is blocked until the
exporter folds to the BASE magnitude. Everything in the "Ask" section above still applies —
the exporter can resolve the jurisdiction from the `-import_from` it already reads.

### The inline shape, found after option 1 landed

corpus-lane, same day, verified on this tree: option 1 as first written covered the
DECLARATION and left the identical defect open on the inline quantity literal.

    -constant_number_units(m, 155000, cent)   ->  NotImplementedError    refused
    pay(155000(cent))                         ->  pay(155000).           EMITTED

Both shapes hold `Quantity(Decimal('1550.00'), dollar)` in the engine. `_try_quantity` kept
the magnitude and dropped the unit for every unit, base or scaled — correct under the
2026-09-08 ruling while the written magnitude IS the stored one, wrong the moment the unit
carries a factor. Same predicate, second data shape; the first fix did not reach it.

Now refused too, at the one point where the inline unit is attached, with the same base-unit
test. Both refusals lift together when option 2 lands.

Nothing was exposed: corpus inline quantity literals name `euro` (36), `baht` (9) and
`dollar` (5), nothing scaled.

**The lesson for the next fix here: this predicate has two data shapes.** A change that
reads only one of them covers half the surface, and the half it misses looks identical from
the outside.

### The two refusals have OPPOSITE polarity, deliberately

Worth knowing before editing either, because they look like the same check and are not:

    declaration path   refuse unless the unit is KNOWN BASE      (_base_unit_names)
    inline path        refuse only if the unit is KNOWN SCALED   (_is_known_scaled_unit)

A declaration in a scaled unit had zero occurrences anywhere when this landed, so refusing
everything not known to be safe costs nothing there. The inline `5000(euro)` form is used
throughout the corpus and the tests and has exported this way since the 2026-09-08 ruling —
refusing unknown names there broke 15 tests on the first attempt, including the
still-supported TitleCase `Metre` alias and four `iso_type_checking` fixture roundtrips. So
the inline check under-refuses in the direction of the established behaviour: an unrecognised
name keeps working, only the known hazard is refused.

When option 2 lands, both become the same conversion and the asymmetry goes away.

**One more trap, paid for once.** `_try_quantity` is reached by every one-argument call, not
only by quantities — it identifies a quantity and returns None for anything else. A check
placed before that identification refuses `implements(k1)`. `test_ordinary_predicate_call_is_untouched`
in `tests/test_prolog_quantity_units.py` catches it; the guard belongs inside the branches
that have already established the node IS a quantity.

---

## 2026-09-12 — the operator expects the constants family in Scryer/Trealla via TERM EXPANSION

Operator, on landing the decimal-string form: *"I expect constants predicate family to be
available for Scryer and Trealla anyway, using term expansion."*

**That reframes this todo and may retire its premise.** Option 2 (fold to the base magnitude) is
a way of making a LOSSY export less wrong: the 2026-09-08 ruling was that ISO Prolog cannot carry
a quantity, so the exporter discards the unit and the only question was which number survives.
If the constants family exists on the Prolog side as term-expanded declarations, the exporter
stops needing to fold at all — it emits the declaration and the unit crosses with it.

Three things that follow, none of them yet decided:

* **Option 2 may be the wrong shape of work.** Folding to the base magnitude is a patch on a
  channel that would no longer be the channel. Worth settling the term-expansion direction
  BEFORE building it, because the two answers do not compose — one discards units more
  carefully, the other stops discarding them.
* **The scaled-unit refusals would lift for a different reason.** Today they exist because
  dropping `usd_cent` or `basis_point` changes the magnitude. Under term expansion the unit is
  not dropped, so there is nothing to refuse.
* **It changes what "lossy" means for the roster.** iso-export-lane's export-bytes axis compares
  emitted Prolog; a declaration-carrying export is a different file shape, not a different number
  in the same shape. That is a coordinated change, not an engine-side one.

**Not a decision to make from here.** Recorded so that whoever picks up option 2 checks the
term-expansion direction with the operator first, rather than building the fold and discovering
it was scaffolding.
