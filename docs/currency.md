# Currency amounts

Exact-decimal money for legal/financial rulebases. A currency amount is a
[`Quantity`](units.md) whose **magnitude is a `decimal.Decimal`** (never a binary
float) and whose **dimension is a currency** (`euro`, `dollar`, …). Currencies are
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
total <- (eval_(0.1(euro), A), eval_(0.2(euro), B), eval_(A + B, T))   # T = 0.30(euro), exact

# round / display with an EXPLICIT mode
show  <- money_str(T, half_up, S)              # S = "0.30 EUR"
euros <- money_round(SomeAmount, half_even, R) # R quantized to 2 dp, still a currency amount
sym   <- money_format(price, symbol, half_up, S)  # S = "€7.89"
```

---

## Importing currencies

Each currency is defined **once**, in its home **jurisdiction module**, and referenced
from there. Jurisdiction modules are spelled out (`european_union`, `united_states`, …) —
never ISO country codes (`is`/`in`/`as` collide with reserved words).

**Single-currency rulebase** — import the bare name and never write the prefix:

```clausal
-import_from(japan, [yen])
budget is 1000000(yen)          # a Japanese statute means Japanese yen
```

**Multiple currencies** — import each, or qualify with the jurisdiction:

```clausal
-import_from(european_union, [euro])
-import_from(united_states, [dollar])
-import_module(european_union)        # enables the qualified form below

eu_price is 10.00(euro)
us_price is 12.00(united_states.dollar)   # qualified — same object as the bare `dollar`
```

Two references to the **same** currency (bare-imported or module-qualified) are the same
dimension and add freely. Two **different** currencies are distinct dimensions and never
add — `euro + dollar` raises [`UnitsMismatch`](#errors-and-catch3).

### The vocabulary

The **full ISO 4217 set (all ~150 active currencies)** ships, one per home jurisdiction,
generated from ISO 4217 minor units. Import any by its jurisdiction module — the bare
currency name is the everyday word (`baht`, `rupee`, `won`, `franc`, `peso`, `dinar`, …):

| Import | Currency | ISO | Minor units (scale) | Symbol |
|--------|----------|-----|---------------------|--------|
| `european_union` | `euro` | EUR | 2 | € |
| `united_states` | `dollar` | USD | 2 | $ |
| `united_kingdom` | `sterling` | GBP | 2 | £ |
| `japan` | `yen` | JPY | 0 | ¥ |
| `bahrain` | `dinar` | BHD | 3 | BD |
| `thailand` | `baht` | THB | 2 | THB |
| `south_korea` | `won` | KRW | 0 | ₩ |
| `kuwait` | `dinar` | KWD | 3 | KWD |

(examples — the same-named `dinar` in `bahrain`/`kuwait`/`jordan`/… are **distinct**
currencies, kept apart by their jurisdiction module.) The home jurisdiction is the
currency's issuer, so a country using another's currency references the issuer — an
Ecuadorian rulebase (legal tender: US dollar) imports `dollar` from `united_states`. Shared
regional currencies live in a regional module: `european_union.euro`,
`west_african_cfa.franc` (XOF), `central_african_cfa.franc` (XAF), `cfp_franc.franc` (XPF),
`east_caribbean.dollar` (XCD).

The full table is generated data — see
[`clausal/modules/countries/_data.py`](#extending-the-vocabulary). Scales come from ISO 4217
(so `won`/`yen` are 0, the Gulf dinars are 3); symbols are a common glyph where one exists,
otherwise the ISO code (the `symbol` display style then shows the code, e.g. `"THB19.99"`).

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
amount_value <- (eval_(7.89(euro), A), strip_units(A, V))   # V = Decimal("7.89")
```

---

## Arithmetic rules

Inherited unchanged from [units](units.md); currency just fixes the magnitude to `Decimal`.

| Operation | Behaviour |
|-----------|-----------|
| `euro + euro`, `euro - euro` | same currency required; **full precision kept** (no rounding) |
| `euro + dollar` | `UnitsMismatch` — different currencies never combine |
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
-import_from(currency, [currency_scale, currency_code, currency_symbol])
currency_scale(euro, N)     # N = 2
currency_code(euro, C)      # C = "EUR"   (a string)
currency_symbol(euro, S)    # S = "€"     (a string)
```

---

## Errors and `catch/3`

Two catchable exceptions, both used via the `ClassName(Msg)` catcher form (like any
[Clausal exception](exceptions.md)):

- **`UnitsMismatch`** — combining different currencies, or a currency with a plain number.
- **`CurrencyPrecisionError`** — tagging a value with sub-scale precision.

```clausal
# recover from an over-precise input
safe_price(Text, P) <-
    catch(money(Text, euro, P),
          CurrencyPrecisionError(_Msg),
          money_round(... /* a fallback */, half_up, P)).

# treat a currency mismatch as a rule failure
catch(eval_(A + B, C), UnitsMismatch(_M), 1 == 1)
```

An uncaught `CurrencyPrecisionError` / `UnitsMismatch` aborts the query. Note a currency
mismatch is a *hard error*, not a silent failure — you must handle it if a rule may see
mixed currencies.

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

**3. Migrating from the old `currency.<code>` atoms.** The legacy clausify vocabulary
(`kit/currency.clausal`) exposed ISO alpha-3 codes as atoms (`currency.eur`, and the hacks
`all`/`try_`). Replace them:
- `currency.eur` → `euro` (from `european_union`); `currency.usd` → `dollar`
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
`OVERRIDE_NAME`/`OVERRIDE_SYMBOL`) and rerun it:

```bash
python scripts/gen_currencies.py   # rewrites _data.py + the jurisdiction modules
```

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
