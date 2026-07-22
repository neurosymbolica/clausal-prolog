# Decimal Currency — Plan 2: Currency vocabulary, metadata & qualified naming

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce currencies as Decimal-backed, dimension-safe **units** — a starter set of spelled-out, jurisdiction-qualified currency predicates (`european_union.euro`, `united_states.dollar`, `united_kingdom.sterling`, `japan.yen`, `bahrain.dinar`) that carry per-currency scale/ISO-code/symbol metadata and can be written inline as `7.89(euro)`.

**Architecture:** A currency is a units **base dimension** (self-keyed, non-convertible) — so the existing `Quantity` dimension enforcement gives `euro + dollar → UnitsMismatch`, no coercion, and scale-by-dimensionless-only, for free. A `_CurrencyPredicate` subclass of the existing `_UnitsPredicate` adds `is_currency`/`scale`/`iso_code`/`symbol`. `Quantity` construction detects a currency dimension and coerces the magnitude to `Decimal` (establishing the "currency value is always Decimal" invariant). Each currency is defined exactly once in its jurisdiction module; jurisdiction modules are registered as importable built-ins. The `n(Unit)` sugar is extended to accept module-qualified unit names (`european_union.euro`).

**Tech Stack:** Python 3.13, `decimal.Decimal`, the existing units/`Quantity` machinery, the module import/alias system, pytest.

## Global Constraints

- A currency is a **base dimension**: its `_dims` is `{self: 1}` (self-keyed), exactly like `Metre`. Currencies are **never** convertible and carry no scale factor between each other.
- Currency magnitudes are always `Decimal`. Coercion of a `float` MUST use `Decimal(str(f))`, never `Decimal(f)`. `bool` MUST be rejected (it is an `int` subclass).
- **One canonical home per currency, no re-exports.** `euro` is defined only in `european_union`; `dollar` only in `united_states`; etc. Two references to the same currency (bare-imported or module-qualified) MUST be the SAME object (module-scoped atom identity). Different currencies (`united_states.dollar` vs a hypothetical `australia.dollar`) are distinct dimensions and MUST NOT add.
- Jurisdiction module names are **spelled-out atoms** (`european_union`, `united_states`, `united_kingdom`, `japan`, `bahrain`) — never ISO alpha-2/alpha-3 codes (those collide with reserved words: `is`/`in`/`as`/`do`/`no`). ISO codes live only as **string** metadata (`iso_code`).
- Starter-set scales (ISO 4217 minor units), verbatim: `euro` = 2 (`"EUR"`, `"€"`), `dollar` = 2 (`"USD"`, `"$"`), `sterling` = 2 (`"GBP"`, `"£"`), `yen` = 0 (`"JPY"`, `"¥"`), `dinar` = 3 (`"BHD"`, `"BD"`).
- Preserve all existing units/`Quantity`/renderer behavior. Additive changes only; no unrelated refactoring.
- Spec: `docs/superpowers/specs/2026-07-22-decimal-currency-design.md` (§1.5, Layer 2). Plan 1 (Decimal `Quantity` core) is already merged; `Decimal` is imported in `clausal/terms.py` and `Quantity._num_pair` exists.
- **Deferred to Plan 3** (do NOT build here): exact source-lexeme literal capture, the construction-time precision check + `CurrencyPrecisionError`, and the money builtins (`money`/`money_precise`/`money_round`/`money_str`/`money_format`/`currency_*`/`__format__`). In Plan 2, `7.89(euro)` becomes `Decimal("7.89")` via the runtime `Decimal(str(f))` coercion path — exact for literals; Plan 3 upgrades it to structural exactness + precision enforcement.

---

## File Structure

- Create: `clausal/modules/countries/__init__.py` — empty package marker.
- Create: `clausal/modules/countries/_currency.py` — `_CurrencyPredicate` class + `_make_currency(...)` factory (imports `_UnitsPredicate` from units).
- Create: `clausal/modules/countries/european_union.py` — defines `euro`.
- Create: `clausal/modules/countries/united_states.py` — defines `dollar`.
- Create: `clausal/modules/countries/united_kingdom.py` — defines `sterling`.
- Create: `clausal/modules/countries/japan.py` — defines `yen`.
- Create: `clausal/modules/countries/bahrain.py` — defines `dinar`.
- Modify: `clausal/templating/term_rewriting.py`
  - `_IMPORT_ALIASES` dict (~1392–1460): add the 5 jurisdiction aliases.
  - `_is_unit_expr` (~345): accept `Attribute` nodes; ensure `Attribute` is imported.
- Modify: `clausal/terms.py` — add `_to_decimal(x)` helper; in `Quantity.__init__`, coerce the magnitude to `Decimal` when a dim key is a currency.
- Create: `tests/test_currency.py` — Python-level unit tests + `.clausal`-source integration tests.

**Running tests:** from `/workspace/clausal-bug-fix`, `python -m pytest tests/test_currency.py -v` (fallback: `PYTHONPATH=. ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_currency.py -v`).

---

### Task 1: Currency predicate type, factory, starter vocabulary & registration

**Files:**
- Create: `clausal/modules/countries/__init__.py`, `clausal/modules/countries/_currency.py`, and the 5 jurisdiction modules listed above.
- Modify: `clausal/templating/term_rewriting.py` (`_IMPORT_ALIASES`).
- Test: `tests/test_currency.py`

**Interfaces:**
- Consumes: `clausal.modules.units._UnitsPredicate` (base class, `__slots__ = ("_dims",)`, `__call__(value)` returns `Quantity(value, self._dims)`).
- Produces:
  - `clausal.modules.countries._currency._CurrencyPredicate(_UnitsPredicate)` with extra slots `is_currency, iso_code, scale, symbol`.
  - `clausal.modules.countries._currency._make_currency(name, iso_code, scale, symbol) -> _CurrencyPredicate` — a self-keyed base dimension (`pred._dims = {pred: 1}`) with `is_currency=True` and the given metadata.
  - Module-level currency objects: `european_union.euro`, `united_states.dollar`, `united_kingdom.sterling`, `japan.yen`, `bahrain.dinar`.
  - `_IMPORT_ALIASES` entries mapping each jurisdiction name to `countries.<name>`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_currency.py`:

```python
from decimal import Decimal

import pytest


class TestCurrencyVocabulary:
    def test_euro_metadata(self):
        from clausal.modules.countries.european_union import euro
        assert euro.is_currency is True
        assert euro.iso_code == "EUR"
        assert euro.scale == 2
        assert euro.symbol == "€"

    def test_currency_is_self_keyed_base_dimension(self):
        from clausal.modules.countries.european_union import euro
        assert euro._dims == {euro: 1}

    def test_scale_variety(self):
        from clausal.modules.countries.japan import yen
        from clausal.modules.countries.bahrain import dinar
        assert yen.scale == 0
        assert dinar.scale == 3

    def test_all_starter_currencies_defined(self):
        from clausal.modules.countries.european_union import euro
        from clausal.modules.countries.united_states import dollar
        from clausal.modules.countries.united_kingdom import sterling
        from clausal.modules.countries.japan import yen
        from clausal.modules.countries.bahrain import dinar
        seen = {c.iso_code for c in (euro, dollar, sterling, yen, dinar)}
        assert seen == {"EUR", "USD", "GBP", "JPY", "BHD"}

    def test_distinct_currencies_are_distinct_dimensions(self):
        from clausal.modules.countries.european_union import euro
        from clausal.modules.countries.united_states import dollar
        assert euro is not dollar
        assert euro._dims != dollar._dims
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_currency.py::TestCurrencyVocabulary -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'clausal.modules.countries'`.

- [ ] **Step 3: Create the package marker and currency machinery**

Create `clausal/modules/countries/__init__.py`:

```python
"""Built-in jurisdiction modules exposing currency vocabulary.

Each currency is defined exactly once, in its home jurisdiction module, and
referenced there (bare-imported within a single-currency rulebase, or module-
qualified when several currencies are in play). Currencies are Decimal-backed
units base dimensions — see clausal.modules.countries._currency.
"""
```

Create `clausal/modules/countries/_currency.py`:

```python
"""Currency predicate type and factory.

A currency is a units *base dimension* (self-keyed, like Metre) carrying
per-currency display metadata: minor-unit scale, ISO-4217 code, and symbol.
Dimension safety (no cross-currency addition, no coercion, scale-by-
dimensionless-only) is inherited unchanged from Quantity/units.
"""
from __future__ import annotations

from clausal.modules.units import _UnitsPredicate


class _CurrencyPredicate(_UnitsPredicate):
    """A units base-dimension predicate that denotes a currency."""

    __slots__ = ("is_currency", "iso_code", "scale", "symbol")

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.is_currency = True
        self.iso_code = None
        self.scale = None
        self.symbol = None


def _make_currency(name: str, iso_code: str, scale: int, symbol: str) -> _CurrencyPredicate:
    """Create a self-keyed currency base dimension with display metadata."""
    pred = _CurrencyPredicate(name)
    pred._dims = {pred: 1}          # self-referential key — a base dimension
    pred.iso_code = iso_code
    pred.scale = scale
    pred.symbol = symbol
    return pred
```

- [ ] **Step 4: Create the five jurisdiction modules**

Create `clausal/modules/countries/european_union.py`:

```python
"""European Union — euro."""
from clausal.modules.countries._currency import _make_currency

euro = _make_currency("euro", iso_code="EUR", scale=2, symbol="€")
```

Create `clausal/modules/countries/united_states.py`:

```python
"""United States — dollar."""
from clausal.modules.countries._currency import _make_currency

dollar = _make_currency("dollar", iso_code="USD", scale=2, symbol="$")
```

Create `clausal/modules/countries/united_kingdom.py`:

```python
"""United Kingdom — sterling."""
from clausal.modules.countries._currency import _make_currency

sterling = _make_currency("sterling", iso_code="GBP", scale=2, symbol="£")
```

Create `clausal/modules/countries/japan.py`:

```python
"""Japan — yen (a zero-minor-unit currency)."""
from clausal.modules.countries._currency import _make_currency

yen = _make_currency("yen", iso_code="JPY", scale=0, symbol="¥")
```

Create `clausal/modules/countries/bahrain.py`:

```python
"""Bahrain — dinar (a three-minor-unit currency)."""
from clausal.modules.countries._currency import _make_currency

dinar = _make_currency("dinar", iso_code="BHD", scale=3, symbol="BD")
```

- [ ] **Step 5: Register the jurisdictions as importable built-ins**

In `clausal/templating/term_rewriting.py`, find the `_IMPORT_ALIASES` dict (~line 1392–1460) and add these five entries (place them with the other non-`py.` module aliases such as `"units": "units"`):

```python
    "european_union": "countries.european_union",
    "united_states": "countries.united_states",
    "united_kingdom": "countries.united_kingdom",
    "japan": "countries.japan",
    "bahrain": "countries.bahrain",
```

(The resolver prepends `clausal.modules.`, so `european_union` → `clausal.modules.countries.european_union`.)

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_currency.py::TestCurrencyVocabulary -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add clausal/modules/countries clausal/templating/term_rewriting.py tests/test_currency.py
git commit -m "feat(currency): starter currency vocabulary as units base dimensions"
```

---

### Task 2: Decimal-coerce currency magnitudes at Quantity construction

**Files:**
- Modify: `clausal/terms.py` (`Quantity.__init__` ~1814; add module-level `_to_decimal`)
- Test: `tests/test_currency.py`

**Interfaces:**
- Consumes: `Quantity(value, dims)`; the currency predicates from Task 1 (duck-typed via `getattr(k, "is_currency", False)` — `terms.py` does NOT import the currency class).
- Produces: any `Quantity` whose dimension includes a currency key has a `Decimal` `_value`. `_to_decimal(x)` module helper: `Decimal`→as-is, `int`→`Decimal(x)`, `float`→`Decimal(str(x))`, `str`→`Decimal(x)`, `bool`→`TypeError`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_currency.py`:

```python
class TestCurrencyDecimalConstruction:
    def _euro(self, v):
        from clausal.terms import Quantity
        from clausal.modules.countries.european_union import euro
        return Quantity(v, euro)

    def test_float_magnitude_becomes_decimal(self):
        q = self._euro(7.89)
        assert isinstance(q.value, Decimal)
        assert q.value == Decimal("7.89")

    def test_int_magnitude_becomes_decimal(self):
        from clausal.terms import Quantity
        from clausal.modules.countries.japan import yen
        q = Quantity(5, yen)
        assert isinstance(q.value, Decimal)
        assert q.value == Decimal("5")

    def test_same_currency_addition_is_exact(self):
        # The whole point: 0.1 + 0.2 == 0.3 exactly, not 0.30000000000000004.
        r = self._euro(0.1) + self._euro(0.2)
        assert r.value == Decimal("0.3")

    def test_cross_currency_addition_raises(self):
        from clausal.terms import Quantity, UnitsMismatch
        from clausal.modules.countries.united_states import dollar
        with pytest.raises(UnitsMismatch):
            _ = self._euro(1.00) + Quantity(1.00, dollar)

    def test_currency_plus_plain_number_raises(self):
        from clausal.terms import UnitsMismatch
        with pytest.raises(UnitsMismatch):
            _ = self._euro(1.00) + 5

    def test_scale_by_dimensionless_keeps_decimal_and_dims(self):
        r = self._euro(10.00) * 3
        assert isinstance(r.value, Decimal)
        assert r.value == Decimal("30.00")
        from clausal.modules.countries.european_union import euro
        assert r.dims == {euro: 1}

    def test_ratio_of_same_currency_is_dimensionless(self):
        r = self._euro(10.00) / self._euro(4.00)
        assert r.dims == {}
        assert r.value == Decimal("2.5")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency.py::TestCurrencyDecimalConstruction -v`
Expected: FAIL — `test_float_magnitude_becomes_decimal` gets a `float` value (not `Decimal`); some arithmetic assertions differ.

- [ ] **Step 3: Add the `_to_decimal` helper**

In `clausal/terms.py`, near the top-level helpers just above `class Quantity` (after `_dims_str`, ~line 1785), add:

```python
def _to_decimal(x):
    """Coerce a numeric magnitude to Decimal for a currency amount.

    Uses Decimal(str(f)) for floats — never Decimal(f), which would expose the
    binary expansion. Rejects bool (an int subclass) rather than treating it as
    a number.
    """
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        raise TypeError(f"cannot use {x!r} as a currency amount")
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(str(x))
    if isinstance(x, str):
        return Decimal(x)
    raise TypeError(f"cannot coerce {x!r} to a Decimal currency amount")
```

- [ ] **Step 4: Coerce in `Quantity.__init__`**

In `clausal/terms.py`, at the END of `Quantity.__init__` (the normal path, right after `self._dims = MappingProxyType({k: v for k, v in actual_dims.items() if v != 0})` ~line 1835), add:

```python
        if not isinstance(self._value, Decimal):
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
                    self._value = _to_decimal(self._value)
                    break
```

(This runs only when the value isn't already a `Decimal`, so arithmetic intermediates — already `Decimal` — pay nothing. The `isinstance(dims, Quantity)` early-return branch is not a currency path and is left unchanged; currencies are always passed as the `_CurrencyPredicate` itself.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency.py::TestCurrencyDecimalConstruction -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the broader suite for no regressions**

Run: `python -m pytest tests/test_currency.py tests/test_quantity_decimal.py tests/test_units.py -q`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add clausal/terms.py tests/test_currency.py
git commit -m "feat(currency): coerce currency magnitudes to Decimal at construction"
```

---

### Task 3: Accept module-qualified units in `n(Unit)` sugar + end-to-end `.clausal` tests

**Files:**
- Modify: `clausal/templating/term_rewriting.py` (`_is_unit_expr` ~345; ensure `Attribute` imported)
- Test: `tests/test_currency.py`

**Interfaces:**
- Consumes: the currency vocabulary (Task 1) and Decimal construction (Task 2); the `.clausal` module loader `clausal.import_hook._load_module` and `clausal.logic.solve.call`.
- Produces: `_is_unit_expr` returns `True` for an `Attribute` whose base is a valid unit expression, so `7.89(european_union.euro)` parses; `.clausal` currency literals work end-to-end (bare-imported and module-qualified).

- [ ] **Step 1: Write the failing integration tests**

Append to `tests/test_currency.py`:

```python
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load(name, src):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.clausal")
    with open(p, "w") as f:
        f.write(src)
    return _load_module(name, p).__dict__["$module"]


def _succeeds(mod, pred="Test"):
    return any(True for _ in call(pred, module=mod))


class TestCurrencyClausalIntegration:
    def test_bare_imported_currency_literal_is_exact(self):
        # 0.1(euro) + 0.2(euro) == 0.3(euro): passes ONLY with exact Decimal math.
        mod = _load("cur_bare",
            "-import_from(european_union, [euro])\n"
            "Test <- (eval_(0.1(euro), A), eval_(0.2(euro), B), "
            "eval_(A + B, C), eval_(0.3(euro), D), C == D)\n")
        assert _succeeds(mod)

    def test_module_qualified_currency_literal(self):
        # european_union.euro must parse in n(Unit) position (the _is_unit_expr fix).
        mod = _load("cur_qual",
            "-import_module(european_union)\n"
            "Test <- (eval_(7.89(european_union.euro), A), "
            "eval_(1.23(european_union.euro), B), eval_(A + B, C), "
            "eval_(9.12(european_union.euro), D), C == D)\n")
        assert _succeeds(mod)

    def test_cross_currency_addition_fails_in_clausal(self):
        # euro + dollar must NOT succeed (dimension safety end-to-end).
        mod = _load("cur_mismatch",
            "-import_from(european_union, [euro])\n"
            "-import_from(united_states, [dollar])\n"
            "Test <- (eval_(1.00(euro), A), eval_(1.00(dollar), B), eval_(A + B, C))\n")
        assert not _succeeds(mod)

    def test_has_units_with_qualified_currency(self):
        mod = _load("cur_has_units",
            "-import_from(py.units, [has_units])\n"
            "-import_from(european_union, [euro])\n"
            "-import_module(european_union)\n"
            "Test <- (eval_(7.89(euro), A), has_units(A, european_union.euro))\n")
        assert _succeeds(mod)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency.py::TestCurrencyClausalIntegration -v`
Expected: `test_bare_imported_currency_literal_is_exact` and `test_cross_currency_addition_fails_in_clausal` may already pass, but `test_module_qualified_currency_literal` and `test_has_units_with_qualified_currency` FAIL — `european_union.euro` in unit position doesn't parse (the `n(Unit)` sugar's `_is_unit_expr` rejects `Attribute`, so the eval fails and `Test` has no solution).

- [ ] **Step 3: Extend `_is_unit_expr` to accept `Attribute`**

In `clausal/templating/term_rewriting.py`, first ensure `Attribute` is importable in this module. Check the AST import at the top of the file; if `Attribute` is not already imported alongside `Name`, `BinOp`, `Constant`, etc., add it to that import.

Then in `_is_unit_expr` (~line 345), add an `Attribute` clause (a module-qualified name like `european_union.euro` is `Attribute(value=Name("european_union"), attr="euro")`):

```python
    if isinstance(node, Attribute):
        return _is_unit_expr(node.value)
```

Place it among the other `isinstance` checks (e.g. right after the `Name` check). This makes `european_union.euro` a valid unit expression; the qualified name lowers to the currency object exactly as it does in ordinary term position (verified by spike).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency.py::TestCurrencyClausalIntegration -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full currency + adjacent suites**

Run: `python -m pytest tests/test_currency.py tests/test_quantity_decimal.py tests/test_units.py tests/test_module_imports.py -q`
Expected: PASS (all) — confirms no regression to units, the Decimal core, or the module-import/qualified-atom machinery.

- [ ] **Step 6: Commit**

```bash
git add clausal/templating/term_rewriting.py tests/test_currency.py
git commit -m "feat(currency): accept module-qualified units in n(Unit) sugar"
```

---

## Self-Review

**Spec coverage (Plan 2 = §1.5 metadata + Layer 2 vocabulary/naming, plus the §1.1 currency value invariant):**
- §1.5 `is_currency`/`scale`/`iso_code`/`symbol` metadata → Task 1. ✓
- §1.1 currency magnitudes coerced to `Decimal` at construction → Task 2. ✓
- Layer 2 spelled-out jurisdiction modules, one canonical home, no re-exports, ISO codes as strings → Task 1 (modules + registration), verified distinct/shared identity in Tasks 1 & 3. ✓
- Dimension safety (euro+dollar raises, currency+plain raises, scale-by-dimensionless) → inherited from units, asserted in Tasks 2 & 3. ✓
- `_is_unit_expr` `Attribute` support for `european_union.euro` (spec's "confirmed required") → Task 3. ✓
- Deferred to Plan 3 (correctly absent here): exact lexeme capture, precision check + `CurrencyPrecisionError`, money/currency builtins + `__format__`.

**Placeholder scan:** none — every step has concrete code, exact metadata values, and commands.

**Type consistency:** `_make_currency(name, iso_code, scale, symbol)` signature is used identically across all five jurisdiction modules and matches its definition in `_currency.py`. `_to_decimal` defined in Task 2 and used only there. Currency detection uses duck-typed `getattr(k, "is_currency", False)`, so `terms.py` needs no import of the currency class. `_dims = {pred: 1}` self-keying matches the existing `_make_unit_pred_base` pattern.

**Scope check:** Focused on vocabulary + metadata + the one parser fix. No money builtins or precision logic leak in.

---

## Roadmap — Plan 3 (written after Plan 2 lands)

Exact source-lexeme capture (`Token` raw text → `PNumber.text` → compiler lowering → `n(Unit)` sugar) so `7.89(euro)` builds `Decimal("7.89")` from text without a float ever existing; the construction-time precision check + `CurrencyPrecisionError` (§1.5.2), with `money_precise` as the escape; and the money builtins `money/3`, `money_round/3`, `money_str/3`, `money_format/4`, accessors `currency_scale`/`currency_code`/`currency_symbol`, and `Quantity.__format__` currency styles (§1.6). Also close the two Plan-1 deferred `Decimal×float` arithmetic gaps recorded in `.superpowers/sdd/deferred-decimal-gaps.md` (`__pow__`; the `__init__` scaled-unit branch is already handled by Plan 1's fast-follow — re-verify it stays clear for currencies).
