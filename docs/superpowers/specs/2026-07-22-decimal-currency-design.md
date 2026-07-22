# Decimal currency amounts for Clausal — design

**Date:** 2026-07-22 · **Status:** approved for planning · **Repo:** `clausal`

## Problem

Clausal has no exact-decimal number type. Fractional literals (`3.14`) lex to Python
`float` (IEEE-754 binary), so money arithmetic drifts: `0.1 + 0.2 != 0.3`, and naive
rounding is wrong (`round(2.675, 2) == 2.67`). Legal rulebases reason over financial
amounts, where this is unacceptable. A `decimal.Decimal` can currently be passed in as a
ground Python value, but it is treated as an opaque head literal, conflates with `int`
under unification, and has no lexing, arithmetic, rounding, or rendering path.

Currency amounts also carry rules that plain numbers do not:

- Each currency has a **fixed minor-unit scale** (euro = 2, yen = 0, bahraini dinar = 3).
  Digits beyond that scale are incorrect **for display**.
- A currency amount may be **added/subtracted only to the same currency** — euro + dollar
  is an error, with **no coercion / no implicit conversion** (exchange rates are not fixed).
- A currency amount may be **multiplied or divided only by a dimensionless number**
  (a rate, a count), never added to one.

## Non-goals (explicitly out of scope)

- A general-purpose / bare `Decimal` literal usable anywhere. `3.14` stays `float`.
- "Decimal-by-default" (changing what all fractional literals mean). Rejected: Python
  raises `TypeError` on `Decimal + float`, and the physics-units feature legitimately
  stores float SI magnitudes (`inch = 0.0254`), so a global switch is disruptive.
- Translation / i18n of currency names (already handled elsewhere in Clausal; the N×M
  name matrix is not our concern here).
- Currencies whose minor unit is not a power of ten (e.g. "nearest 1000 units").
- Exchange-rate conversion between currencies.
- Cryptocurrencies; offset scales (Celsius/Fahrenheit-style) — units already excludes these.
- Broad resolution of the parked cross-type numeric identity items A01-D001 / A02-D002.
  We fix only the narrow `Decimal` **rendering** gap this feature needs.

## Key insight: currency is a units dimension

The existing `Quantity` / units feature (`clausal/terms.py`, `clausal/modules/units.py`)
**already enforces exactly the arithmetic rules currency needs**, verified in code:

- `Quantity.__add__` / `__sub__` require *identical* dims or raise `UnitsMismatch`
  (`terms.py` `_require_same_dims`); **no auto-conversion**.
- Dimensioned + plain number → `UnitsMismatch`; only *dimensionless* + plain number is allowed.
- `*` / `/` combine dimensions; scaling by a plain (dimensionless) number is allowed.

So each currency becomes its **own base dimension**. `euro + dollar` → `UnitsMismatch`
for free; `euro * 2` scales; `euro / euro` is a dimensionless ratio. The only two things
the units system lacks for money are: (1) the magnitude is `float`, not `Decimal`;
(2) there is no per-currency scale/code metadata or quantized display.

The design therefore has two layers:

1. **Language mechanics** (this feature, in `clausal`): Decimal-backed `Quantity`, exact
   literal capture, currency dimension metadata, rounding/display predicates, Decimal rendering.
2. **Currency vocabulary** (built-in, near units): jurisdiction modules defining currencies.

## Layer 1 — language mechanics

### 1.1 `Quantity` gains Decimal magnitudes

`Quantity._value` may be `int`, `float`, or `Decimal`. When the dimension is a **currency**,
construction coerces the magnitude to `Decimal`:

| Incoming magnitude | Coercion |
|---|---|
| `int` | `Decimal(n)` — exact |
| `Decimal` | as-is |
| source-literal (see 1.2) | `Decimal(<lexeme text>)` — **structurally exact** |
| runtime `float` | `Decimal(str(f))` — best-effort (see 1.3) |
| `str` | `Decimal(s)` — exact (the `money(...)` constructor) |

### 1.2 Exact literal capture (structurally exact)

A currency literal like `7.89(euro)` desugars through the existing `n(Unit)` call-sugar
(`clausal/templating/term_rewriting.py`) to a `Quantity` construction. The magnitude `7.89`
is otherwise lexed to a `float` first, and the compiler **cannot know at compile time that
`euro` is a currency** (units are runtime values). Two coordinated changes remove float from
the currency-literal path entirely:

- **Preserve the numeric literal's source lexeme.** The tokenizer keeps the raw text of
  `INTEGER`/`FLOAT` tokens; `PNumber` (`clausal/tools/prolog_ast.py`) gains an optional
  `text: str | None`.
- **Currency-aware construction entry point.** When the `n(Unit)` magnitude is a numeric
  literal, the sugar passes the lexeme text *unconditionally* alongside the parsed value
  (a hint, not a commitment). At runtime the construction helper dispatches on the unit:
  currency → `Decimal(text)`; non-currency → the parsed `float` (physics units keep float).

So `7.89(euro)` builds `Decimal("7.89")` straight from the lexeme; the number never becomes
a float. Non-literal magnitudes (a variable, an expression) carry no text and take the 1.3 path.

### 1.3 Runtime float fallback

When a currency `Quantity` is constructed from a value that is *already* a `float` at
runtime (e.g. a variable bound to a float), coercion is `Decimal(str(f))`.

- This is **exact for any value a human would have typed as a literal** — the IEEE-754
  round-trip guarantee means `str(float)` is the shortest decimal that round-trips, which
  reproduces the typed digits (verified: 10,000-literal sweep, zero value-mismatches).
- It is **best-effort, not exact, for a *computed* float** that already carried drift before
  reaching currency-land (`0.1 + 0.2` is `0.30000000000000004` as a double before coercion;
  `Decimal(str(...))` faithfully captures the drift — it cannot un-drift upstream loss).
- **Load-bearing rule:** coercion is `Decimal(str(f))`, **never** `Decimal(f)`. Direct
  `Decimal(0.2)` is the raw binary expansion `0.20000000000000001110…` and corrupts money.

Documented caveat: to compute money exactly, values must reach Decimal-land as literals,
ints, or via the string constructor `money("7.89", euro)` — before any float arithmetic.

### 1.4 Arithmetic value coercion

To keep money exact when it meets a plain rate (`price * 0.2` for tax) without hitting
Python's `Decimal + float → TypeError`, `Quantity` value arithmetic coerces the *other*
operand to `Decimal` whenever one side is `Decimal` (`int` exact, `float` via `str`). All
dimension checks are unchanged. `10.00(euro) / 3` retains full Decimal precision internally
(quantized only on display).

### 1.5 Currency dimension metadata

The unit-predicate object (`_UnitsPredicate` in `clausal/modules/units.py`) is extended
(or subclassed as `Currency`) to carry:

- `is_currency: bool`
- `scale: int` — minor-unit digits (euro 2, yen 0, bahraini_dinar 3)
- `iso_code: str` — ISO-4217 alpha-3, e.g. `"EUR"` (a **string**, for display/interchange)
- `symbol: str` — display symbol, e.g. `"€"`, `"$"`, `"£"`, `"¥"` (a **string**)

A currency is a **base** dimension (self-keyed, non-convertible), exactly like `Metre`.

### 1.5.1 Construction is lossless — no auto-quantize

Tagging a number as a currency does **not** round it to the currency's `scale`.
Construction preserves the full value; `scale` is consumed only by display/quantization
(1.6). Rationale: auto-quantizing on construction would (a) contradict the chosen
"full precision in arithmetic, quantize only for display" model, (b) silently corrupt
legitimately higher-precision values (a per-litre price, an interest rate), and (c) mask
float drift rather than prevent it. Note the two forms:

```
0.1(euro) + 0.2(euro)   % each literal captured exactly as Decimal → added in Decimal → 0.30 exactly
(0.1 + 0.2)(euro)       % 0.1 + 0.2 computes in float FIRST (0.30000000000000004), THEN tagged
```

Both parse (the `n(Unit)` sugar fires for any non-Name/non-Attribute callee, so a
parenthesized expression qualifies), but only the first is exact. The compound form has no
single lexeme, so it takes the 1.3 runtime-float fallback and inherits any prior drift.
Auto-quantize would hide this; instead we keep construction lossless and **actively reject
over-precise construction** (1.5.2).

### 1.5.2 Construction-time precision check

Rather than silently rounding, currency **construction** rejects a value that carries
significant digits below the currency's `scale` — this catches float drift and typos at the
point they enter the money domain. The check is trailing-zero-safe: raise **iff**
`value != value.quantize(Decimal(10) ** -scale)` (i.e. quantizing to `scale` would lose
information). Examples (euro, scale 2):

```
7.89(euro)          ok           7.890(euro)   ok (== 7.89)
7.891(euro)         RAISE        (0.1 + 0.2)(euro)  RAISE (0.30000000000000004)
7(yen)   ok   7.0(yen) ok   7.5(yen)  RAISE (scale 0)   1.234(bahraini_dinar) ok
```

**Scope: construction only, never arithmetic results.** Tagging a raw number (`n(Unit)`
sugar, the runtime-float path 1.3, the `money(...)` string constructor) is checked. A
*computed* currency `Quantity` (a division/multiplication result) is **not** — full precision
is preserved for intermediates and quantized only at display. So `10.00(euro) / 3` yields
`3.333…(euro)` and is allowed; writing `3.333(euro)` directly raises.

**Escape for deliberate sub-scale amounts.** Unit prices / tariffs are legitimately written
below display scale (`0.0034(euro)` per kWh). `money_precise(Text, Currency, Out)` constructs
from an exact string **without** the precision check — a distinct, greppable "I mean it" path.

**Exception:** a new `CurrencyPrecisionError` (catchable via `catch/3`, like `UnitsMismatch`).
Message names the value, the currency and its `scale`, and advises the three fixes:
(a) combine per-currency literals — `0.1(euro) + 0.2(euro)`; (b) round explicitly with
`money_round(V, Mode, Out)` after choosing the rounding; (c) if sub-scale precision is
intended, use `money_precise`.

### 1.6 Rounding & display predicates (explicit mode required)

**Naming convention.** `currency_*` predicates take a *denomination* (the dimension, e.g.
`euro`) and report its metadata; `money_*` predicates (and `money`) take or produce an
*amount* (value + currency, e.g. `7.89(euro)`). Future predicates follow this split.

Arithmetic never auto-rounds; quantization is an explicit operation with a **required**
rounding-mode argument (no hidden global default):

- `money_round(Amount, Mode, Out)` — `Out` is `Amount` quantized to its currency's `scale`,
  still a currency `Quantity`.
- `money_str(Amount, Mode, Str)` — formatted display string, quantized to `scale`; default
  form `"3.33 EUR"` (value + ISO code).
- `money_format(Amount, Style, Mode, Str)` — display with an explicit style controlling
  which label and where: `Style` ∈ `symbol` (`"€3.33"`), `code` (`"3.33 EUR"`),
  `name` (`"3.33 euro"`), `plain` (`"3.33"`). Symbol placement (prefix/suffix) comes from
  the currency's metadata default; grouping/locale niceties are a future extension.
- `money(Text, Currency, Out)` — exact constructor from a decimal **string** (or integer),
  bypassing float entirely; for the legally-critical path. Subject to the 1.5.2 precision
  check. Also usable in expression position as `money("7.89", euro)` (2-arg).
- `money_precise(Text, Currency, Out)` — exact string constructor that **skips** the 1.5.2
  precision check, for deliberate sub-scale amounts (unit prices, tariffs).

**Python / f-string surface.** Currency `Quantity` implements `__format__`, so amounts format
inside f-strings and the `++()` Python escape via a small spec mini-language mirroring the
predicate styles: `f"{amt}"` → `"3.33 EUR"` (default), `f"{amt:symbol}"` → `"€3.33"`,
`f"{amt:code}"` → `"3.33 EUR"`, `f"{amt:name}"` → `"3.33 euro"`, `f"{amt:plain}"` → `"3.33"`.
Formatting quantizes to `scale`; an explicit rounding mode may be appended in the spec
(e.g. `f"{amt:symbol,half_even}"`), defaulting to `half_even` **only** on the Python
formatting surface (the Clausal predicates always require an explicit `Mode`).

**Accessors:** `currency_scale(Currency, N)`, `currency_code(Currency, Code)` (Code a string),
`currency_symbol(Currency, Sym)` (Sym a string).

Rounding-mode atoms → `decimal` constants:

| atom | `decimal` mode |
|---|---|
| `half_up` | `ROUND_HALF_UP` |
| `half_even` | `ROUND_HALF_EVEN` |
| `half_down` | `ROUND_HALF_DOWN` |
| `up` | `ROUND_UP` |
| `down` | `ROUND_DOWN` |
| `ceiling` | `ROUND_CEILING` |
| `floor` | `ROUND_FLOOR` |

An unknown mode atom raises. Existing `strip_units(7.89(euro), V)` yields `V = Decimal("7.89")`;
existing `has_units(X, euro)` checks the currency dimension — both work unchanged.

### 1.7 Decimal rendering fix

`term_str` (`clausal/terms.py`) currently renders `(int, float, complex)` via `repr`;
`Decimal` falls through. Add `Decimal` to the numeric branch so embedded decimals render
correctly. Narrow scope — no unification/identity changes (A01-D001 / A02-D002 stay parked).

## Layer 2 — currency vocabulary (built-in)

Currencies are **built-in**, alongside units — they are everyday reasoning objects like
dates, change rarely, and are small. Because currencies attach to jurisdictions, this
introduces a lightweight built-in **countries/jurisdictions** layer (country + currency
associations, plus ISO-code string metadata). Language *codes* may be added to the same
layer later; translation machinery is out of scope.

### 2.1 Naming — spelled-out, jurisdiction-qualified

- **Canonical spelled-out currency names**, one per currency, no aliases: `euro`,
  `sterling`, `yen`, `baht`, `dollar`, `krona`.
- **Jurisdiction modules are spelled-out atoms**: `european_union`, `united_states`,
  `united_kingdom`, `japan`, `thailand`, `iceland`. **Not** ISO alpha-2 codes — those
  reintroduce the exact keyword-collision class we are eliminating (`is` = Iceland,
  `in` = India, `as` = American Samoa, `do` = Dominican Republic, `no` = Norway), the same
  problem as today's `try_`/`all` atom codes.
- ISO codes (alpha-2 country, alpha-3 currency) exist **only as string metadata**, never as
  atoms or module names.

Usage: a single-currency rulebase imports the bare name and the prefix never appears —
`import_from(japan, [yen])` then write `yen`; because a Japanese statute means Japanese yen.
The prefix surfaces only when several currencies are in play: `united_states.dollar`,
`european_union.euro`.

### 2.2 One canonical home per currency, no re-exports

Atom identity in Clausal is **module-scoped and import-driven** (Python-like, not a single
Prolog registry). A currency is **defined exactly once**, in its home jurisdiction module,
and referenced there by everyone:

- The **euro** lives in `european_union` (`european_union.euro`). `france`/`germany` do
  **not** define or re-export it; eurozone rulebases import `euro` from `european_union`.
  This makes every euro reference the **same** dimension object, so amounts add.
- Ecuador has **no** dollar of its own; an Ecuadorian rulebase uses `united_states.dollar`.
- `united_states.dollar` and `australia.dollar` are **separately defined** → **distinct**
  dimensions → `united_states.dollar + australia.dollar` raises `UnitsMismatch`. The whole
  point is that different currencies never silently add.
- Regional/shared currencies (euro, CFA franc, East Caribbean dollar) get a **regional
  jurisdiction module**, same pattern as the euro.

## Components to build (in `clausal`)

1. `Quantity` Decimal support + arithmetic value coercion — `clausal/terms.py`.
2. Numeric-literal source-lexeme preservation — tokenizer, `PNumber` AST, `n(Unit)` sugar
   in `clausal/templating/term_rewriting.py`; currency-aware construction entry point.
3. Currency dimension metadata (`is_currency`, `scale`, `iso_code`, `symbol`) plus
   `Quantity.__format__` for currency — `clausal/modules/units.py`, `clausal/terms.py`.
4. Currency/jurisdiction vocabulary modules (built-in) — new module(s) near units.
5. Rounding/display/constructor builtins: `money_round/3`, `money_str/3`, `money_format/4`,
   `money/3`, `money_precise/3`, mode-atom → `decimal` mapping, the 1.5.2 precision check +
   `CurrencyPrecisionError`, and accessors (`currency_scale`, `currency_code`, `currency_symbol`).
6. Decimal rendering in `term_str` — `clausal/terms.py`.
7. Docs (`docs/units.md` currency section or a new `docs/currency.md`) + tests.

Extend the unit-expression grammar (`_is_unit_expr`, `clausal/templating/term_rewriting.py`)
to accept module-qualified currency references (`european_union.euro`, an `Attribute` node)
as well as bare names — **confirmed required**: the current `_is_unit_expr` has no `Attribute`
case, so `european_union.euro` in unit position does not parse today.

## Data flow

```
author writes  7.89(euro)
  → n(Unit) sugar preserves lexeme "7.89" + passes euro
  → currency-aware construction: euro.is_currency → Quantity(Decimal("7.89"), {euro:1})
arithmetic  7.89(euro) + 1.23(euro)
  → same dims → Quantity(Decimal("9.12"), {euro:1})       (exact, full precision)
  10.00(euro) / 3
  → scalar 3 coerced to Decimal → Quantity(Decimal("3.333…"), {euro:1})
display  money_str(Total, half_up, S)
  → quantize to scale(euro)=2, HALF_UP → "9.12 EUR"
error  7.89(euro) + 5(united_states.dollar)  → UnitsMismatch
       7.89(euro) + 5                        → UnitsMismatch
```

## Error handling

- Cross-currency `+`/`-`, and currency `+` plain number → `UnitsMismatch` (existing behavior).
- Over-precise currency **construction** → `CurrencyPrecisionError` (1.5.2); computed
  intermediates are exempt; `money_precise` opts out.
- Unknown rounding-mode atom → raise.
- `money("bad", euro)` malformed string → raise.
- Currency `Quantity` from a runtime `float` → coerced via `Decimal(str(f))` then precision-
  checked; documented as best-effort. `money(...)` / literals / ints are the exact paths.

## Testing

- **Exactness:** `0.1(euro) + 0.2(euro) == 0.3(euro)`; `7.89(euro) + 1.23(euro) == 9.12(euro)`.
- **Literal capture:** lexeme path exact including tricky literals; `money("7.89", euro)` exact.
- **Dimension safety:** euro+dollar raises; euro+5 raises; euro*2 ok; euro/euro dimensionless;
  `united_states.dollar` vs `australia.dollar` distinct (add raises); `european_union.euro`
  shared identity across imports (add succeeds).
- **Rounding:** `Decimal("2.675")` quantized half_up → 2.68 (the classic trap); `10.00/3`
  full precision then round; per-currency scale (yen 0, bahraini_dinar 3).
- **Precision check (1.5.2):** `7.891(euro)`, `(0.1+0.2)(euro)`, `7.5(yen)` raise
  `CurrencyPrecisionError`; `7.890(euro)`, `7.0(yen)`, `1.234(bahraini_dinar)` pass;
  computed intermediates (`10.00(euro)/3`) exempt; `money_precise("0.0034", euro)` passes.
- **Rendering & formatting:** embedded `Decimal` renders; `money_str` default `"3.33 EUR"`;
  `money_format` styles (`symbol`→`"€3.33"`, `name`→`"3.33 euro"`, `plain`→`"3.33"`);
  `Quantity.__format__` in an f-string produces the same styles; accessors return the
  scale/code/symbol metadata.
- **Modes:** each mode atom maps to the right `decimal` constant; unknown atom raises.

## Migration (separate, out of scope here)

Clausify's `kit/currency.clausal` (flat lowercase alpha-3 atoms, with the `all`/`try_`
collisions) will be migrated to this vocabulary once this feature lands. Todo filed at
`/workspace/clausify/todo/migrate-currency-to-decimal-vocabulary.md`.
