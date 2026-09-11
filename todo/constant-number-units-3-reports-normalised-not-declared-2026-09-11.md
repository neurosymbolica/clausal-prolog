# `constant_number_units/3` reports the NORMALISED pair, not what was declared

**Found by corpus-lane 2026-09-11, hours after the predicate landed (`c4c7d6c9`).**
Reproduced here before filing.

    -import_from(units, [day])
    -constant_number_units(standstill, 30, day)

    constant_value(standstill, V)            ->  Quantity(2592000, second)
    constant_number_units(standstill, N, U)  ->  N = 2592000, U = second

**The declared 30 and `day` are unrecoverable from either predicate.** A reflective
predicate named after a directive should relate what that directive declared; this one
relates the Quantity the units library built after normalising to SI base units.

## Why it matters more than it looks

The corpus has 9 parameters whose names end `_days` and which a migration would want to
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
not a missing table entry, and it gates the "represent the corpus's units" project.

## The rescaling rule, measured (corpus-lane's formulation, confirmed here)

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

Three unit-design calls now gate the "represent the corpus's units" project, and none is a
missing table row:

    cent          must not rescale to euro
    day           must not rescale to second (and calendar days are not 86400s)
    basis point / percent   dimensionless ratios, no unit at all today

## corpus-lane's argument for DECLARED, which is stronger than mine

If /3 reports the declared pair, a corpus gate can check that a parameter's declared unit
matches the unit its NAME claims — `_cents` declaring `cent`, `_days` declaring `day`. That
check is impossible against the normalised pair, because every duration comes back as
`second` whatever was written. So "declared" is not only more faithful: it is what makes the
documented-vs-represented problem mechanically checkable, which is the reason the corpus
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

corpus-lane checked the current values: 30 `_cents` facts, 0 of them not divisible by 100,
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

So of the 91 name-encoded units in the corpus, the ~11 duration ones (`_days`, `_months`,
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
