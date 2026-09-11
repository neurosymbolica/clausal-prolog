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
