# Currency amounts

Exact-decimal money for financial and regulatory rules. A currency amount is a
[`Quantity`](units.md) whose **magnitude is exact** (a `decimal.Decimal`, or a
`fractions.Fraction` after a division that does not terminate; never a binary
float) and whose **dimension is a currency** (`euro`, `usd`, …). Currencies are
units *base dimensions*, so all of dimensional analysis applies: euros add only to
euros, money scales only by dimensionless numbers, and mixing currencies is an error —
with **no implicit conversion** (exchange rates are not constants).

This page is the integration guide. If you are converting existing rules to use currency,
read [Applying currency to existing rules](#applying-currency-to-existing-rules) first.
Arithmetic in general (what `/`, `//`, `rdiv` and `eval_/2` do) is documented in
[Arithmetic](arithmetic.md) and [Operators](operators.md); this page covers only what a
currency adds.

---

## Quick start

A `.seam` file (the same syntax as `.clausal`, hosting Python) declares the rules and
queries them from Python with a goal-position `--`:

```clausal
-module(shop, [])
-import_from(european_union, [euro])
-import_from(currency, [money_round, money_str, money_format])
-private([half_up, half_even, symbol])   # rounding modes and styles are atoms

from clausal import to_python

# write an amount: value(currency); the value is an exact Decimal
price(P) <- eval_(7.89(euro), P)

# arithmetic keeps full precision; same currency only
total(T) <- eval_(0.1(euro) + 0.2(euro), T)

# round and display with an EXPLICIT mode
show(S) <- (total(T), money_str(T, half_up, S))
rounded(R) <- (eval_(10.00(euro) / 3, Q), money_round(Q, half_even, R))
sym(S) <- (price(P), money_format(P, symbol, half_up, S))

def main():
    for T in --total(T):
        print(T)                 # 0.3 (euro)   magnitude Decimal('0.3'), no float anywhere
    for R in --rounded(R):
        print(R)                 # 3.33 (euro)
    for S in --show(S):
        print(to_python(S))      # 0.30 EUR     money_str answers a string
    for S in --sym(S):
        print(S)                 # €7.89        money_format answers an atom (a str)
```

Rounding modes (`half_up`, …) and display styles (`symbol`, …) are ordinary atoms, so a
module declares the ones it writes (here with `-private`), as it would any other atom.
A query runs from a function (`main` above), not at module top level: the module's
predicates are registered only once the file has finished loading.

---

## Importing currencies

Each currency is defined **once**, in its home **jurisdiction module**, and referenced
from there. Jurisdiction modules are spelled out (`european_union`, `united_states`, …) —
never ISO country codes (`is`/`in`/`as` collide with reserved words).

**A currency's identifier names exactly one currency, program-wide.** The everyday word is
kept when it belongs to a single *current* currency — `euro`, `yen`, `baht`, `sterling`,
`lira` — and replaced by the lowercase **ISO 4217 code** when several currencies share it:
`dollar` is the word of 22 current currencies, so it is not bound at all and the US dollar is
`usd`, Australia's `aud`; `dinar` belongs to eight, so Bahrain's is `bhd` and Kuwait's `kwd`.
120 of 254 currencies are named by their code, 134 keep their word.

The word survives as the currency's *display* name either way — a judgment says "500.00
dollar", not "500.00 USD" — so this changes the identifier a rulebase **writes**, not the
word the system **prints**.

**Single-currency module** — import the bare name and never write the prefix:

```clausal
-import_from(japan, [yen])
-constant_number_currency(budget, 1000000, yen)   # a Japanese rule means Japanese yen
```

**Multiple currencies** — import each, or qualify with the jurisdiction:

```clausal
-import_from(european_union, [euro])
-import_from(united_states, [usd])
-import_module(united_states)         # enables the qualified form below

eu_price(P) <- eval_(10.00(euro), P)
us_price(P) <- eval_(12.00(united_states.usd), P)   # qualified — same currency as the bare `usd`
```

Two references to the **same** currency (bare-imported or module-qualified) are the same
dimension and add freely. Two **different** currencies are distinct dimensions and never
add — `euro + usd` raises [`UnitsMismatch`](#errors-and-catch3).

### The vocabulary

The **full ISO 4217 set (all ~150 active currencies)** ships, one per home jurisdiction,
generated from ISO 4217 minor units. Import any by its jurisdiction module — the bare
currency name is the everyday word (`baht`, `rupee`, `won`, `franc`, `peso`, `dinar`, …):

| Import | Currency | ISO | Minor units (scale) | Symbol |
|--------|----------|-----|---------------------|--------|
| `european_union` | `euro` | EUR | 2 | € |
| `united_states` | `usd` | USD | 2 | $ |
| `united_kingdom` | `sterling` | GBP | 2 | £ |
| `japan` | `yen` | JPY | 0 | ¥ |
| `bahrain` | `bhd` | BHD | 3 | BD |
| `thailand` | `baht` | THB | 2 | THB |
| `south_korea` | `won` | KRW | 0 | ₩ |
| `kuwait` | `kwd` | KWD | 3 | KWD |

(examples — the same-named `dinar` in `bahrain`/`kuwait`/`jordan`/… are **distinct**
currencies, kept apart by their jurisdiction module.) The home jurisdiction is the
currency's issuer, so a country using another's currency references the issuer — an
Ecuadorian module (legal tender: US dollar) imports `usd` from `united_states`. Shared
regional currencies live in a regional module: `european_union.euro`,
`west_african_cfa.xof` (XOF), `central_african_cfa.xaf` (XAF), `cfp_franc.xpf` (XPF),
`east_caribbean.xcd` (XCD).

The full table is generated data — see
[`clausal/modules/countries/_data.py`](#extending-the-vocabulary). Scales come from ISO 4217
(so `won`/`yen` are 0, the Gulf dinars are 3); symbols are a common glyph where one exists,
otherwise the ISO code (the `symbol` display style then shows the code, e.g. `"THB19.99"`).

### Historical (and future) currencies

Withdrawn currencies ship too, so rules can reason about obligations denominated in a
currency no longer in use (a pre-euro Deutsche Mark contract, an old Zimbabwe-dollar
judgment). Every currency carries its **in-service date range** — `start` and `end` (ISO date
strings; `end` is `None` while still current; a future `start` denotes a scheduled currency
not yet in use), queryable via `currency_start`/`currency_end`.

Where a country reused a currency word across successive currencies, the names are
discriminated: the **current** one keeps the plain word, and older ones take the
distinguishing term from their official name, or a date range when only the date differs:

```clausal
-import_from(germany, [dem])            # Deutsche Mark (1948–2002), historical
-import_from(zimbabwe, [gold, dollar_1980_2008, dollar_2009_2024])
-import_from(angola,  [kwanza, new_kwanza, readjusted_kwanza])
-import_from(venezuela, [bolivar, bolivar_1871_2008, bolivar_2008_2018])
```

Historical amounts behave exactly like current ones — exact `Decimal`, dimension-safe, the
same `money_*` predicates. `19.99(dem) + 0.01(dem)` is `20.00(dem)`; `dem + euro` raises
`UnitsMismatch` (a Deutsche Mark is not a euro — conversion is explicit and out of scope).

---

## Writing amounts

### `value(currency)` — the normal form

```clausal
-import_from(european_union, [euro])
-import_from(japan, [yen])
-import_from(bahrain, [bhd])

a(X) <- eval_(7.89(euro), X)     # X = 7.89 (euro),  magnitude Decimal('7.89')
b(X) <- eval_(1000(yen), X)      # X = 1000 (yen),   yen has no minor unit
c(X) <- eval_(1.234(bhd), X)     # X = 1.234 (bhd),  the Bahraini dinar has scale 3
```

The written value becomes an **exact `Decimal`** — `7.89(euro)` is exactly 7.89, never the
binary-float `7.8899999…`. Integers and decimal literals both work.

### The precision check

Tagging a number as a currency **rejects any value with more decimal places than the
currency's scale**, raising [`CurrencyPrecisionError`](#errors-and-catch3):

```clausal
-import_from(european_union, [euro])
-import_from(japan, [yen])
-import_from(bahrain, [bhd])

ok_1(X) <- eval_(7.89(euro), X)     # ok
bad_1(X) <- eval_(7.891(euro), X)   # RAISES CurrencyPrecisionError: 3 dp for a 2-dp currency
bad_2(X) <- eval_(7.5(yen), X)      # RAISES: yen has scale 0
ok_2(X) <- eval_(1.234(bhd), X)     # ok: the Bahraini dinar has scale 3
```

This is deliberate: it catches money entering through lossy float arithmetic. The
canonical footgun is doing the maths in float **before** tagging:

```clausal
-import_from(european_union, [euro])

wrong(X) <- eval_((0.1 + 0.2)(euro), X)      # RAISES: 0.1 + 0.2 is a float first (0.30000000000000004)
right(X) <- eval_(0.1(euro) + 0.2(euro), X)  # each literal is an exact Decimal: X = 0.3 (euro)
```

(`wrong/1` also warns at load, `ClausalCurrencyLiteralWarning`, because the float carries
17 significant digits; see [below](#float-literals-are-exact-to-15-significant-digits).)

When the check fires, do one of three things (the error message says so):
1. **combine per-currency literals** — `0.1(euro) + 0.2(euro)`, not `(0.1 + 0.2)(euro)`;
2. **round explicitly** — `money_round(V, Mode, Out)` after deciding the rounding;
3. **use `money_precise`** for a deliberately sub-scale amount.

### Float literals are exact to 15 significant digits

There is no decimal literal syntax: `1550.00` in a `.clausal` file is a Python float before
any currency code sees it. That is safe far further than it sounds, because the currency path
coerces through `Decimal(str(f))` — never `Decimal(f)` — and **measured on this code path, a
decimal with 15 or fewer significant digits always survives**. Past that it is a hazard, not
a certainty: over 40,000 random two-decimal amounts per row, 16 digits lost 11.77%, 17 lost
83.11%, 18 lost 98.25%. About one 17-digit amount in six still comes through intact, which is
why the warning says the amount *may* not be the one written.

At two decimal places that covers every amount below about ten trillion. Above it, the amount
may already have been rounded by the tokenizer, and nothing downstream can recover what was
written — so the currency constructor warns
([`ClausalCurrencyLiteralWarning`](#errors-and-catch3)) whenever a float magnitude carries 16
or more significant digits. It cannot detect the loss; it detects the band in which loss is
possible, which is the difference between a loud problem and a silent wrong amount.

**The exact spelling for a large amount is a [minor unit](#minor-units)**, because the
magnitude is then an integer and an integer is exact at any size:

```text
     12345678901234565 eur_cent ->  123456789012345.65   exact
    123456789012345.65 euro  ->  123456789012345.66   one cent high, and warns
```

The euro line is not a rounding that happens later — `123456789012345.65` cannot be *written*
as a float literal at all. The parser produces the nearest float, whose `repr` is
`123456789012345.66`, so the source text is gone before any currency code runs. Its
neighbours `.63` and `.68` lose a cent the same way, while `.67` and `.69` happen to survive
intact; which amounts fall on which side is not something a reader can predict, and that is
the point of warning on the whole band.

`money/3` takes the amount as a **string**, which is exact by construction and is the other
way to write one:

### `money/3` and `money_precise/3` — string constructors

`money(Text, Currency, Out)` builds an amount from a decimal **string** (exact, and
precision-checked). `money_precise(Text, Currency, Out)` is the same but **skips** the
precision check — for genuine sub-scale amounts (unit prices, tariffs, tax rates).

```clausal
-import_from(european_union, [euro])
-import_from(currency, [money, money_precise])

price(P) <- money("7.89", euro, P)                # P = 7.89 (euro); "7.891" would raise
rate(RATE) <- money_precise("0.0034", euro, RATE) # RATE = 0.0034 (euro), sub-cent, allowed
```

Prefer `money("...", C, X)` (string) over `X(euro)` when the value comes from external data
you want parsed exactly with no chance of a float in the pipeline.

### Extracting the number

`strip_units/2` (from `py.units`) yields the bare `Decimal`:

```clausal
-import_from(py.units, [strip_units])
-import_from(european_union, [euro])

amount_value(V) <- (eval_(7.89(euro), A), strip_units(A, V))   # V = Decimal('7.89')
```

---

## Bare integers are not money

A number that carries its scale only in an identifier — `minimum_margin_bps(300)`,
`monthly_limit_cents` — is a bare integer to the engine. Two failures follow, and
neither announces itself:

```text
two 'cents' integers, different currencies
  bare ints :  5000000 + 155000  ->  5155000      AUD and USD, silently summed
  as money  :  UnitsMismatch: Unit mismatch for add: aud vs usd

a cents value against a dollars threshold
  bare ints :  155000 > 1550     ->  True         "exceeds the threshold"
  as money  :  1550.00 > 1550    ->  False        it does not
```

The second is the one to keep in mind: not a wrong number, a **reversed answer**.

**So the engine warns.** A name ending in a scale word (`_cents`, `_bps`, `_satang`,
`_pence`, `_percent`, …) that carries a bare numeric literal raises
`ClausalScaleInNameWarning`, once per (file, identifier):

```text
margin.clausal:93: `minimum_margin_bps` names a scale but carries a bare
number — the scale exists only in the identifier, where nothing can check it. Declare
the amount with -constant_number_currency (or -constant_number_units) and use it here,
so the unit is a fact the engine holds.
```

It fires on both shapes: a **fact** with a bare literal argument, and a `-constant_value`
declaration whose name claims a scale but which takes no unit. A site that has been
converted carries a quantity rather than a literal and goes quiet, so the lint is a
**migration worklist, not a permanent complaint**.

### What it cannot see, and why that matters

The discriminator is the **functor's name**. A bare literal in an argument of a functor that
claims no scale is invisible:

```text
minimum_margin_bps(300),                                     warns
margin_ok(P) <- check_ratio_gte(P, tier1, total, 300, …)     SILENT — 300 is the floor
```

Picture both lines in one program: the second is the one that decides, and the first is a
fact nothing reads any more. So **an emptied warning list is not "this program is done"** —
converting the site the lint names can silence a program whose deciding literal is untouched.
Self-emptying is a genuine progress signal for the sites the lint *can* see, and it is not a
completeness claim.

Closing that gap needs a signal the source does not currently carry. The promising one is the
**callee's parameter**: if `check_ratio_gte/6`'s fourth parameter were itself declared to
take a ratio, the literal would be checkable at the call. A same-value or same-file heuristic
is not — it learns the cases it was built from.

### What the warning COUNT does not mean

Worth stating plainly, because the count is offered as a migration progress signal and it is
**wrong in both directions**:

* It **under-reports**. A bare literal under a functor that claims no scale is invisible, and
  that is where a deciding value can sit — so a program can reach zero warnings with its
  deciding literal untouched.
* It **over-reports on a table's CALL SITES.** `t_usd_cents(1, X)` warns because the functor
  claims a scale and carries a bare literal — but that literal is the index key, not money.
  `money_at(N)` lives on the declaration and a call site does not carry it, so the
  discriminator cannot tell a key column from a money column there. A table read with literal
  keys (household size 1..8, say) lights up one warning per call site on migration, each one
  telling an author to declare an index as money.
* It **over-reports** wherever the lint has not been taught that a site is already declared.
  It exempts a row carrying a unit, including one produced by
  [`-constants_number_currency`](#tables-a-declaration-that-defines-the-predicate) — but the
  exemption is a rule about the row's shape, and a future declaration form the rule does not
  recognise would warn on correct code again.

So a falling count is evidence of progress and not a measure of it, and **zero warnings is not
"this program is migrated"**. Read it as a worklist that empties, never as a certificate.

The suffixes are derived from the vocabulary — every curated minor-unit word and every
[ratio unit](#ratio-units-percent-and-basis_point) name, plus plurals — so giving a currency a
minor unit, or adding a ratio unit, extends the lint with no second edit. What stays
hand-maintained is what no vocabulary holds: retired spellings, and the abbreviations `bps`
and `pct`. That half is *expected to shrink*, so the union asserts the two halves do not
overlap; when ratio units landed on 2026-09-12 it was the assertion that named `percent` and
`basis_points` as words to drop.

---

## Tables: a declaration that defines the predicate

Much published money is in TABLES, not single facts. Declare the table and it **defines the
predicate your rules already call** — so a program migrates by replacing N fact lines with one
declaration, and no call site changes:

```clausal
-import_from(united_states, [usd, usd_cent])
-constants_number_currency(benefit_cap/2,
                           [(1, 29200), (2, 53600), (3, 76800)],
                           usd_cent, money_at(2))
```

```text
benefit_cap(2, A)        A = 536.00 (usd)
benefit_cap(SIZE, A)     (1, 292.00) (2, 536.00) (3, 768.00)
```

**There is no `constant(...)` retrieval and no subscript.** `constant/1` substitutes a single
value at *compile* time; a table is a lookup by key at *runtime*, which is a predicate call —
so the rows are reached exactly as hand-written facts were.

`-constants_number_units(name/arity, ROWS, unit, number_at(N))` is the general-unit sibling,
matching [`-constant_number_units`](#declaring-money-constant_number_currency); the money form
refuses a unit that is not money, and each names its own column keyword.

**The money column is declared, never inferred** — real tables put it in arg 2 of 2, in arg 3
of 4, and beside a two-date validity window, so any positional rule would guess wrong on one
of them, silently. The money cell must be a written number: a table row is data, not an
expression.

---

## Minor units

**Ruled 2026-09-11.** This supersedes an earlier ruling of the same day, "there is no
minor-unit currency, and there will not be"; [what changed](#what-changed-and-why) is
recorded below rather than deleted.

A minor unit is an **ordinary scaled unit** of its base currency, defined in the same
jurisdiction module as the currency itself — the same shape as `kilometre` against `metre`:

```clausal
-import_from(united_states, [usd, usd_cent])

# what the source SAID, in the unit it said it in
-constant_number_units(monthly_limit, 155000, usd_cent)
```

```text
stored                    1550.00 (usd)       Decimal('1550.00'); one representation, always
constant_value/2          1550.00 (usd)
constant_number_units/3   155000, usd_cent    what the declaration said
```

The point is that the declaration names the **currency and the scale where the engine can
see both**, instead of encoding them in the parameter's identifier —
`monthly_limit_cents` — where only a human can read them. A scale in a name is
documentation the engine cannot check; a declared unit is a fact it can.

After declaration the constant simply **is** a dollar amount, which is what makes minor and
major amounts add with no conversion logic and no mixed-dimension arithmetic:

```clausal
-import_from(european_union, [euro, eur_cent])

total(T) <- (eval_(5000 (eur_cent), A), eval_(10.00 (euro), B), eval_(A + B, T))   # T = 60.00 (euro)
```

Being an ordinary unit, a minor unit works in a declaration, in the `155000 (usd_cent)` annotation
sugar and in arithmetic — there is no special case anywhere, and nothing to remember about
where the spelling is legal.

## Decimal strings: declaring the digits

**Ruled 2026-09-12.** A written `292.00` is a Python **float literal**, and it has already lost
its trailing zero by the time any quantity exists:

```text
-constant_number_units(fee, 292.00, usd)     stores  Decimal('292.0')
-constant_number_units(fee, "292.00", usd)   stores  Decimal('292.00')
```

Same number, different scale, and the scale is the part the source wrote. Nothing downstream can
recover it — by the time the value reaches a `Quantity` the digits are gone.

So a **string in the number position is read as an exact `Decimal`**, in all four members of the
family:

```clausal
-import_from(united_states, [usd])

-constant_number_units(s_fee, "292.00", usd)
-constant_number_currency(s_limit, "1550.00", usd)
```

This is the counterpart of [minor units](#minor-units), reached from the other side. A minor unit
keeps a published "29200 cents" recoverable by declaring the **scale**; a decimal string keeps a
published "292.00 dollars" exact by declaring the **digits**. Use whichever the source text uses.

**Only the directives named for carrying a unit.** `-constant_value(greeting, "292.00")` is a
string constant and stays one — reading strings as numbers there would silently retype every text
constant in every program.

**What is still refused**, because the directive is named for the claim that only numbers carry
units: a string that is not a number (`"abc"`), and the non-finite Decimals (`"NaN"`,
`"Infinity"`) which parse perfectly well and are not amounts. The currency precision check is
unchanged and now runs against an exact value, so `-constant_number_currency(x, "19.999", usd)`
is still refused for sub-scale digits.

`constant_number_units/3` reports the **Decimal**, not the string: the string is how the
magnitude was spelled, not what was declared.

**The scale does not survive EXPORT**, though the magnitude does. Prolog has no decimal type, so
an exported `1550.00` is read as a float and prints as `1550.0` (measured 2026-09-13 in both
Scryer and Trealla). A decimal string keeps the declared scale exact inside the engine; at the
Prolog boundary only the number crosses.

**One consequence worth knowing for the migration.** The [scale lint](#bare-integers-are-not-money)
keys on a bare numeric literal, so a site converted to the string form goes silent — correctly,
since it now carries its unit, but it means the warning count falls for string migrations as well
as unit ones. As ever, a falling count is evidence of progress rather than a measure of it.

## Ratio units: `percent` and `basis_point`

**Landed 2026-09-12**, unchanged from the mechanism minor units proved. A ratio is a pure
number written at a scale — 300 basis points **is** the ratio 0.03 — so a ratio unit is an
ordinary scaled unit against the *dimensionless* base rather than a currency:

```clausal
-import_from(py.units, [basis_point])

# what the regulation SAID, in the unit it said it in
-constant_number_units(min_margin, 300, basis_point)
```

```text
stored                     Decimal('0.0300'), dimensionless   one representation, always
constant_value/2           Decimal('0.0300'), dimensionless
constant_number_units/3    300, basis_point                  what the declaration said
```

Same bargain as the currency half: the declaration carries the scale where the **engine** can
read it, so a program can stop carrying it in a parameter's name. `minimum_margin_bps` can
go back to being `minimum_margin`.

Both units are dimensionless, so `300 (basis_point)` and `3 (percent)` are the **same
quantity** and compare equal — a program declares in whichever spelling its source uses and
the arithmetic does not care which was chosen. A ratio multiplies against money and keeps the
money's dimension:

```clausal
-import_from(py.units, [basis_point])
-import_from(united_states, [usd])

charge(C) <- eval_(300 (basis_point) * 1550.00 (usd), C)   # C = 46.50000 (usd), exact
```

**The factor is a `Decimal`, built with `scaleb`, and that is the whole safety argument.** A
scaled unit returns from `Quantity.__init__` before the currency coercion runs, so exactness
here is not inherited from the money path — it comes from a float magnitude being read beside
a `Decimal` factor as `Decimal(str(f))`. `5.25 (percent)` is therefore exactly `0.0525`. Give
a unit a *float* factor instead and that stops: `gram = Quantity(1e-3, {kilogram: 1})` is why
`7 gram` is not exactly 0.007. A ratio multiplies against the thresholds that decide a case,
which makes it the last place to reintroduce binary floating point.

Adding a ratio unit is one entry in `RATIO_UNITS` in `clausal/modules/units.py` plus its
binding; that table is the **authority**, and the
[scale lint](#bare-integers-are-not-money) and the exporter both enumerate from it rather
than from a list written beside them.

**Two limits, both deliberate.** A bare number is [never compatible with a ratio
unit](#asserting-a-unit-compatible_units2) — once ratios are dimensionless, a bare `0.03`
would otherwise satisfy every ratio claim there is. And the Prolog exporter treats a
ratio unit like every scaled unit (see [below](#the-prolog-exporter-and-scaled-units)): a
**declaration** exports its base magnitude (`-constant_number_units(min_margin, 300,
basis_point)` exports `0.0300`, never `300`), while an **inline** `300(basis_point)` is
refused, because units are discarded on export and dropping `basis_point` would emit `300`
against a stored `0.03`, a 10000x error.

**What ratio units do not solve**, and it is the same shape the currency half left open: a
module whose *public interface* computes in basis points — a `margin_ratio_bps/2` it exports
— still has to rescale its producers and consumers together. This makes that conversion
cheaper, because no representation changes at any interface, not free.

## Declaring money: `-constant_number_currency`

`-constant_number_units` takes any unit. When the constant is **money**, say so:

```clausal
-import_from(united_states, [usd])
-constant_number_currency(monthly_limit, 5000, usd)     # stored Decimal('5000') usd
```

The directive is named for its claim and enforces it, exactly as
`-constant_number_units` is named for "only numbers carry units". The third argument must be
**money**, which is a *shape* and not a type: **one currency at exponent one**. That admits a
currency and a [minor unit](#minor-units) of one, and nothing else:

```text
usd          ok          usd / second   refused — a rate, not an amount
usd_cent     ok          usd ** 2       refused — an area in dollars
                         metre          refused — not money at all
```

Shape rather than type because the property the declaration asserts is *this constant is
money*, and a minor unit satisfies it. Requiring a currency object split the two safety
properties so that an author could have the currency gate or the minor-unit scale but never
both — and the identifiers a migration to declared money meets are typically spelled
`_cents`, `_satang` or `_pence`, so the narrow gate would have covered exactly the case the
migration is least likely to produce.

```text
-constant_number_currency(fee, 5000, metre)

TypeError: -constant_number_currency: `fee` declares money, but <unit metre> is not
an amount of money. The unit must be a currency or a minor unit of one — one
currency at exponent one — so a rate (`usd / second`) or a power (`usd ** 2`) is
not accepted either. Use -constant_number_units for a quantity that is not money.
```

That is the gap it closes, and it is worth being precise about which one. A **mistyped or
unbound** currency was already caught — a currency identifier has to be bound to be written,
so `-constant_number_units(fee, 5000, dollar)` is a `NameError`. What was not caught is a
unit that loads perfectly well and **is not money**: `-constant_number_units(fee, 5000,
metre)` yields `Quantity(5000, metre)`, an int-valued length, in silence. Asking for money
and getting a length is the error this refuses.

Two further properties, each with a test:

* **A compound unit is refused.** Money is an amount, not a rate; `usd / second` is a good
  unit expression and belongs to the general directive.
* **Everything else is inherited**, deliberately: the value must be a number, the
  [precision check](#the-precision-check) still rejects sub-scale digits, and the constant is
  still visible through [`constant_number_units/3`](#minor-units) with its declared pair. A
  stricter declaration of the same fact does not hide it from the view that already exists.

---

### Which currencies have one

| Import | Minor unit | Factor |
|--------|-----------|--------|
| `european_union` | `eur_cent` | 1/100 euro |
| `united_states` | `usd_cent` | 1/100 dollar |
| `australia` | `aud_cent` | 1/100 dollar |
| `united_kingdom` | `penny` | 1/100 sterling |
| `thailand` | `satang` | 1/100 baht |

**A shared subunit word carries its currency in its name; a unique one does not.** `cent`
belongs to the euro, the US dollar and the Australian dollar alike, so the bare word names
none of them and is not bound — `eur_cent`, `usd_cent`, `aud_cent`. `penny` is sterling's
alone and `satang` is the baht's alone, so they stay bare. The rule is derived from the
curated word table, not written per currency.

This is not decoration. It closes two holes by construction:

* `-import_from(european_union, [euro, eur_cent])` followed by
  `-import_from(united_states, [usd, usd_cent])` used to bind `cent` **twice, silently,
  last-one-wins** — and a rulebase computing throughout in what it believed were euro cents
  would be holding dollars and never raise, because nothing would ever meet a euro amount to
  mismatch against. Two minor units can now be imported into one file.
* `constant_number_units/3` reports the declared **spelling**, so the spelling has to carry
  the currency. Both sides previously answered `cent`, and the qualified `united_states.cent`
  that would have disambiguated records nothing at all — `_units_ast_to_term` returns `None`
  for an attribute, so that declaration has no `/3` answer.

Minor-unit *names* are not in ISO 4217 — the standard carries only the number of decimal
places — so they are curated data, added per currency as a rulebase needs one. See
`MINOR_UNITS` in [`scripts/gen_currencies.py`](#extending-the-vocabulary). This set covers
the currencies that programs were found carrying a minor-unit scale for in identifier names.

Names are **singular**, as every unit name in the vocabulary is (`metre`, not `metres`): GBP's
subunit is `penny`, even where a rulebase spells its own identifiers `_pence`.

A minor unit is **jurisdiction-scoped**, and since a shared word is not bound bare, the
identifier already says which. A cent of one currency still never adds to a cent of another.

```clausal
-import_from(united_states, [usd, usd_cent])
-import_module(european_union)

us(A) <- eval_(5000 (usd_cent), A)        # A = 50.00 (usd)
eu(A) <- eval_(5000 (european_union.eur_cent), A)   # A = 50.00 (euro)
```

### The factor is derived, never written

`_make_minor_unit(usd)` builds `Quantity(Decimal(1).scaleb(-usd.scale), {usd: 1})`.
Two properties are load-bearing:

* the factor comes from the currency's **own ISO scale**, so it cannot drift from the scale
  the rounding and formatting paths use: `_make_minor_unit` on a scale-3 currency yields
  a factor of `Decimal('0.001')`, not `0.01`, without anyone restating the scale; and
* it is a **`Decimal`**, built with `scaleb` rather than written as a literal. `gram` is
  `Quantity(1e-3, {kilogram: 1})` — a *float* factor, which is why `7 gram` is `0.007` in
  binary floating point. A factor is the one place money could get back into floats.

A **scale-0 currency has no minor unit** and asking for one raises: 16 currencies (yen, won,
…) have no subunit in circulation, and one invented at scale 0 would make `1 minor` equal
`1 yen`.

### The gate this makes possible

Because `/3` reports the **declared** pair, a parameter whose name ends `_cents` but whose
declaration does not say a minor unit is now a *mechanically checkable* defect. That is the
"documented but not represented" problem closed — and eventually the suffix disappears from
the name entirely, because the declaration carries it.

### The Prolog exporter and scaled units

`clausal_to_prolog` discards units on export, which is faithful for a **base** unit (a
currency, `metre`, `second`, or a factor-1 derived unit like `newton`) and wrong for a
**scaled** one unless the magnitude is converted first. The two shapes are handled
differently:

* A **declaration** exports the magnitude the engine holds, converted exactly to the base
  unit:

  ```text
  -constant_number_units(monthly_limit, 155000, usd_cent)   exports   1550
  -constant_number_units(min_margin, 300, basis_point)      exports   0.0300
  ```

  An integral result is emitted as an integer; a fractional amount stays a decimal number,
  which Prolog reads as a float (Prolog has no decimal type).

* An **inline** quantity in a scaled unit, `pay(155000(usd_cent))`, is still **refused**:

  ```text
  NotImplementedError: clausal_to_prolog: 155000(usd_cent) is a quantity in a scaled unit
  (usd_cent), and units are discarded on export -- which keeps the written magnitude, not
  the one the engine holds once a unit rescales. Write the amount in a base unit, ...
  ```

  The same refusal covers `30(day)` and `5(kilometre)`: the defect was never
  currency-specific — `day` is `Quantity(86400, second)`, so an exported `30` was never the
  2592000 the engine holds. Declare such an amount as a constant, or write it in a base unit.

### What changed, and why

The earlier ruling gave three reasons against a minor unit. The first is **answered** by
naming the currency in the unit; the other two were **measured on this tree and do not
hold**:

1. *`cent` is ambiguous — euros have cents, dollars have cents.* Answered twice over. Each
   minor unit lives in its jurisdiction module, so they are distinct units that never add, by
   the rule that already governs `dinar`; and because the word `cent` is shared, it is not
   bound bare at all — the amount is written `eur_cent` or `usd_cent`, which says which at
   the site rather than at the import.
2. *A scaled minor unit would silently rescale `5000 eur_cent` to `50`.* It rescales — to
   `Decimal('50.00') euro`, which is the correct amount and the single representation the
   design wants. The 100× error described was a misreading: normalisation multiplies by the
   factor.
3. *It would put money in floats.* Measured false: the currency constructor coerces through
   `Decimal(str(f))`, so even `Quantity(0.01, {usd: 1})` stores `Decimal('0.01')`. The
   float hazard `gram` demonstrates is real for physical units and blocked for currency —
   and `_make_minor_unit` never writes a factor literal anyway.

Decimal amounts in the **base** currency remain exact and remain correct — minor units record
what a source *said*, they do not make the base form insufficient:

```clausal
-import_from(european_union, [euro])
-constant_number_units(rate, 0.10, euro)

# 0.1 + 0.1 + 0.1 is exactly 0.3 (euro) -- a float would give 0.30000000000000004
sums(X) <- eval_(constant(rate) + constant(rate) + constant(rate), X)
```

Use [`eval_/2`](arithmetic.md) to *compute* an amount. A comparison (`==`, `>`, `<=`, …)
between amounts works directly and respects the currency, and `X == A + B` with `X` unbound
binds `X` to the sum. But `==` is a constraint, and inside a constraint division is rational
(see [Operators](operators.md)), so `X == 7.89(euro)` answers a magnitude of
`Fraction(789, 100)` rather than `Decimal('7.89')`: the same amount, not the same
representation.

**Ratios are covered too** — see [ratio units](#ratio-units-percent-and-basis_point).

**And durations are not units at all** — see [`date_add/3` and `days_between/3`](builtins.md).
A "within 30 days" rule is a relation between two dates, not a quantity: months vary in
length and business days need a holiday calendar, neither of which a scalar can express.

## Arithmetic rules

Inherited from [units](units.md); currency just keeps the magnitude exact. The general
rules for each operator are in [Arithmetic](arithmetic.md) and [Operators](operators.md).

| Operation (inside `eval_/2`) | Behaviour |
|-----------|-----------|
| `euro + euro`, `euro - euro` | same currency required; **full precision kept** (no rounding) |
| `euro + usd` | `UnitsMismatch` — different currencies never combine |
| `euro + 5` | `UnitsMismatch` — a currency amount and a plain number never add |
| `euro * 3`, `euro * 20(percent)`, `euro * rdiv(6, 5)` | scale by an exact dimensionless number → euro |
| `euro * 0.2` | **refused**: `type_error(exact_number, 0.2)` — a float beside an exact amount; write the factor exactly (`20(percent)`, `rdiv(1, 5)`) |
| `euro / 4` | exact: `10.00(euro) / 4` is `2.5 (euro)`, magnitude `Decimal('2.5')` |
| `euro / 3` | exact: `10.00(euro) / 3` is `10/3 (euro)`, magnitude `Fraction(10, 3)` — never a 28-digit rounded `Decimal` |
| `euro / 0` | `evaluation_error(zero_divisor)` in `eval_/2`; inside a constraint (`X == 1(euro) / 0`) the goal fails |
| `euro / euro` | a **dimensionless** ratio (e.g. for “what fraction of …”) |

```clausal
-import_from(european_union, [euro])
-import_from(py.units, [percent])

vat(NET, VAT) <- eval_(NET * 20 (percent), VAT)       # exact
share(S) <- eval_(10.00(euro) / 3, S)                   # S = 10/3 (euro), Fraction(10, 3)
```

**Rounding is never automatic.** Intermediate results keep every digit; you quantize only
at display (below). So `10.00(euro) / 3` stays `10/3` internally and becomes `"3.33 EUR"`
only when you ask.

---

## Rounding and display

Every rounding/display predicate takes a **required, explicit mode**. The mode and style
are atoms, written bare once the module declares them (`-private([half_up, symbol])`); a
string (`"half_up"`) is accepted too.

**Modes:** `half_up`, `half_even` (banker's), `half_down`, `up`, `down`, `ceiling`, `floor`.

- `money_round(Amount, Mode, Out)` — `Out` is `Amount` quantized to the currency's scale,
  still a currency amount.
- `money_str(Amount, Mode, Str)` — `"3.33 EUR"` (value + ISO code), a **string**.
- `money_format(Amount, Style, Mode, Str)` — `Style` ∈ `symbol` (`'€3.33'`), `code`
  (`'3.33 EUR'`), `name` (`'3.33 euro'`), `plain` (`'3.33'`), answered as an **atom**.

The argument is an amount, so compute it first; `money_round(10.00(euro) / 3, …)` would hand
the rounding predicate the unevaluated term and fail.

```clausal
-import_from(european_union, [euro])
-import_from(currency, [money_precise, money_round, money_str, money_format])
-private([half_up, symbol])

r(R) <- (eval_(10.00(euro) / 3, Q), money_round(Q, half_up, R))          # R = 3.33 (euro)
s(S) <- (money_precise("2.675", euro, P), money_str(P, half_up, S))       # S = "2.68 EUR" (not 2.67: no float trap)
f(S) <- (money_precise("3.345", euro, P), money_format(P, symbol, half_up, S))   # S = '€3.35'
```

An unknown mode or style raises (catchable — see below).

**Python / f-strings.** A currency `Quantity` also formats in Python f-strings (inside a
`++()` escape or interop), spec `"<style>[,<mode>]"`, default style `code`, default mode
`half_even`:

```python
# amt is 3.345 (euro)
f"{amt}"              # "3.34 EUR"
f"{amt:symbol}"       # "€3.34"
f"{amt:name}"         # "3.34 euro"
f"{amt:plain,half_up}"# "3.35"
```

---

## Accessors

Query a currency's metadata (the argument is the currency, e.g. `euro`):

```clausal
-import_from(currency, [currency_scale, currency_code, currency_symbol,
                        currency_start, currency_end])
-import_from(european_union, [euro])
-import_from(germany, [dem])

facts(N, C, S) <- (currency_scale(euro, N),    # N = 2
                   currency_code(euro, C),     # C = "EUR"   a string
                   currency_symbol(euro, S))   # S = '€'     an atom
history(S, E) <- (currency_start(dem, S),      # S = '1948-06-20'  an ISO date, as an atom
                  currency_end(dem, E))        # E = '2002-05-15'; euro's end is None (still current)
```

**An unbound currency RAISES.** An accessor is a function of a currency, so asking with an
unbound first argument asks nothing — and answering nothing is the fail-open shape, where a
typo'd field or an unbound variable becomes "no answer" and the rule silently does not fire.
`currency_scale`, `currency_symbol`, `currency_start` and `currency_end` all raise
`instantiation_error` instead.

### `currency_code/2` is a relation, not an accessor

A code identifies a currency — 254 currencies, 254 distinct ISO codes — so it runs in every
direction:

```text
currency_code(euro, X)      X = "EUR"       the canonical UPPERCASE string
currency_code(C, eur)       C = euro        an atom, in either case
currency_code(C, "EUR")     C = euro
currency_code(C, ++"EUR")   C = euro        a Python string
currency_code(C, Code)      enumerates all 254
```

**The code may be written as an atom or a string.** `"EUR"` written in a `.seam` or
`.clausal` file is a *string* (the default `-double_quotes(chars)`), `eur` or `'EUR'` is an
*atom*, and `++"EUR"` hands in a Python `str`, which is an atom too. All of them reach the
same currency; `currency_code(euro, X)` answers the string.

Case-insensitive, which covers the two spellings that **can** exist: `eur` and `"EUR"`. A
mixed-case `Eur` is not a misspelled code — TitleCase is a logic *variable*, so it would
become a fresh variable and match anything.

**Enumeration yields all 254, historical included**, because the relation must be complete:
the forward mode answers for a withdrawn currency, so the reverse and the enumeration have to
reach it too. *Is this a current currency* is a different question, and `currency_end/2`
answers it — a current currency's end is `None`. A rulebase validating user input against
"real currencies today" wants that filter, not this relation.

---

## Type tests: a quantity IS a number

`number/1` is true of a **`Quantity`** as well as an int or a float — a quantity is a number
carrying a unit — and `quantity/1` says so explicitly:

```text
number(10000(euro))    succeeds        quantity(10000(euro))   succeeds
number(10000)          succeeds        quantity(10000)         fails
integer(10000(euro))   fails           float_(10000(euro))     fails
```

**This exists because the alternative was silent and catastrophic.** A program that sums
money behind a `number(V)` guard — the documented shape in real conformance rules, where *a
member whose key is absent or non-numeric contributes nothing, and an empty list totals 0* —
would, on attaching units, total **zero for every field**, compare 0 against 0 in every
consistency rule, and report a whole conformance surface as satisfied with a green suite.

Accepting inverts the failure mode rather than merely widening the test. Code that guards and
then does **bare** arithmetic raises loudly at the site:

```text
number(V), V > 0                 error(system_error(units_mismatch), (>)/2)
                                 message: plain number: dimensionless vs euro
sum_list([1(euro), 1(usd)], S)   UnitsMismatch: Unit mismatch for add: euro vs usd
```

`integer/1` and `float_/1` stay **strict**: they name a specific representation and a quantity
is neither. Widening those would make `integer(V)` — which is how a program asserts
minor-unit scale — silently true for an amount in any scale at all.

`sum_list/2` seeds from the **first element** rather than a bare `0`, so a list of money
totals rather than raising on `0 + Quantity`. An empty list still gives `0`, plain lists are
unchanged, and mixing currencies still raises.

> **ISO note.** ISO says `number/1` is true of integers and floats only. A `Quantity` cannot
> occur in an ISO `.pl` program, so no conforming program can observe the difference.

---

## Asserting a unit: `compatible_units/2`

[`has_units/2`](units.md) answers "does this carry that unit?" by **succeeding or failing**.
In a goal position a failure is swallowed — the guard does not fire, the rule does not fire,
and the caller gets "no" rather than "you passed the wrong thing". When the answer matters,
assert it:

```clausal
-import_from(py.units, [compatible_units])
-import_from(european_union, [euro])

# raises UnitsMismatch unless AMOUNT is a euro quantity
positive_fee(AMOUNT) <- (compatible_units(AMOUNT, euro), AMOUNT > 0.00(euro))
```

```text
compatible_units: expected usd, got aud
compatible_units: 5 carries no unit, so it cannot be euro. A bare number is never
compatible, not even with dimensionless — write the quantity (`5(euro)`), or declare
it with -constant_number_currency.
```

It raises [`UnitsMismatch`](#errors-and-catch3), so `catch/3` catches it and binds the
message exactly as for a mismatch raised by arithmetic.

**Scale is ignored, because by here it has already been applied.** A scaled unit normalises
at construction, so `155000 usd_cent` *is* `Decimal('1550.00') usd` and `5 kilometre` is 5000
metres. What is left to check is the dimension, and a minor unit names the same one as its
currency:

```text
compatible_units(155000(usd_cent), usd)       succeeds
compatible_units(155000(usd_cent), usd_cent)  succeeds
compatible_units(5(kilometre), metre)         succeeds
```

That is also what makes [ratio units](#ratio-units-percent-and-basis_point) work.
`basis_point` and `percent` are both dimensionless *with a scale factor*, so both normalise
and `300 basis_point` compares equal to `3 percent` — the same right answer from either
spelling.

**A bare number is never compatible, not even with `dimensionless`.** This is deliberately
stricter than the arithmetic, which does let a bare number add to a dimensionless quantity.
The predicate asserts that a value IS a quantity carrying a unit, and a bare number satisfies
no unit claim — and it is the only version that closes the hole for ratios, where a bare
`0.03` would otherwise pass as "dimensionless" and wave through the case the check exists to
catch. A dimensionless *quantity* — a ratio built by division, say — passes.

---

## Errors and `catch/3`

Two catchable exceptions, and one warning.  Both exceptions are Python classes, so a `.clausal` file names
them in its import list and catches them with a `++` catcher (see
[Clausal exceptions](exceptions.md)): the bare class `++CurrencyPrecisionError`
matches by `isinstance`; the instance form `++UnitsMismatch(M)` also binds `M`
to the message.

- **`UnitsMismatch`** — combining different currencies, or a currency with a plain number,
  in arithmetic (`eval_/2`, `sum_list/2`) or in `compatible_units/2`.
- **`CurrencyPrecisionError`** — tagging a value with sub-scale precision.

A **comparison** across dimensions (`V > 0` with `V` a euro amount) raises the ISO error
term `error(system_error(units_mismatch), (>)/2)` instead; catch it with an ordinary
`error(system_error(units_mismatch), _)` pattern.

```clausal
-module(prices, [safe_price(TEXT, P), checked_sum(A, B, RESULT), mismatch(MESSAGE)])
-import_from(clausal.terms, [CurrencyPrecisionError, UnitsMismatch])
-import_from(currency, [money, money_precise, money_round])
-import_from(european_union, [euro])
-private([half_up])

# recover from an over-precise input: take it exactly, then round explicitly
safe_price(TEXT, P) <- catch(
    money(TEXT, euro, P),
    ++CurrencyPrecisionError,
    (money_precise(TEXT, euro, RAW), money_round(RAW, half_up, P)))

# report a currency mismatch instead of aborting, keeping the message
checked_sum(A, B, RESULT) <- catch(
    eval_(A + B, RESULT),
    ++UnitsMismatch(M),
    RESULT is mismatch(M))
```

`safe_price("7.891", P)` answers `P = 7.89 (euro)`; `checked_sum` over a euro and a dollar
amount answers `mismatch("Unit mismatch for add: euro vs usd")`.

An uncaught `CurrencyPrecisionError` / `UnitsMismatch` aborts the query. Note a currency
mismatch is a *hard error*, not a silent failure — you must handle it if a rule may see
mixed currencies.

### And one warning

**`ClausalCurrencyLiteralWarning`** (`clausal.lint_warnings`) — a float money magnitude
carrying 16 or more significant digits, i.e. one in the band where
[the written literal may already have been rounded](#float-literals-are-exact-to-15-significant-digits).
Not an exception and not catchable with `catch/3`: nothing has gone wrong *yet* and the
amount may be perfectly correct — it is the only signal available, because by the time the
currency code runs there is a float and no record of what was typed. Silence it the way the
other lints are silenced, with `warnings.filterwarnings` on the class.

---

## Applying currency to existing rules

Guidance for converting an existing set of rules to use currency.

**1. Decide what is money.** A number denotes money when the regulation or contract attaches it
to a currency (a price, fee, threshold, penalty, balance). Tag those — bare numbers lose the
dimension safety and exactness that are the whole point.

**2. Pick the currency by jurisdiction.** The rules' jurisdiction fixes the currency:
a UK regulation → `sterling` from `united_kingdom`; a eurozone directive → `euro` from
`european_union`. Import the bare name; the prefix only appears when a rule genuinely spans
currencies.

**3. Migrating from the old `currency.<code>` atoms.** A common legacy pattern exposes ISO
alpha-3 codes as atoms (`currency.eur`, plus `all`/`try_` escapes). Replace them:
- `currency.eur` → `euro` (from `european_union`); `currency.usd` → `usd`
  (`united_states`); `currency.gbp` → `sterling` (`united_kingdom`); `currency.jpy` → `yen`
  (`japan`); the `try_`/`all` escapes disappear entirely.
- A bare number that was *implicitly* an amount in a given currency becomes `N(currency)`.
- Anything that only *named* a currency (metadata, a “currency of this contract” slot) uses
  the currency object itself (`euro`), and its code/symbol via the accessors.
- Every active ISO 4217 currency already ships (see [The vocabulary](#the-vocabulary)) —
  find the right jurisdiction module and import the bare name. Only truly missing/new
  currencies need [adding](#extending-the-vocabulary); never fall back to a bare atom code.

**4. Common patterns.**

```clausal
-import_from(european_union, [euro])
-import_from(py.units, [percent])
-import_from(currency, [money_precise, money_round])

# a threshold comparison (same currency; comparison respects dims)
over_limit(AMOUNT) <- (AMOUNT > 1000(euro))

# a percentage / tax rate: an exact dimensionless factor (a float factor is refused)
with_vat(NET, GROSS) <- eval_(NET * 120 (percent), GROSS)     # GROSS keeps full precision
vat_due(NET, MODE, DUE) <- (eval_(NET * 20 (percent), RAW), money_round(RAW, MODE, DUE))

# summing line items: sum_list/2 totals a list of amounts; round once, at the end
order_total(ITEMS, TOTAL) <- sum_list(ITEMS, TOTAL)

# a per-unit price below display scale: money_precise
unit_price(P) <- money_precise("0.0034", euro, P)
```

**5. Pitfalls to avoid.**
- **Float-first maths.** Never compute in plain floats and then tag — `(0.1 + 0.2)(euro)`
  raises, and even where it wouldn't, it would carry drift. Keep money in Decimal from the
  first literal: `0.1(euro) + 0.2(euro)`.
- **Rounding mid-computation.** Don't `money_round` intermediates; keep full precision and
  round once at the boundary you actually report. Repeated rounding accumulates error.
- **Choosing a rounding mode by default.** There is none — the mode is required. Use the one
  the rule mandates (tax rules often say “round half up”); state it explicitly.
- **Cross-currency arithmetic.** If a rule can see mixed currencies, either it's a modelling
  error or you must convert *explicitly* (there is no built-in conversion) and `catch` the
  `UnitsMismatch`.

**6. Current limitations**: amounts above ~10²⁶
minor units, and `NaN`/`Infinity`, surface as raw/awkward errors; currency `__format__`
rejects generic alignment specs like `f"{amt:>10}"`. None affect ordinary legal amounts.

---

## Extending the vocabulary

The vocabulary is **generated** by `scripts/gen_currencies.py` (ISO 4217 minor units +
babel names/symbols) into `clausal/modules/countries/`: the authoritative table `_data.py`
and one self-contained module per jurisdiction. Jurisdictions are registered
**automatically** — the import resolvers fall back to any name in `_data.JURISDICTIONS`
(so no manual alias edits, unlike earlier versions).

To add or correct a currency, edit the generator (its scale-exception sets, `REGIONAL`,
`OVERRIDE_NAME`/`OVERRIDE_SYMBOL`) and rerun it. To give a currency a
[minor unit](#minor-units), add its ISO code to the generator's `MINOR_UNITS` table
with the subunit's NAME — the factor is never written there, `_make_minor_unit` derives it
from the currency's own scale:

```python
MINOR_UNIT_WORDS = {"EUR": "cent", "USD": "cent", "GBP": "penny"}   # ISO code -> subunit WORD
```

The bound NAME is derived from that table, not written: a word belonging to more than one
currency takes its ISO code as a prefix (`eur_cent`), a word belonging to one stays bare
(`penny`). So adding a currency whose subunit word is already in use renames nothing that
exists — but adding a *second* user of a currently-unique word would, which is why the
resolved `MINOR_UNITS` is emitted into `_data.py` where a test checks it against the rule.

```bash
python scripts/gen_currencies.py   # rewrites _data.py + the jurisdiction modules
```

(Minor-unit names are curated because ISO 4217 does not carry them — it gives only the
number of decimal places. A currency with no entry simply has no minor unit, which is the
honest state for one whose subunit a rulebase has never needed to write.)

For a one-off currency not covered by the generator, hand-add a module and append its name
to `JURISDICTIONS` in `_data.py`:

```python
# clausal/modules/countries/switzerland.py
from clausal.modules.countries._currency import _make_currency
franc = _make_currency("franc", iso_code="CHF", scale=2, symbol="Fr")
```

Scales must be the ISO 4217 minor unit (not babel/CLDR display precision, which differs for
some currencies).

---

*See also: [Physical units](units.md) — the dimensional-analysis machinery currency is built
on · [Arithmetic](arithmetic.md) · [Exceptions](exceptions.md) — `catch/3` · design rationale
in `docs/superpowers/specs/2026-07-22-decimal-currency-design.md`.*
