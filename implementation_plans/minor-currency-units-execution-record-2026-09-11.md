# Minor currency units — execution record, 2026-09-11

Task handed to the engine lane in `SESSION-HANDOFF-2026-09-11-engine-lane-END.md` §4a/§4b.
The operator's original words: *"there must be units eur_cents and usd_cents in the currency
module, with scale factor vs base euro/usd. constant_number_units() should be clear about the
unit. euro numbers must be addable to eur_cents."*

## What was built

`cent`, as an **ordinary scaled unit** of its base currency, in the jurisdiction module that
already owns the currency:

    # clausal/modules/countries/united_states.py   (generated)
    cent = _make_minor_unit(dollar)          # Quantity(Decimal('0.01'), {dollar: 1})

    -import_from(united_states, [dollar, cent])
    -constant_number_units(sga_monthly, 155000, cent)

      stored               Quantity(Decimal('1550.00'), dollar)
      constant_value/2     Quantity(Decimal('1550.00'), dollar)
      constant_number_units/3    155000, cent

That is §4b's behaviour table exactly, reached by defining a unit rather than by building a
compile-time spelling recogniser. The whole feature is a 35-line factory plus one generated
line per currency — **no change to the directive, the annotation sugar, or arithmetic.**

## The design was changed on measurement, with the operator's go

§4b ruled for a compile-time declaration spelling (`usd_cents` lowered through
`Decimal(n).scaleb(-scale)`), explicitly *not* a unit in the dimension system, on three
stated reasons. Two of them do not hold on this tree:

| §4b's reason | measured |
| --- | --- |
| a real `eur_cents` would rescale `5000` to `50 euro` and we would relitigate it forever | It rescales to `Decimal('50.00') euro` — the correct amount, and the single representation §4b itself wants. Not a difference between the designs. |
| the numeric type follows the FACTOR's type, so a minor unit is "one careless `0.01` from putting money in floats" | **False for currency.** The currency constructor coerces through `Decimal(str(f))`: even `Quantity(0.01, {dollar: 1})` stores `Decimal('0.01')`. The `gram = Quantity(1e-3, …)` hazard is real for physical units and blocked here. `_make_minor_unit` also never writes a factor literal — it derives one from the currency's own ISO scale with `scaleb`. |
| a dimension per currency-scale doubles the dimension table | Stands, but applies to a **base** dimension. A scaled unit adds no dimension. |

The first objection in the landed `docs/currency.md` section — *`cent` is ambiguous, euros
have cents and dollars have cents* — is answered by putting the currency **in scope** rather
than in the name: `cent` lives in its jurisdiction module, so `united_states.cent` and
`european_union.cent` are distinct units that never add. That is the rule that already
governs `dinar` (Bahrain's is not Kuwait's).

Operator ruled for the real-unit design, and for EUR/USD only, after seeing the above.

## Two questions the operator asked back, and the measured answers

**"Honestly why can't we use the base currency in constants?"** — You can, and it is already
exact: `-constant_number_units(x, 1550.00, dollar)` stores `Quantity(Decimal('1550.0'),
dollar)`, and `_check_currency_precision` rejects sub-scale digits. So minor units buy
exactly one thing — recording what the **source** said — and the base-currency form was never
unsafe. Worth keeping in view if downstream code migration is re-costed.

**"I think the minor units always have names, right?"** — 238 of 254 do; 16 are ISO scale 0
(yen, won) and have no subunit in circulation. But the *names* are not in ISO 4217, which
carries only the number of decimal places, so they are curated data: `MINOR_UNITS` in
`scripts/gen_currencies.py`, EUR and USD populated.

## A real defect found and fixed on the way

`constant_number_units/3` reported the declared magnitude as a **Python float**:
`-constant_number_units(fee, 19.99, euro)` answered `19.99` binary, even though the
constant's VALUE is `Decimal('19.99')`. `_literal_number` reads the raw AST value and nothing
reconciled it with the value's kind — so the one channel whose whole job is fidelity to the
declaration was the one place money went binary.

Fixed by passing the constant to `register_constant_units` and recording the declared
magnitude **in the same numeric kind the value uses**. An `int` stays an `int` (already
exact) and a non-currency float (`1.5 hour`) is untouched; both have negative-control tests.

## A hazard found and NOT fixed — deliberately

`clausal_to_prolog` folds a constant to its **declared** magnitude and discards the unit, so

    -constant_number_units(sga_monthly, 155000, cent)   exports as   pay(155000).

where the engine holds `Decimal('1550.00') dollar` — a 100× money error in the exported
program, flagged only by a `/* LOSSY: */` comment. This is **pre-existing and general**
(`30 day` exports as `30` though the engine stores 2592000 seconds); minor units only point
it at money. Not fixed here because the correct fix is the exporter's — it can resolve the
jurisdiction from the `-import_from` it is already converting — and that is a change of
scope, not a line. Written up in
`todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`, pinned by a
characterisation test, and warned about in `docs/currency.md`.

## Documents corrected, not left

Two landed documents stated the superseded ruling. Both now record what changed and why,
rather than being silently rewritten:

* `docs/currency.md` — the section "There is no minor-unit currency, and there will not be"
  (landed `960edd94`) is replaced by "Minor units — `cent`", carrying a
  "What changed, and why" subsection.
* `todo/constant-number-units-3-reports-normalised-not-declared-2026-09-11.md` — its
  "RULED … no minor-unit currency … ever" section now carries a SUPERSEDED section.

**Ratios and durations are NOT superseded.** No `percent`, no `basis_point` (parked in
`todo/ratio-declaration-units-basis-points-and-percent-2026-09-11.md`, which is a downstream user's
live blocker and the obvious next one); durations remain date arithmetic.

## Worth putting to the other lanes

A downstream user holds 71 ambiguous `_cents` parameter names spanning three lanes (13 profile keys
on the oracle interface, 56 reaching `eval/` bodies, 27 anchored in mutation catalogs). Now
that the declaration can carry the currency and the scale, **most of those renames may be
unnecessary** — the name can stay while the declaration says `cent`. That turns a 71-name
cross-lane rename into a much smaller pass. It is a downstream user's call, not this lane's.

## Evidence

    tests/test_currency_minor_units.py        15 tests, written before the code
    engine suite                              see the handoff for the failure-set diff
