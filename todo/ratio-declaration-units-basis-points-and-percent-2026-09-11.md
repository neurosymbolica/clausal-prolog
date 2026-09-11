# Ratio units: `basis_points` and `percent` as declaration spellings

Filed 2026-09-11. Operator's call, same session: minor CURRENCY units now, ratios in a todo.

**Why it is worth doing.** It is corpus-lane's live blocker, not a hypothetical.
`eu/banking/crr_leverage_ratio` computes in basis points **throughout**: `leverage_ratio_bps/2`
is EXPORTED, the kit supplies `ratio_bps`, and 15 `bps` references span the public interface,
the queries and the tests. `au/merger_clearance` has the same shape with `_cents`
(8 parameters, 69 references). The approved corpus migration told those parameters to become
plain decimals, which is exactly what makes the migration expensive — it redirects the two
groups that are hardest to convert.

**What landing minor units already proved.** The mechanism needs nothing new:

    cent = _make_minor_unit(dollar)      #  Quantity(Decimal('0.01'), {dollar: 1})

An ordinary scaled unit with a `Decimal` factor works in the directive, in the `155000 (cent)`
annotation sugar and in arithmetic, and normalises to its base exactly. The ratio case is the
same shape against the DIMENSIONLESS base rather than a currency:

    basis_points = Quantity(Decimal('0.0001'), {})      # 300 basis_points -> Decimal('0.03')
    percent      = Quantity(Decimal('0.01'),   {})      # 5.25 percent     -> Decimal('0.0525')

`clausal/modules/units.py` already has a dimensionless unit (empty dims, ~line 186) to hang
these off. Verify the exactness claim before writing the docs — the currency path coerces
through `Decimal(str(f))`, and a DIMENSIONLESS quantity may not, in which case the factor must
be built with `scaleb` and the multiplication checked for a float result.

**What it buys.** `constant_number_units/3` reports the DECLARED pair, so
`-constant_number_units(min_leverage, 300, basis_points)` keeps "300 bps" recoverable while
the value is `0.03` — the same "documented but not represented" problem the currency half
closed. A domain can then stop renaming its parameters `_bps`.

**What it does NOT solve** (measured by corpus-lane, 2026-09-11, and still true):

* A domain whose PUBLIC interface computes in bps — `leverage_ratio_bps/2` is exported, so
  rescaling the parameter without rescaling its producers and consumers makes the comparison
  wrong. This makes that conversion cheaper (no representation change at any interface), not
  free.
* Values DUPLICATED as bare literals: `minimum_leverage_bps(300)` and a bare `300` at
  `leverage_ratio.clausal:111`. Converting the fact leaves the literal, so the DRY premise of
  the migration survives only if the literal sites become `constant(...)` too.

**Also note.** `docs/currency.md` currently says "there is still no `percent` or
`basis_point` unit" and points here. Update it when this lands.
