# Ratio units: `basis_points` and `percent` as declaration spellings

Filed 2026-09-11. Operator's call, same session: minor CURRENCY units now, ratios in a todo.

**Why it is worth doing.** It is corpus-lane's live blocker, not a hypothetical.
`<downstream-domain>` computes in basis points **throughout**: `leverage_ratio_bps/2`
is EXPORTED, the library supplies `ratio_bps`, and 15 `bps` references span the public interface,
the queries and the tests. `<downstream-domain>` has the same shape with `_cents`
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

---

# DONE — 2026-09-12

`percent` and `basis_point` are dimensionless scaled units in
`clausal/modules/units.py`, built from `RATIO_UNITS` (name -> decimal exponent), with the
factor a `Decimal` built by `scaleb`. Nothing else changed: the directive, the `300
(basis_point)` annotation sugar and the arithmetic all took them unmodified, exactly as this
todo predicted. Pinned in `tests/test_ratio_units.py`.

**Singular, not plural.** Every other unit name in the repo is singular (`metre`, `usd_cent`,
`penny`), and `docs/currency.md` already used `basis_point`. The todo's own title said
`basis_points`; the convention won.

## The exactness question this todo said to verify — answered, and the todo's reason was wrong

The worry was that the currency coercion path is what makes minor units exact and that a
dimensionless quantity might lack it. Measured, with `gram`'s float factor as the negative
control that shows the probe can see inexactness:

    300 (basis_point)        Decimal('0.0300')      exact
    5.25 (percent)           Decimal('0.0525')      exact
    0.5 (basis_point)        Decimal('0.00005')     exact
    Fraction(1,3) (percent)  Fraction(1, 300)       exact
    7 (gram)   [control]     0.007 as a float       INEXACT

It is **not** the currency coercion. `_to_decimal` is keyed on an `is_currency` dimension and
sits in the other `Quantity.__init__` branch; a scaled unit returns at terms.py:2372 and never
reaches it. Exactness comes from `_num_pair`, which is dimension-agnostic and reads a float
beside a `Decimal` as `Decimal(str(f))`. So the one load-bearing requirement is that the
FACTOR is a `Decimal` — which is what `_make_minor_unit` already argued, and what `gram` does
not have. No `scaleb` check on the multiplication was needed.

## What landing them turned up: a refusal that was blind to exactly this shape

`_is_known_scaled_unit` in the exporter selected `isinstance(v, Quantity) and v.dims`. The
`and v.dims` clause excludes a DIMENSIONLESS scaled unit — a ratio unit's shape — so
`300(basis_point)` exported as `300` against a stored `0.03`, a **10000x** error, silently.
The declaration path refused correctly; only the inline path was blind, which is the same
half-covered-surface shape the 2026-09-11 review already found once.

**The clause excluded nothing on the day it was written.** There were zero dimensionless
`Quantity` constants in `units.py`, so no instrument could have noticed it, and the fix adds
exactly `{basis_point, percent}` to the refused set and removes nothing. This is the
"instrument keyed on a property the checked thing does not have" family again — and the
version of it that is invisible until the population changes, which is the hard version.

## The scale lint's hand-maintained half shrank, and its own control said so

`basis_points` and `percent` left `_HAND_MAINTAINED_SCALE_WORDS` for the derived half; `bps`
and `pct` stay, being abbreviations no vocabulary holds. The derivation was extended first,
with the hand list untouched, purely to watch the overlap assertion fire — it did, naming
both words. A half designed to shrink now has a demonstrated way of noticing that it should
have.

The inline copy of the derivation inside `_scale_suffixes` was deleted in favour of calling
`_derived_scale_words()`: two copies would have let the overlap control go on checking a set
the lint no longer used.

## Still not solved, unchanged from the analysis above

* A domain whose PUBLIC interface computes in bps (`leverage_ratio_bps/2` is exported) still
  has to rescale producers and consumers together. Cheaper, not free.
* Values duplicated as bare literals — `leverage_ratio.clausal:111`'s bare `300` under
  `check_ratio_gte/6` — are invisible to the lint, because the discriminator is the FUNCTOR's
  name. Unchanged by this landing, and the callee's-parameter design in the handoff is still
  the promising fix.
* **The exporter refuses a ratio-unit amount**, so `<downstream-domain>` cannot migrate and
  stay on the export roster until option 2 lands
  (`todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`). That todo was
  already load-bearing; this makes it block corpus-lane's stated blocker too.
