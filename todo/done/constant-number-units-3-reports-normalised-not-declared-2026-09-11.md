# `constant_number_units/3` reports the NORMALISED pair, not what was declared

**Status: FIXED 2026-09-11 (commit 6e00bc75).** `constant_number_units/3` reports the declared pair (`30`, `day`) while `constant_value/2` remains the normalised value view; both are documented at docs/builtins.md#constant_number_units3. Pinned in tests/test_constants.py::test_constant_number_units_3_reports_the_DECLARED_pair.

**Found by a downstream user 2026-09-11, hours after the predicate landed (`c4c7d6c9`).**
Reproduced here before filing.

    -import_from(units, [day])
    -constant_number_units(standstill, 30, day)

    constant_value(standstill, V)            ->  Quantity(2592000, second)
    constant_number_units(standstill, N, U)  ->  N = 2592000, U = second

**The declared 30 and `day` are unrecoverable from either predicate.** A reflective
predicate named after a directive should relate what that directive declared; this one
relates the Quantity the units library built after normalising to SI base units.

## Why it matters more than it looks

Downstream code has 9 parameters whose names end `_days` and which a migration would want to
declare in days. `article_2d_standstill_days(10)` becoming
`-constant_number_units(article_2d_standstill_days, 10, day)` silently turns every
comparison against it from 10 into 864000. A rule reading
`DAYS_ELAPSED > ++article_2d_standstill_days` goes from a ten-day standstill to one that
never fires.

Same family as the `_cents`/`euro` 100x hazard: units arithmetic silently rescaling a
statutory number. Two instances in the same proposed migration.

**Currency does NOT rescale** — `-constant_number_units(fee, 5000, euro)` stays
`Quantity(5000, euro)`. The hazard is specific to SI-derived units (day, minute, and
presumably hour/week) where the library normalises to a base.

## The decision

Should `constant_number_units(Name, Number, Units)` report:

1. **The DECLARED pair** — `(30, day)`. Recommended. `constant_value/2` already gives the
   value as a Quantity, so /3 earns its place by relating the DECLARATION, and the two
   predicates become complementary rather than one being a lossy view of the other. For a
   statutory number, recovering what the provision said is the point.
2. **The normalised pair** — `(2592000, second)`. What it does today. Defensible (it is
   what the constant IS) but surprising, undocumented, and dangerous in exactly the domain
   the predicate was asked for.

Whichever is chosen, the OTHER one should be reachable and the choice documented at
`docs/builtins.md#constant_number_units3`, which currently says neither.

## Implementing (1)

The directive has the declared number and unit expression in hand as AST at
`_handle_constant_value_directive`. Register them alongside the value — the units
expression lowers to the same nested-tuple term shape `_units_term` already builds
(`('/', ('metre',), ('second',))`), so the predicate can return it directly instead of
reconstructing one from `Quantity.dims`.

Note this makes the two predicates disagree about the number on purpose, which must be
documented rather than discovered: `constant_value/2` yields 2592000 seconds and
`constant_number_units/3` yields 30 day, and both are true of the same constant.

## Separately: a calendar-duration unit that does not rescale

Even with (1), the VALUE is still 2592000 seconds, so arithmetic on a migrated `_days`
parameter is still in seconds. A statutory "within 30 days" is 30 CALENDAR days, which is
not 30 x 86400 across a DST boundary or a month end. Representing a legal deadline in
seconds looks more precise and is less correct. That is a units-library design problem,
not a missing table entry, and it gates the "represent downstream code's units" project.

## The rescaling rule, measured (a downstream user's formulation, confirmed here)

It is NOT "SI-derived units rescale". It is: **a unit that is not the base of its own
dimension rescales to that base.**

    7 kilogram   (IS the base)     ->  7          kilogram     no rescale
    7 metre      (IS the base)     ->  7          metre        no rescale
    7 gram       (not the base)    ->  0.007      kilogram     RESCALES (down)
    7 kilometre  (not the base)    ->  7000       metre        RESCALES (up)
    30 day       (not the base)    ->  2592000    second       RESCALES (up)
    5000 euro    (own dimension)   ->  5000       euro         no rescale

Currency does not rescale because each currency is effectively its own dimension with no
base to normalise toward.

**`gram` rescaling DOWN to 0.007 is a second hazard**: an exact integer quantity becomes a
fraction. For a legal or financial number that is worse than a factor change, because it
also changes the arithmetic type.

### What that means for a `cent` unit

A `cent` defined as a scaled euro would rescale TO euro, turning a declared 5000 cents into
50 — the same 100x error the migration exists to prevent, in the other direction. So the
minor-currency unit is not a table entry either: it has to be its own unit, related to euro
by a conversion the caller asks for explicitly. Same shape as the calendar-duration problem.

Three unit-design calls now gate the "represent downstream code's units" project, and none is a
missing table row:

    cent          must not rescale to euro
    day           must not rescale to second (and calendar days are not 86400s)
    basis point / percent   dimensionless ratios, no unit at all today

## A downstream user's argument for DECLARED, which is stronger than mine

If /3 reports the declared pair, a corpus gate can check that a parameter's declared unit
matches the unit its NAME claims — `_cents` declaring `cent`, `_days` declaring `day`. That
check is impossible against the normalised pair, because every duration comes back as
`second` whatever was written. So "declared" is not only more faithful: it is what makes the
documented-vs-represented problem mechanically checkable, which is the reason downstream code
lane cares about the migration at all.

## Numeric TYPE also changes, and the rule is narrower than "rescaling gives floats"

Measured:

    7 gram      (rescales DOWN)  ->  0.007              float
    7 kilogram  (base)           ->  7                  int
    30 day      (rescales UP)    ->  2592000            int
    5000 euro   (currency)       ->  Decimal('5000')    Decimal
    12.5 euro   (currency)       ->  Decimal('12.5')    Decimal

So it is not "a rescaling unit lands in binary floating point" — `day` rescales and stays
`int`. **The float comes from DIVISION.** Rescaling up by an integer factor keeps the
integer; rescaling down introduces a float. The currency path is different again: it
coerces to `Decimal`, including a float literal.

### Why this decides the `cent` design rather than merely informing it

A `cent` that rescales to `euro` is a division by 100, so it takes the float path: every
monetary parameter would move from exact integer to binary floating point. That is the
precise failure integer-cents storage exists to prevent, arriving through the mechanism
meant to make units safer.

So the minor-currency unit has TWO constraints, not one:

1. it must not rescale to euro (else 5000 cents becomes 50), and
2. whatever it does must keep money out of floats — i.e. behave like the currency path
   (Decimal), not like the SI path.

A downstream user checked the current values: 30 `_cents` facts, 0 of them not divisible by 100,
so today's magnitudes would all land on whole euro. That removes the magnitude hazard for
the CURRENT data and not the type hazard (50.0 is a float whether or not it is whole) — and
"every value happens to divide by 100" is not a property anyone maintains, so it would be
luck to rely on.

## RESOLVED 2026-09-11: the predicate reports the DECLARED pair

Landed at `6e00bc75`. The declared number and unit expression are lowered at compile time and
registered beside `.constants`; `constant_value/2` remains the value view. The two disagree
about the number on purpose and both are documented.

## Operator, 2026-09-11: "dates are weird — months change lengths, business days need
## computation, awareness of holidays"

This closes out the calendar-duration question, and the answer is that **a duration unit was
the wrong model**, not a missing one.

What the engine already has (`clausal/modules/py/datetime.py`): `date_add`, `date_sub`,
`date_diff`, `days_between`, `date_between`, `weekday`, `ordinal`, `date_of`. Real date
arithmetic on Python `date` objects.

What it does NOT have: any month arithmetic, any business-day notion, any holiday calendar.
Grepped, not assumed.

### Why that settles it

A statutory "within 30 days" is a RELATION between two dates, not a scalar quantity:

- **Days** are already expressible — `date_add(Start, 30, Deadline)` / `days_between/3`. No
  unit is needed, and a unit is worse: `Quantity(30, day)` normalises to 2592000 seconds and
  invites arithmetic that is wrong across a DST boundary.
- **Months** cannot be a duration at all. "Three months from 31 January" is a calendar rule,
  not a multiplication; there is no number of seconds that means it. A `month` unit would be
  incoherent, which is presumably why the units library has none.
- **Business days** need a holiday calendar, which is jurisdiction-specific and dated — data,
  not a unit. Two member states disagree about the same Tuesday.

So of the 91 name-encoded units in downstream code, the ~11 duration ones (`_days`, `_months`,
`_minutes`) should NOT migrate to units under any design. They want date-arithmetic
predicates, and the two that do not exist (month arithmetic, business days) are a separate
piece of engine work with a data dependency.

That leaves the units project narrower than it looked: `cent` (35), `bps`/`percent` (21), and
a handful of mass cases. The durations leave the units column entirely.

### Unchanged, and still gating

`cent` still needs a unit that neither rescales to euro nor puts money in a float — and the
float, measured, comes from the unit DEFINITION: `gram` is `Quantity(0.001, kilogram)` with
`0.001` stored as a Python float. So a minor-currency unit defined the same way would inherit
the same defect. `day` is `Quantity(86400, second)` and `kilometre` `Quantity(1000, metre)`,
both int — the type follows the factor's own type, which is a fixable property of the
definition rather than of the mechanism.

## RULED 2026-09-11: no minor-unit currency, no ratio units, ever

**Operator: "cent is ambiguous. euros have cents, dollars have cents. Let's never use cents.
Use the base currency, decimal numbers should be well supported in Clausal."**

That resolves the `cent` design problem by removing it. Documented at
`docs/currency.md#there-is-no-minor-unit-currency-and-there-will-not-be`, which is where
someone would otherwise go to "fix" the missing unit.

Three reasons, and the first is the operator's and the strongest: **a quantity tagged `cent`
does not say which currency it belongs to**, so the unit carries LESS information than the
base-currency form. The other two are the measured hazards — a scaled minor unit would rescale
(5000 cent -> 50) and would put money in floats (the rescale is a division; the type follows
the unit's factor, and `gram`'s factor is a Python float).

**Extended by the same principle to ratios:** no `percent`, no `basis_point`. Write `0.0525`,
not `525` of a scaled unit. A scale encoded in a name is documentation the engine cannot check;
a decimal is a number it can. That closes the second of the three unit-design gates.

**And durations were already ruled out** — date arithmetic, not units. That closes the third.

So all three gates on the "represent downstream code's units" project are now closed, and none of
them by adding a unit:

    cent (35 params)     -> base currency with decimals
    bps/percent (21)     -> plain decimal ratios
    days/months (13)     -> date predicates, not units

### Verified: decimal money is exact, via the documented idiom

    eval_(++rate + ++rate + ++rate, X)   ->  Quantity(Decimal('0.3'), euro)

Exact — a float gives 0.30000000000000004. Scaling and comparison work too.

**One sharp edge worth knowing before downstream code relies on it:** `eval_/2` is the idiom for
unit-carrying values, not `==`. `docs/arithmetic.md` says so ("CLP constraints don't operate on
Quantity objects"), and `++a == ++b` on two amounts raises `type_error(integer, Quantity)` from
clpfd. Comparisons (`>`, `=<`) work directly. Worth stating because `==` is the idiom for
ordinary arithmetic, so it is the one a reader reaches for first — I did.

## SUPERSEDED 2026-09-11 (later the same day): minor currency units EXIST

The section above — "RULED 2026-09-11: no minor-unit currency, no ratio units, ever" — is
**no longer the ruling for currency.** `cent` is implemented, as an ordinary scaled unit of
its base currency, in `clausal/modules/countries/{european_union,united_states}.py`. See
`docs/currency.md#minor-units--cent` and `tests/test_currency_minor_units.py`.

The operator's refinement answers the first reason and the other two were **measured false on
this tree**, which is why it changed:

1. *`cent` is ambiguous.* Answered by putting the currency in scope, not in the name:
   `cent` lives in its jurisdiction module, so `united_states.cent` and `european_union.cent`
   are distinct units that never add — the rule that already governs `dinar`.
2. *A scaled minor unit would rescale, 5000 cent -> 50.* It rescales to
   `Decimal('50.00') euro`, which is the CORRECT amount: normalisation multiplies by the
   factor. The "100x error" above was a misreading of the direction.
3. *It would put money in floats.* Measured false: the currency constructor coerces through
   `Decimal(str(f))`, so even `Quantity(0.01, {dollar: 1})` stores `Decimal('0.01')`. The
   `gram` hazard is real for physical units and blocked for currency. `_make_minor_unit`
   derives the factor from the currency's own ISO scale with `scaleb` and never writes a
   literal, so there is no factor to get wrong.

**Ratios are NOT superseded by this** — there is still no `percent` or `basis_point`, and the
generalisation is parked in
`todo/ratio-declaration-units-basis-points-and-percent-2026-09-11.md`.

**Durations are NOT superseded either** — still date arithmetic, not units.

So of the three gates the section above declared closed, the first is now closed the other
way: by adding the unit.

    cent (35 params)     -> DECLARE in cent; the value is base currency with decimals
    bps/percent (21)     -> still plain decimal ratios (todo above)
    days/months (13)     -> still date predicates, not units
