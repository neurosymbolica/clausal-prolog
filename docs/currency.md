# Currency amounts

Exact-decimal money for legal/financial rulebases. A currency amount is a
[`Quantity`](units.md) whose **magnitude is a `decimal.Decimal`** (never a binary
float) and whose **dimension is a currency** (`euro`, `usd`, …). Currencies are
units *base dimensions*, so all of dimensional analysis applies: euros add only to
euros, money scales only by dimensionless numbers, and mixing currencies is an error —
with **no implicit conversion** (exchange rates are not constants).

This page is the integration guide. If you are refactoring a rulebase to use currency,
read [Applying currency in a formalization](#applying-currency-in-a-formalization) first.

---

## Quick start

```clausal
-import_from(european_union, [euro])
-import_from(currency, [money, money_round, money_str, money_format])

# write an amount: value(currency) — the value is an exact Decimal
price is 7.89(euro)

# arithmetic keeps full precision; same-currency only
total <- (eval_(0.1(euro), A), eval_(0.2(euro), B), eval_(A + B, T_UNUSED))   # T = 0.30(euro), exact

# round / display with an EXPLICIT mode — each line below is its own
# independent predicate, not a continuation of the one above
show  <- money_str(T_UNUSED, half_up, S_UNUSED)              # S = "0.30 EUR"
euros <- money_round(some_amount, half_even, R_UNUSED) # R quantized to 2 dp, still a currency amount
sym   <- money_format(price, symbol, half_up, S_UNUSED)  # S = "€7.89"
```

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

**Single-currency rulebase** — import the bare name and never write the prefix:

```clausal
-import_from(japan, [yen])
budget is 1000000(yen)          # a Japanese statute means Japanese yen
```

**Multiple currencies** — import each, or qualify with the jurisdiction:

```clausal
-import_from(european_union, [euro])
-import_from(united_states, [usd])
-import_module(european_union)        # enables the qualified form below

eu_price is 10.00(euro)
us_price is 12.00(united_states.usd)   # qualified — same object as the bare `usd`
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
Ecuadorian rulebase (legal tender: US dollar) imports `usd` from `united_states`. Shared
regional currencies live in a regional module: `european_union.euro`,
`west_african_cfa.xof` (XOF), `central_african_cfa.xaf` (XAF), `cfp_franc.xpf` (XPF),
`east_caribbean.xcd` (XCD).

The full table is generated data — see
[`clausal/modules/countries/_data.py`](#extending-the-vocabulary). Scales come from ISO 4217
(so `won`/`yen` are 0, the Gulf dinars are 3); symbols are a common glyph where one exists,
otherwise the ISO code (the `symbol` display style then shows the code, e.g. `"THB19.99"`).

### Historical (and future) currencies

Withdrawn currencies ship too, so a rulebase can reason about obligations denominated in a
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
same `money_*` predicates. `19.99(mark) + 0.01(mark)` is `20.00(mark)`; `mark + euro` raises
`UnitsMismatch` (a Deutsche Mark is not a euro — conversion is explicit and out of scope).

---

## Writing amounts

### `value(currency)` — the normal form

```clausal
7.89(euro)        # → Quantity(Decimal("7.89"), euro)
1000(yen)         # → Quantity(Decimal("1000"), yen)   (yen has no minor unit)
1.234(dinar)      # → Quantity(Decimal("1.234"), dinar)
```

The written value becomes an **exact `Decimal`** — `7.89(euro)` is exactly 7.89, never the
binary-float `7.8899999…`. Integers and decimal literals both work.

### The precision check

Tagging a number as a currency **rejects any value with more decimal places than the
currency's scale**, raising [`CurrencyPrecisionError`](#errors-and-catch3):

```clausal
7.89(euro)     # ok
7.891(euro)    # RAISES — 3 dp for a 2-dp currency
7.5(yen)       # RAISES — yen has scale 0
1.234(dinar)   # ok — dinar has scale 3
```

This is deliberate: it catches money entering through lossy float arithmetic. The
canonical footgun is doing the maths in float **before** tagging:

```clausal
(0.1 + 0.2)(euro)      # RAISES — 0.1 + 0.2 computes in float first (0.30000000000000004)
0.1(euro) + 0.2(euro)  # correct — each literal is exact Decimal, added in Decimal space → 0.30
```

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
money("7.89", euro, P)              # P = 7.89(euro); "7.891" would raise
money_precise("0.0034", euro, Rate) # Rate = 0.0034(euro), sub-cent, allowed
```

Prefer `money("...", C, X)` (string) over `X(euro)` when the value comes from external data
you want parsed exactly with no chance of a float in the pipeline.

### Extracting the number

`strip_units/2` (from `py.units`) yields the bare `Decimal`:

```clausal
-import_from(py.units, [strip_units])
amount_value <- (eval_(7.89(euro), A), strip_units(A, V_UNUSED))   # V = Decimal("7.89")
```

---

## Bare integers are not money

A number that carries its scale only in an identifier — `minimum_leverage_bps(300)`,
`sga_monthly_amount_cents` — is a bare integer to the engine. Two failures follow, and
neither announces itself:

```text
two 'cents' integers, different currencies
  bare ints :  5000000 + 155000  ->  5155000      AUD and USD, silently summed
  as money  :  UnitsMismatch: dollar (AUD) vs dollar (USD)

a cents value against a dollars threshold
  bare ints :  155000 > 1550     ->  True         "exceeds the threshold"
  as money  :  1550.00 > 1550    ->  False        it does not
```

The second is the one to keep in mind: not a wrong number, a **reversed answer**.

**So the engine warns.** A name ending in a scale word (`_cents`, `_bps`, `_satang`,
`_pence`, `_percent`, …) that carries a bare numeric literal raises
`ClausalScaleInNameWarning`, once per (file, identifier):

```text
leverage_ratio.clausal:93: `minimum_leverage_bps` names a scale but carries a bare
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
minimum_leverage_bps(300),                                   warns
ratio_ok(P) <- check_ratio_gte(P, tier1, total, 300, …)      SILENT — 300 is the floor
```

Both lines are from one real domain, and the second is the one that decides; the first is a
fact nothing reads any more. So **an emptied warning list is not "this domain is done"** —
converting the site the lint names can silence a domain whose deciding literal is untouched.
Self-emptying is a genuine progress signal for the sites the lint *can* see, and it is not a
completeness claim.

Closing that gap needs a signal the source does not currently carry. The promising one is the
**callee's parameter**: if `check_ratio_gte/6`'s fourth parameter were itself declared to
take a ratio, the literal would be checkable at the call. A same-value or same-file heuristic
is not — it learns the cases it was built from.

The money suffixes are derived from the currency vocabulary — every curated minor-unit word
plus its plural — so giving a currency a minor unit extends the lint with no second edit.
The ratio words (`bps`, `basis_points`, `percent`, `pct`) are written out because ratios are
not units yet; that list shrinks to the derivation when they are.

---

## Minor units

**Ruled 2026-09-11.** This supersedes an earlier ruling of the same day, "there is no
minor-unit currency, and there will not be"; [what changed](#what-changed-and-why) is
recorded below rather than deleted.

A minor unit is an **ordinary scaled unit** of its base currency, defined in the same
jurisdiction module as the currency itself — the same shape as `kilometre` against `metre`:

```clausal
-import_from(united_states, [usd, usd_cent])

# what the filing SAID, in the unit it said it in
-constant_number_units(sga_monthly, 155000, usd_cent)
```

```text
stored            Quantity(Decimal('1550.00'), dollar)   one representation, always
constant_value/2  Quantity(Decimal('1550.00'), dollar)
constant_number_units/3   155000, usd_cent                   what the declaration said
```

The point is that the declaration names the **currency and the scale where the engine can
see both**, instead of encoding them in the parameter's identifier —
`sga_monthly_amount_cents` — where only a human can read them. A scale in a name is
documentation the engine cannot check; a declared unit is a fact it can.

After declaration the constant simply **is** a dollar amount, which is what makes minor and
major amounts add with no conversion logic and no mixed-dimension arithmetic:

```clausal
-import_from(european_union, [euro, eur_cent])

total(T) <- (eval_(5000 (eur_cent), A), eval_(10.00 (euro), B), eval_(A + B, T))   # 60.00(euro)
```

Being an ordinary unit, a minor unit works in a declaration, in the `155000 (usd_cent)` annotation
sugar and in arithmetic — there is no special case anywhere, and nothing to remember about
where the spelling is legal.

## Declaring money: `-constant_number_currency`

`-constant_number_units` takes any unit. When the constant is **money**, say so:

```clausal
-import_from(united_states, [usd])
-constant_number_currency(sga_monthly, 5000, usd)     # stored Decimal('5000') usd
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
both — and every identifier the corpus migration concerns is spelled `_cents`, `_satang` or
`_pence`, so the narrow gate would have covered exactly the case the migration is least
likely to produce.

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

Three further properties, each with a test:

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
the currencies a corpus census found carrying a minor-unit scale in identifier names.

Names are **singular**, as every unit name in the vocabulary is (`metre`, not `metres`): GBP's
subunit is `penny`, even where a rulebase spells its own identifiers `_pence`.

A minor unit is **jurisdiction-scoped**, and since a shared word is not bound bare, the
identifier already says which. A cent of one currency still never adds to a cent of another.

```clausal
-import_from(united_states, [usd, usd_cent])
-import_module(european_union)

us(A) <- eval_(5000 (usd_cent), A)        # 50.00(dollar)
eu(A) <- eval_(5000 (european_union.eur_cent), A)   # 50.00(euro)
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

### The Prolog exporter refuses a scaled unit

`clausal_to_prolog` folds a constant to its declared magnitude and discards the unit, which is
faithful for a **base** unit (a currency, `metre`, `second`, or a factor-1 derived unit like
`newton`) and wrong for a **scaled** one. `-constant_number_units(sga_monthly, 155000, usd_cent)`
would export as `155000` where the engine holds `Decimal('1550.00') dollar` — a 100× money
error. So it **refuses** rather than folding:

```text
NotImplementedError: clausal_to_prolog: -constant_number_units(sga_monthly, ..., usd_cent)
declares a constant in a scaled unit (usd_cent), and the exporter folds a constant to its
DECLARED magnitude -- which is not the magnitude the engine holds once a unit rescales.
Declare the constant in a base unit ...
```

The same refusal covers `30 day` and `5 kilometre`: the defect was never currency-specific —
`day` is `Quantity(86400, second)`, so the exported `30` was never the 2592000 the engine
holds. It also covers the **inline** form, `pay(155000(usd_cent))`, which reaches a different
lowering and had the identical defect; refusing one shape and not the other would leave a
hole in the middle of the guarantee. The two checks have opposite polarity on purpose — a
declaration is refused unless its unit is known to be a base unit, while an inline quantity
is refused only if its unit is known to be scaled, because that form is used throughout the
corpus and an unrecognised name there must keep working. Ruled 2026-09-11, after three independent censuses agreed nothing declares a constant
in a scaled unit today, so the refusal costs nothing and stops being free once the corpus
constants migration starts.

To export such a constant, declare it in the base unit — or lift the refusal by teaching the
exporter to fold to the base magnitude, which it can do: the `-import_from` it is already
converting says where the unit name resolves. See
`todo/exporter-folds-scaled-units-to-the-wrong-magnitude-2026-09-11.md`.

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

# 0.1 + 0.1 + 0.1 is exactly 0.30(euro) -- a float would give 0.30000000000000004
sums(X) <- eval_(constant(rate) + constant(rate) + constant(rate), X)
```

Use [`eval_/2`](arithmetic.md) for arithmetic on amounts, not `==`: CLP constraints do not
operate on `Quantity` objects and will raise `type_error`. Comparisons (`>`, `=<`) work
directly.

**Ratios are not covered by this.** There is still no `percent` or `basis_point` unit —
write the ratio as a plain decimal (`0.0525`), not `525` of a scaled unit. The minor-unit
mechanism generalises to them unchanged, and doing so is parked in
`todo/ratio-declaration-units-basis-points-and-percent-2026-09-11.md`; until it lands, a
scale encoded in a ratio's NAME is documentation the engine cannot check.

**And durations are not units at all** — see [`date_add/3` and `days_between/3`](builtins.md).
A statutory "within 30 days" is a relation between two dates, not a quantity: months vary in
length and business days need a holiday calendar, neither of which a scalar can express.

## Arithmetic rules

Inherited unchanged from [units](units.md); currency just fixes the magnitude to `Decimal`.

| Operation | Behaviour |
|-----------|-----------|
| `euro + euro`, `euro - euro` | same currency required; **full precision kept** (no rounding) |
| `euro + usd` | `UnitsMismatch` — different currencies never combine |
| `euro + 5` | `UnitsMismatch` — a currency amount and a plain number never add |
| `euro * 3`, `euro * 0.2` | scale by a dimensionless number → euro (the `0.2` is coerced to Decimal) |
| `euro / 3` | division keeps full precision — e.g. `10.00(euro) / 3` = `3.333…(euro)` |
| `euro / euro` | a **dimensionless** ratio (e.g. for “what fraction of …”) |

**Rounding is never automatic.** Intermediate results keep every digit; you quantize only
at display (below). So `10.00(euro) / 3` stays `3.333…` internally and becomes `"3.33 EUR"`
only when you ask.

---

## Rounding and display

Every rounding/display predicate takes a **required, explicit mode**. In `.clausal` the mode
and style are written as bare words.

**Modes:** `half_up`, `half_even` (banker's), `half_down`, `up`, `down`, `ceiling`, `floor`.

- `money_round(Amount, Mode, Out)` — `Out` is `Amount` quantized to the currency's scale,
  still a currency amount.
- `money_str(Amount, Mode, Str)` — `"3.33 EUR"` (value + ISO code).
- `money_format(Amount, Style, Mode, Str)` — `Style` ∈ `symbol` (`"€3.33"`), `code`
  (`"3.33 EUR"`), `name` (`"3.33 euro"`), `plain` (`"3.33"`).

```clausal
money_round(10.00(euro) / 3, half_up, R)   # R = 3.33(euro)
money_str(2.675(... via money_precise ...), half_up, S)   # S = "2.68 EUR"  (not 2.67 — no float trap)
money_format(P, symbol, half_up, S)        # S = "€3.35"
```

Unknown mode or style raises (catchable — see below).

**Python / f-strings.** A currency `Quantity` also formats in Python f-strings (inside a
`++()` escape or interop), spec `"<style>[,<mode>]"`, default style `code`, default mode
`half_even`:

```python
f"{amt}"              # "3.33 EUR"
f"{amt:symbol}"       # "€3.33"
f"{amt:name}"         # "3.33 euro"
f"{amt:plain,half_up}"# "3.35"
```

---

## Accessors

Query a currency's metadata (the argument is the currency, e.g. `euro`):

```clausal
-import_from(currency, [currency_scale, currency_code, currency_symbol,
                        currency_start, currency_end])
currency_scale(euro, N)     # N = 2
currency_code(euro, C)      # C = "EUR"   (a string)
currency_symbol(euro, S)    # S = "€"     (a string)
currency_start(mark, S)     # S = "1948-06-20"   (ISO date string)
currency_end(mark, E)       # E = "2002-05-15";  euro's end is None (still current)
```

---

## Errors and `catch/3`

Two catchable exceptions, and one warning.  Both exceptions are Python classes, so a `.clausal` file names
them in its import list and catches them with a `++` catcher (see
[Clausal exceptions](exceptions.md)): the bare class `++CurrencyPrecisionError`
matches by `isinstance`; the instance form `++UnitsMismatch(M)` also binds `M`
to the message.

- **`UnitsMismatch`** — combining different currencies, or a currency with a plain number.
- **`CurrencyPrecisionError`** — tagging a value with sub-scale precision.

```clausal
-import_from(clausal.terms, [CurrencyPrecisionError, UnitsMismatch])

# recover from an over-precise input
safe_price(TEXT, P) <-
    catch(money(TEXT, euro, P),
          ++CurrencyPrecisionError,
          money_round(... /* a fallback */, half_up, P)).

# treat a currency mismatch as a rule failure, keeping the message
catch(eval_(A + B, C), ++UnitsMismatch(M), 1 == 1)
```

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

## Applying currency in a formalization

Guidance for an instance refactoring a rulebase to use currency.

**1. Decide what is money.** A number denotes money when the statute/contract attaches it
to a currency (a price, fee, threshold, penalty, balance). Tag those — bare numbers lose the
dimension safety and exactness that are the whole point.

**2. Pick the currency by jurisdiction.** The rulebase's jurisdiction fixes the currency:
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
# a threshold comparison (same currency; comparison respects dims)
over_limit(Amount) <- Amount > 1000(euro).

# a percentage / tax rate — a dimensionless factor
with_vat(Net, Gross) <- eval_(Net * 1.20, Gross).       # 20% VAT; Gross keeps full precision
vat_due(Net, Mode, Due) <- (eval_(Net * 0.20, Raw), money_round(Raw, Mode, Due)).

# summing line items (fold with eval_); round once, at the end, for display
# a per-unit price below display scale → money_precise
unit_price(P) <- money_precise("0.0034", euro, P).
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

**6. Current limitations** (see the deferred-gaps note in the repo): amounts above ~10²⁶
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
