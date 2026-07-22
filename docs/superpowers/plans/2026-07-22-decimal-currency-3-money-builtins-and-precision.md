# Decimal Currency — Plan 3: money builtins & construction precision check

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give currency amounts their user-facing capability — explicit-mode rounding and display (`money_round`/`money_str`/`money_format`, plus f-string `__format__`), exact string constructors (`money`/`money_precise`), metadata accessors (`currency_scale`/`currency_code`/`currency_symbol`) — and a fail-loud construction-time precision check (`CurrencyPrecisionError`) that rejects amounts carrying digits below the currency's scale.

**Architecture:** Currency arithmetic keeps full Decimal precision; quantization is explicit at display. A construction-time check (in `Quantity.__init__`, gated to the *tagging* path only — never arithmetic intermediates) raises `CurrencyPrecisionError` when an amount has sub-scale digits. A new built-in Python module `clausal/modules/currency.py` provides the money predicates (modeled on the units utility-predicate pattern) and a string→`decimal.ROUND_*` mode map. `Quantity.__format__` gains currency-aware styles.

**Tech Stack:** Python 3.13, `decimal` (Decimal + ROUND_* + quantize), the units/`Quantity` machinery, the module alias system, pytest.

## Global Constraints

- **Precision check runs at *tagging* only, never on arithmetic results.** `7.891(euro)` and `money("7.891", euro)` raise; a computed `10.00(euro)/3` → `3.333…(euro)` does NOT (it's quantized only at display). The seam: `Quantity.__init__` receives a `_CurrencyPredicate` as `dims` when tagging, and a plain dims **dict** when arithmetic builds a result — check only the former.
- Trailing-zero-safe check: raise **iff** `value != value.quantize(Decimal(1).scaleb(-scale))`. So `7.890(euro)` (==7.89) passes; `7.891(euro)`, `(0.1+0.2)(euro)`, `7.5(yen)` (scale 0) raise.
- Rounding is **explicit**: every rounding/display predicate takes a required mode argument. Modes are **strings**: `"half_up" | "half_even" | "half_down" | "up" | "down" | "ceiling" | "floor"` → `decimal.ROUND_*`. Unknown mode → raise.
- Arithmetic never auto-rounds; construction never auto-rounds (Plan 2). Only the money display/round predicates quantize.
- `money`/the `n(Unit)` sugar build via the **checked** path; `money_precise` and all result-producing predicates build via the **unchecked** raw-dict path (`Quantity(value, dict(amount.dims))`).
- `CurrencyPrecisionError` is a plain `Exception` (catchable via `catch/3`, like `UnitsMismatch`), defined in `clausal/terms.py`.
- Register the new `currency` module in BOTH `_IMPORT_ALIASES` (`term_rewriting.py`) AND `_MODULE_ALIASES` (`compiler_v2.py`) — Plan 2 proved both are required.
- Spec: `docs/superpowers/specs/2026-07-22-decimal-currency-design.md` (§1.5.2, §1.6). Plans 1 & 2 merged: `Decimal` imported in `terms.py`; `Quantity._num_pair`, `_to_decimal`, and currency Decimal-coercion exist; currencies are `_CurrencyPredicate` with `is_currency`/`scale`/`iso_code`/`symbol` in `clausal/modules/countries/`.
- **Deferred to Plan 4** (do NOT build here): structural source-lexeme literal capture. In Plan 3, literal exactness still comes from Plan 2's `Decimal(str(f))` coercion.
- Additive only; preserve existing behavior. **Commit only the exact files named in each task** (do NOT `git add -A`/`git add .` — an unrelated untracked `implementation_plans/…` doc must stay untracked).

---

## File Structure

- Modify: `clausal/terms.py` — `CurrencyPrecisionError` class; `_check_currency_precision(value, currency)`; call it in `Quantity.__init__` on the tagging path; extend `Quantity.__format__` for currency styles (Task 4).
- Create: `clausal/modules/currency.py` — money predicates + mode map + helpers.
- Modify: `clausal/templating/term_rewriting.py` (`_IMPORT_ALIASES`) and `clausal/logic/compiler_v2.py` (`_MODULE_ALIASES`) — register `currency` → `currency`.
- Test: `tests/test_currency_money.py` — Python + `.clausal` integration tests.

**Running tests:** from `/workspace/clausal-bug-fix`, `python -m pytest tests/test_currency_money.py -v` (fallback: `PYTHONPATH=. ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_currency_money.py -v`).

---

### Task 1: `CurrencyPrecisionError` + construction-time precision check

**Files:**
- Modify: `clausal/terms.py` (`UnitsMismatch` neighborhood ~1766; `Quantity.__init__` ~1814)
- Test: `tests/test_currency_money.py`

**Interfaces:**
- Consumes: `Quantity`, the `_CurrencyPredicate` currency objects (`european_union.euro`, `japan.yen`, `bahrain.dinar`).
- Produces: `clausal.terms.CurrencyPrecisionError(Exception)`; `_check_currency_precision(value, currency)` raising it when `value != value.quantize(Decimal(1).scaleb(-currency.scale))`. The check fires in `Quantity.__init__` only when `dims` is a currency predicate (tagging), not when `dims` is a dict (arithmetic result).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_currency_money.py`:

```python
from decimal import Decimal

import pytest

from clausal.terms import Quantity, CurrencyPrecisionError
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.bahrain import dinar


class TestConstructionPrecisionCheck:
    def test_over_precise_euro_raises(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(7.891, euro)          # 3 dp for a 2-dp currency

    def test_exact_euro_ok(self):
        assert Quantity(7.89, euro).value == Decimal("7.89")

    def test_trailing_zero_ok(self):
        assert Quantity(Decimal("7.890"), euro).value == Decimal("7.890")  # == 7.89, allowed

    def test_drifted_float_expression_raises(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(0.1 + 0.2, euro)      # 0.30000000000000004

    def test_zero_scale_currency_rejects_fraction(self):
        with pytest.raises(CurrencyPrecisionError):
            Quantity(7.5, yen)             # yen scale 0
        assert Quantity(7, yen).value == Decimal("7")

    def test_three_scale_currency_ok(self):
        assert Quantity(Decimal("1.234"), dinar).value == Decimal("1.234")

    def test_arithmetic_intermediate_is_exempt(self):
        # A computed currency result (dims passed as a dict) must NOT be checked.
        r = Quantity(Decimal("10.00"), euro) / 3      # 3.333...(euro), built via dict dims
        assert r.value != r.value.quantize(Decimal("0.01"))   # has sub-scale digits
        assert r.dims == {euro: 1}                              # and did not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency_money.py::TestConstructionPrecisionCheck -v`
Expected: FAIL — `CurrencyPrecisionError` does not exist (ImportError), so collection fails.

- [ ] **Step 3: Add `CurrencyPrecisionError` and the check helper**

In `clausal/terms.py`, right after the `UnitsMismatch` class (~line 1766), add:

```python
class CurrencyPrecisionError(Exception):
    """Raised when a currency amount is constructed with more decimal places
    than the currency's scale allows (e.g. 7.891 for a 2-dp euro)."""


def _check_currency_precision(value, currency) -> None:
    """Raise CurrencyPrecisionError if `value` carries digits below `currency`'s
    scale. Trailing zeros are allowed (7.890 == 7.89). `value` is already Decimal."""
    scale = currency.scale
    if value != value.quantize(Decimal(1).scaleb(-scale)):
        raise CurrencyPrecisionError(
            f"{value} has more decimal places than {currency._name} supports "
            f"(scale {scale}). Combine per-currency literals "
            f"(e.g. 0.1(euro) + 0.2(euro)), round explicitly with "
            f"money_round(V, Mode, Out), or use money_precise for deliberate "
            f"sub-scale amounts."
        )
```

- [ ] **Step 4: Call the check on the tagging path in `Quantity.__init__`**

Plan 2 added a currency Decimal-coercion loop at the end of `Quantity.__init__`. Replace that trailing coercion block with one that ALSO runs the precision check when `dims` (the constructor argument) is itself a currency predicate. Find the current block (after `self._dims = MappingProxyType(...)`):

```python
        if not isinstance(self._value, Decimal):
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
                    self._value = _to_decimal(self._value)
                    break
```

and replace it with:

```python
        if not isinstance(self._value, Decimal):
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
                    self._value = _to_decimal(self._value)
                    break
        # Precision check only when TAGGING a raw number as a currency (dims is a
        # currency predicate). Arithmetic results pass a dims dict and are exempt.
        if getattr(dims, "is_currency", False):
            _check_currency_precision(self._value, dims)
```

(`dims` here is the original constructor argument: a `_CurrencyPredicate` for `Quantity(7.89, euro)` / the `n(Unit)` sugar, but a `dict`/`MappingProxyType` for arithmetic results — `getattr(dict, "is_currency", False)` is `False`, so intermediates are exempt.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency_money.py::TestConstructionPrecisionCheck -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the currency + adjacent suites for no regression**

Run: `python -m pytest tests/test_currency_money.py tests/test_currency.py tests/test_units.py tests/test_quantity_decimal.py -q`
Expected: PASS (all).

- [ ] **Step 7: Commit (named paths only)**

```bash
git add clausal/terms.py tests/test_currency_money.py
git commit -m "feat(currency): construction-time precision check (CurrencyPrecisionError)"
```

---

### Task 2: `currency` module — constructors & accessors

**Files:**
- Create: `clausal/modules/currency.py`
- Modify: `clausal/templating/term_rewriting.py` (`_IMPORT_ALIASES`), `clausal/logic/compiler_v2.py` (`_MODULE_ALIASES`)
- Test: `tests/test_currency_money.py`

**Interfaces:**
- Produces (all importable via `-import_from(currency, [...])`):
  - `money(Text, Currency, Out)` — `Out = Quantity(Decimal(Text), Currency)` via the CHECKED path.
  - `money_precise(Text, Currency, Out)` — same but UNCHECKED (`Quantity(Decimal(Text), dict(Currency._dims))`).
  - `currency_scale(Currency, N)`, `currency_code(Currency, Code)`, `currency_symbol(Currency, Sym)` — unify the metadata (Code/Sym are strings).
- Module-internal helpers reused in Task 3: `_currency_of(amount)` → the currency predicate of a currency `Quantity` (or `None`); the k-less trampoline wrapper.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_currency_money.py`:

```python
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var as LVar, deref
from clausal.logic.solve import _drive_trampoline


def _run(pred, *args):
    """Invoke a module predicate directly; return list of {var_name: value}."""
    trail = Trail()
    var_map = {}
    resolved = []
    for a in args:
        if isinstance(a, str) and a.isupper():
            var_map.setdefault(a, LVar())
            resolved.append(var_map[a])
        else:
            resolved.append(a)
    out = []
    for _ in _drive_trampoline(pred._get_dispatch(), trail, *resolved):
        out.append({k: deref(v) for k, v in var_map.items()})
    return out


def _load(name, src):
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.clausal")
    with open(p, "w") as f:
        f.write(src)
    return _load_module(name, p).__dict__["$module"]


def _succeeds(mod, pred="Test"):
    return any(True for _ in call(pred, module=mod))


class TestMoneyConstructorsAndAccessors:
    def test_money_from_string_is_exact(self):
        from clausal.modules.currency import money
        r = _run(money, "7.89", euro, "OUT")
        assert r[0]["OUT"] == Quantity(Decimal("7.89"), euro)

    def test_money_checks_precision(self):
        from clausal.modules.currency import money
        with pytest.raises(CurrencyPrecisionError):
            _run(money, "7.891", euro, "OUT")

    def test_money_precise_bypasses_check(self):
        from clausal.modules.currency import money_precise
        r = _run(money_precise, "0.0034", euro, "OUT")
        assert r[0]["OUT"].value == Decimal("0.0034")
        assert r[0]["OUT"].dims == {euro: 1}

    def test_accessors(self):
        from clausal.modules.currency import currency_scale, currency_code, currency_symbol
        assert _run(currency_scale, euro, "N")[0]["N"] == 2
        assert _run(currency_code, euro, "C")[0]["C"] == "EUR"
        assert _run(currency_symbol, euro, "S")[0]["S"] == "€"

    def test_money_end_to_end_clausal(self):
        mod = _load("money_ctor",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "Test <- (money(\"7.89\", euro, A), eval_(7.89(euro), B), A == B)\n")
        assert _succeeds(mod)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency_money.py::TestMoneyConstructorsAndAccessors -v`
Expected: FAIL — `No module named 'clausal.modules.currency'`.

- [ ] **Step 3: Create `clausal/modules/currency.py`**

```python
"""clausal.modules.currency — money constructors, rounding, display, accessors.

Currency amounts are Decimal-backed units base dimensions (see
clausal.modules.countries). This module adds the user-facing builtins:
exact constructors, explicit-mode rounding/formatting, and metadata accessors.
"""
from __future__ import annotations

from decimal import (
    Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
    ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR,
)
from typing import Callable

from clausal.terms import Quantity
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a k-less simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


_MODES = {
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "half_down": ROUND_HALF_DOWN,
    "up": ROUND_UP,
    "down": ROUND_DOWN,
    "ceiling": ROUND_CEILING,
    "floor": ROUND_FLOOR,
}


def _currency_of(amount):
    """Return the currency predicate of a currency Quantity, or None."""
    if not isinstance(amount, Quantity) or len(amount.dims) != 1:
        return None
    (key, exp), = amount.dims.items()
    if exp == 1 and getattr(key, "is_currency", False):
        return key
    return None


def _quantize(amount, currency, mode_str):
    """Return the amount's value quantized to the currency's scale using mode_str."""
    rounding = _MODES.get(mode_str)
    if rounding is None:
        raise ValueError(f"unknown rounding mode {mode_str!r}; expected one of "
                         f"{sorted(_MODES)}")
    return amount.value.quantize(Decimal(1).scaleb(-currency.scale), rounding=rounding)


# ── constructors ──────────────────────────────────────────────────────────────

def _money_impl(text, currency, out, trail):
    t, c = deref(text), deref(currency)
    if is_var(t) or is_var(c) or not getattr(c, "is_currency", False):
        return
    q = Quantity(Decimal(str(t)), c)                 # CHECKED path (precision check)
    if unify(deref(out), q, trail):
        yield None


def _money_precise_impl(text, currency, out, trail):
    t, c = deref(text), deref(currency)
    if is_var(t) or is_var(c) or not getattr(c, "is_currency", False):
        return
    q = Quantity(Decimal(str(t)), dict(c._dims))     # UNCHECKED path (raw dict dims)
    if unify(deref(out), q, trail):
        yield None


# ── accessors ─────────────────────────────────────────────────────────────────

def _accessor(attr):
    def impl(currency, out, trail):
        c = deref(currency)
        if not getattr(c, "is_currency", False):
            return
        if unify(deref(out), getattr(c, attr), trail):
            yield None
    return impl


money = ModulePredicate("money")
money._register(3, _simple_to_trampoline(_money_impl))

money_precise = ModulePredicate("money_precise")
money_precise._register(3, _simple_to_trampoline(_money_precise_impl))

currency_scale = ModulePredicate("currency_scale")
currency_scale._register(2, _simple_to_trampoline(_accessor("scale")))

currency_code = ModulePredicate("currency_code")
currency_code._register(2, _simple_to_trampoline(_accessor("iso_code")))

currency_symbol = ModulePredicate("currency_symbol")
currency_symbol._register(2, _simple_to_trampoline(_accessor("symbol")))
```

- [ ] **Step 4: Register the module in both alias registries**

In `clausal/templating/term_rewriting.py`, add to `_IMPORT_ALIASES` (with the other non-`py.` entries):

```python
    "currency": "currency",
```

In `clausal/logic/compiler_v2.py`, add the identical entry to `_MODULE_ALIASES`:

```python
    "currency": "currency",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency_money.py::TestMoneyConstructorsAndAccessors -v`
Expected: PASS (5 tests). (If a `_drive_trampoline` / `_run` wiring detail differs, model it on `tests/test_units.py`'s `run` helper — the dispatch/trampoline convention there is authoritative.)

- [ ] **Step 6: Commit (named paths only)**

```bash
git add clausal/modules/currency.py clausal/templating/term_rewriting.py clausal/logic/compiler_v2.py tests/test_currency_money.py
git commit -m "feat(currency): money/money_precise constructors and currency_* accessors"
```

---

### Task 3: rounding & display predicates

**Files:**
- Modify: `clausal/modules/currency.py`
- Test: `tests/test_currency_money.py`

**Interfaces:**
- Produces:
  - `money_round(Amount, Mode, Out)` — `Out` = `Amount` quantized to its currency's scale with `Mode`, still a currency `Quantity` (built via the UNCHECKED raw-dict path).
  - `money_str(Amount, Mode, Str)` — `"3.33 EUR"` (quantized value + ISO code).
  - `money_format(Amount, Style, Mode, Str)` — `Style` ∈ `"symbol"`→`"€3.33"`, `"code"`→`"3.33 EUR"`, `"name"`→`"3.33 euro"`, `"plain"`→`"3.33"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_currency_money.py`:

```python
class TestMoneyRoundingAndDisplay:
    def _euro(self, v):
        from clausal.modules.currency import money_precise
        return _run(money_precise, v, euro, "OUT")[0]["OUT"]

    def test_money_round_half_up_classic_trap(self):
        from clausal.modules.currency import money_round
        amt = self._euro("2.675")                    # exact Decimal, sub-scale
        out = _run(money_round, amt, "half_up", "OUT")[0]["OUT"]
        assert out.value == Decimal("2.68")          # not 2.67
        assert out.dims == {euro: 1}

    def test_money_round_half_even(self):
        from clausal.modules.currency import money_round
        amt = self._euro("2.665")
        out = _run(money_round, amt, "half_even", "OUT")[0]["OUT"]
        assert out.value == Decimal("2.66")

    def test_money_round_division_result(self):
        from clausal.modules.currency import money_round
        amt = Quantity(Decimal("10.00"), euro) / 3   # 3.333...
        out = _run(money_round, amt, "half_up", "OUT")[0]["OUT"]
        assert out.value == Decimal("3.33")

    def test_money_round_unknown_mode_raises(self):
        from clausal.modules.currency import money_round
        with pytest.raises(ValueError):
            _run(money_round, self._euro("1.00"), "sideways", "OUT")

    def test_money_str_default(self):
        from clausal.modules.currency import money_str
        s = _run(money_str, self._euro("3.335"), "half_up", "OUT")[0]["OUT"]
        assert s == "3.34 EUR"

    def test_money_format_styles(self):
        from clausal.modules.currency import money_format
        amt = self._euro("3.335")
        f = lambda style: _run(money_format, amt, style, "half_up", "OUT")[0]["OUT"]
        assert f("symbol") == "€3.34"
        assert f("code") == "3.34 EUR"
        assert f("name") == "3.34 euro"
        assert f("plain") == "3.34"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency_money.py::TestMoneyRoundingAndDisplay -v`
Expected: FAIL — `money_round`/`money_str`/`money_format` not importable.

- [ ] **Step 3: Add the rounding/display predicates**

Append to `clausal/modules/currency.py` (before the predicate-object registrations, or after — keep impls with their peers):

```python
def _money_round_impl(amount, mode, out, trail):
    a, m = deref(amount), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(m):
        return
    q = Quantity(_quantize(a, c, str(m)), dict(a.dims))   # UNCHECKED raw dict
    if unify(deref(out), q, trail):
        yield None


def _format_value(a, c, mode_str, style):
    v = _quantize(a, c, mode_str)
    if style == "symbol":
        return f"{c.symbol}{v}"
    if style == "code":
        return f"{v} {c.iso_code}"
    if style == "name":
        return f"{v} {c._name}"
    if style == "plain":
        return f"{v}"
    raise ValueError(f"unknown money style {style!r}; expected "
                     f"symbol/code/name/plain")


def _money_str_impl(amount, mode, out, trail):
    a, m = deref(amount), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(m):
        return
    if unify(deref(out), _format_value(a, c, str(m), "code"), trail):
        yield None


def _money_format_impl(amount, style, mode, out, trail):
    a, sty, m = deref(amount), deref(style), deref(mode)
    c = _currency_of(a)
    if c is None or is_var(sty) or is_var(m):
        return
    if unify(deref(out), _format_value(a, c, str(m), str(sty)), trail):
        yield None


money_round = ModulePredicate("money_round")
money_round._register(3, _simple_to_trampoline(_money_round_impl))

money_str = ModulePredicate("money_str")
money_str._register(3, _simple_to_trampoline(_money_str_impl))

money_format = ModulePredicate("money_format")
money_format._register(4, _simple_to_trampoline(_money_format_impl))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency_money.py::TestMoneyRoundingAndDisplay -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit (named paths only)**

```bash
git add clausal/modules/currency.py tests/test_currency_money.py
git commit -m "feat(currency): money_round/money_str/money_format explicit-mode display"
```

---

### Task 4: currency-aware `Quantity.__format__` (f-strings)

**Files:**
- Modify: `clausal/terms.py` (`Quantity.__format__` ~1999)
- Test: `tests/test_currency_money.py`

**Interfaces:**
- Produces: `format(currency_quantity, spec)` where `spec` is `""`/`"code"`/`"symbol"`/`"name"`/`"plain"`, optionally with `",<mode>"` appended (default mode `half_even`). Non-currency quantities keep the existing behavior.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_currency_money.py`:

```python
class TestCurrencyFormat:
    def _euro(self, v):
        from clausal.modules.currency import money_precise
        return _run(money_precise, v, euro, "OUT")[0]["OUT"]

    def test_default_spec_is_code(self):
        assert f"{self._euro('3.33')}" == "3.33 EUR"

    def test_symbol_spec(self):
        assert format(self._euro("3.33"), "symbol") == "€3.33"

    def test_name_and_plain(self):
        assert format(self._euro("3.33"), "name") == "3.33 euro"
        assert format(self._euro("3.33"), "plain") == "3.33"

    def test_spec_with_mode_quantizes(self):
        # 3.335 with half_up -> 3.34; default (half_even) -> 3.34 as well here, so use a
        # value that distinguishes: 3.345 half_even -> 3.34, half_up -> 3.35.
        amt = self._euro("3.345")
        assert format(amt, "plain,half_even") == "3.34"
        assert format(amt, "plain,half_up") == "3.35"

    def test_non_currency_quantity_unchanged(self):
        from clausal.modules.py.units import Metre
        q = Quantity(5.0, {Metre: 1})
        assert format(q, "") == str(q)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_currency_money.py::TestCurrencyFormat -v`
Expected: FAIL — default `__format__` returns `str(self)` (`"3.33 euro"`), not `"3.33 EUR"`; `format(amt, "symbol")` returns `str` formatted, not `"€3.33"`.

- [ ] **Step 3: Extend `Quantity.__format__`**

In `clausal/terms.py`, replace `Quantity.__format__` (~line 1999):

```python
    def __format__(self, spec: str) -> str:
        cur = None
        if len(self._dims) == 1:
            (key, exp), = self._dims.items()
            if exp == 1 and getattr(key, "is_currency", False):
                cur = key
        if cur is None:
            return format(str(self), spec)
        # currency spec: "<style>" or "<style>,<mode>"; default style code, mode half_even
        style, _, mode = spec.partition(",")
        style = style or "code"
        mode = mode or "half_even"
        from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_HALF_DOWN, \
            ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR
        modes = {"half_even": ROUND_HALF_EVEN, "half_up": ROUND_HALF_UP,
                 "half_down": ROUND_HALF_DOWN, "up": ROUND_UP, "down": ROUND_DOWN,
                 "ceiling": ROUND_CEILING, "floor": ROUND_FLOOR}
        rounding = modes.get(mode)
        if rounding is None:
            raise ValueError(f"unknown money format mode {mode!r}")
        v = self._value.quantize(Decimal(1).scaleb(-cur.scale), rounding=rounding)
        if style == "symbol":
            return f"{cur.symbol}{v}"
        if style == "code":
            return f"{v} {cur.iso_code}"
        if style == "name":
            return f"{v} {cur._name}"
        if style == "plain":
            return f"{v}"
        raise ValueError(f"unknown money format style {style!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_currency_money.py::TestCurrencyFormat -v`
Expected: PASS.

- [ ] **Step 5: Full sweep + commit (named paths only)**

Run: `python -m pytest tests/test_currency_money.py tests/test_currency.py tests/test_quantity_decimal.py tests/test_units.py -q`
Expected: PASS (all).

```bash
git add clausal/terms.py tests/test_currency_money.py
git commit -m "feat(currency): currency-aware Quantity.__format__ for f-strings"
```

---

## Self-Review

**Spec coverage (Plan 3 = §1.5.2 precision check + §1.6 builtins/formatting):**
- §1.5.2 construction-time precision check, trailing-zero-safe, tagging-only, `CurrencyPrecisionError`, `money_precise` escape → Task 1 (check) + Task 2 (`money`/`money_precise`). ✓
- §1.6 `money_round`/`money_str`/`money_format` explicit-mode, mode→`decimal.ROUND_*`, `money`/`money_precise`, accessors, `__format__` → Tasks 2–4. ✓
- Deferred to Plan 4 (absent here): structural lexeme capture. Literal exactness meanwhile via Plan 2's `Decimal(str(f))`.

**Placeholder scan:** none — every step has concrete code, exact values, and commands.

**Type consistency:** `_currency_of`, `_quantize`, `_format_value`, `_simple_to_trampoline`, `_MODES` defined in `currency.py` Task 2/3 and reused consistently. `_check_currency_precision`/`CurrencyPrecisionError` in `terms.py` Task 1. Modes are strings everywhere. The checked path is `Quantity(value, currency_pred)`; the unchecked path is `Quantity(value, dict(pred._dims))` — used by `money_precise` and `money_round`.

**Risk note for implementer:** the trampoline/dispatch wiring (`_simple_to_trampoline`, `ModulePredicate._register`, the `_run`/`_drive_trampoline` test helper) must match the working units pattern (`clausal/modules/units.py:445-513`, `tests/test_units.py` `run`). If a predicate doesn't dispatch, align to those references before improvising.

---

## Roadmap — Plan 4 (optional)

Structural source-lexeme literal capture: `Token` raw text → `PNumber.text` (`clausal/tools/prolog_ast.py`) → compiler lowering → `n(Unit)` sugar, so `7.89(euro)` builds `Decimal("7.89")` straight from the lexeme with no float ever existing — upgrading literal exactness from empirical (`Decimal(str(f))`, exact for all typed literals) to structural. Also fold in the deferred gaps in `.superpowers/sdd/deferred-decimal-gaps.md` (`__pow__` Decimal×float; `_to_decimal` bad-string error type; bool bypass via the Quantity-dims branch).
