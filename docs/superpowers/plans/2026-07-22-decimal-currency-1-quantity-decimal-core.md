# Decimal Currency — Plan 1: Decimal support in the Quantity/number layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Clausal's `Quantity` and term renderer correctly support `decimal.Decimal` magnitudes, so a later currency layer can store exact decimal amounts and mix them with plain numeric rates without `TypeError` or wrong rendering.

**Architecture:** Two small, self-contained changes in `clausal/terms.py`: (1) render a bare/embedded `Decimal` as its plain string in `term_str`; (2) coerce a plain `float` operand to `Decimal` inside `Quantity` arithmetic whenever the other operand is a `Decimal`, so exact-decimal magnitudes survive multiplication/division/addition by plain scalars. No language-surface, lexer, or module changes — this is pure runtime numeric plumbing, testable at the Python level.

**Tech Stack:** Python 3.13, `decimal.Decimal`, pytest.

## Global Constraints

- Coercion of a `float` to `Decimal` MUST go through `Decimal(str(f))`, NEVER `Decimal(f)` — the latter exposes the raw binary expansion (`Decimal(0.2)` == `0.2000000000000000111…`) and corrupts money.
- `bool` is an `int` subclass; numeric coercion helpers MUST reject `bool` (do not treat `True`/`False` as numbers) — consistent with resolved decision A01-D001 (split bool from int).
- Do not change the meaning of general `float` literals; `Decimal` is opt-in via explicit construction only.
- Preserve all existing units/`Quantity` behavior: `+`/`-` require identical dims (`UnitsMismatch` otherwise); `*`/`/` merge dims; dimensioned + plain number raises. This plan only adds Decimal handling *within* those paths.
- Follow the existing file's style; no unrelated refactoring.
- Spec: `docs/superpowers/specs/2026-07-22-decimal-currency-design.md` (§1.1, §1.4, §1.7).

---

## File Structure

- Modify: `clausal/terms.py`
  - add `from decimal import Decimal` to the module imports
  - `term_str` (two numeric branches at ~2246 and ~2494): add a `Decimal` branch
  - `Quantity` (class at ~1787): add a `_num_pair` static helper; apply it in
    `__add__`, `__radd__`, `__sub__`, `__rsub__`, `__mul__`, `__rmul__`,
    `__truediv__`, `__rtruediv__`
- Create: `tests/test_quantity_decimal.py` — Python-level unit tests for the above.

**Running tests:** from `/workspace/clausal-bug-fix`, `python -m pytest tests/test_quantity_decimal.py -v`. If the active venv lacks pytest, use the pyenv 3.13.3 interpreter with the repo root on `PYTHONPATH` (e.g. `PYTHONPATH=. ~/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_quantity_decimal.py -v`).

---

### Task 1: Render `Decimal` as a plain number in `term_str`

**Files:**
- Modify: `clausal/terms.py` (imports; two `term_str` numeric branches at ~2246 and ~2494)
- Test: `tests/test_quantity_decimal.py`

**Interfaces:**
- Consumes: `clausal.terms.term_str(t) -> str`, `clausal.terms.Compound`.
- Produces: `term_str` renders a `Decimal` as `str(d)` (e.g. `"7.89"`), not `repr` (`"Decimal('7.89')"`), both standalone and nested in a `Compound`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_quantity_decimal.py`:

```python
from decimal import Decimal

from clausal.terms import term_str, Compound


class TestDecimalRendering:
    def test_bare_decimal_renders_plainly(self):
        assert term_str(Decimal("7.89")) == "7.89"

    def test_decimal_no_trailing_zeros_lost(self):
        # str(Decimal) preserves scale; repr would wrap it in Decimal('...').
        assert term_str(Decimal("7.90")) == "7.90"

    def test_decimal_nested_in_compound(self):
        s = term_str(Compound("price", (Decimal("1.50"),)))
        assert "1.50" in s
        assert "Decimal(" not in s
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_quantity_decimal.py::TestDecimalRendering -v`
Expected: FAIL — bare decimal renders as `"Decimal('7.89')"` (repr path), assertion mismatch.

- [ ] **Step 3: Add the import**

At the top of `clausal/terms.py`, with the other stdlib imports, add:

```python
from decimal import Decimal
```

- [ ] **Step 4: Add a `Decimal` branch to both `term_str` numeric branches**

In `clausal/terms.py`, there are two functions with an identical numeric branch:

```python
    if isinstance(t, (int, float, complex)):
        return _c(repr(t), 'number', style)
```

Immediately **before** each of those two branches (at ~line 2246 and ~line 2494), insert a dedicated `Decimal` branch that renders with `str` (not `repr`):

```python
    if isinstance(t, Decimal):
        return _c(str(t), 'number', style)
```

(`Decimal` is not an `int`/`float` subclass, so it would otherwise fall through to a generic branch; and `repr(Decimal(...))` would print `Decimal('…')`, which is wrong for a term renderer.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_quantity_decimal.py::TestDecimalRendering -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add clausal/terms.py tests/test_quantity_decimal.py
git commit -m "feat(terms): render Decimal as a plain number in term_str"
```

---

### Task 2: Coerce plain scalars to `Decimal` inside `Quantity` arithmetic

**Files:**
- Modify: `clausal/terms.py` (`Quantity` class, ~1787–1922)
- Test: `tests/test_quantity_decimal.py`

**Interfaces:**
- Consumes: `clausal.terms.Quantity(value, dims)`.
- Produces: `Quantity._num_pair(a, b) -> tuple` — a staticmethod returning `(a, b)`
  with the plain operand coerced to `Decimal` when exactly one of them is a `Decimal`
  (float via `Decimal(str(f))`, int via `Decimal(i)`); otherwise unchanged. Applied in
  `__add__`, `__radd__`, `__sub__`, `__rsub__`, `__mul__`, `__rmul__`, `__truediv__`,
  `__rtruediv__`, so a `Decimal`-valued `Quantity` combines with `int`/`float` scalars and
  with mixed-value quantities without `TypeError`, preserving exactness.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quantity_decimal.py`:

```python
from clausal.terms import Quantity


class TestDecimalArithmeticCoercion:
    def test_decimal_quantity_times_float_scalar(self):
        # Decimal * float would raise TypeError without coercion.
        q = Quantity(Decimal("100.00"), {})  # dimensionless
        r = q * 0.2
        assert isinstance(r.value, Decimal)
        assert r.value == Decimal("20.000")

    def test_float_scalar_times_decimal_quantity(self):
        q = Quantity(Decimal("100.00"), {})
        r = 0.2 * q
        assert r.value == Decimal("20.000")

    def test_decimal_quantity_divided_by_float(self):
        q = Quantity(Decimal("10.00"), {})
        r = q / 4.0
        assert r.value == Decimal("2.5")

    def test_decimal_quantity_divided_by_int_still_exact(self):
        q = Quantity(Decimal("10.00"), {})
        r = q / 4
        assert r.value == Decimal("2.5")

    def test_dimensionless_decimal_plus_float(self):
        q = Quantity(Decimal("1.50"), {})
        r = q + 0.25
        assert r.value == Decimal("1.75")

    def test_coercion_uses_str_not_binary_expansion(self):
        # The load-bearing rule: Decimal(str(0.2)) == 0.2, NOT Decimal(0.2).
        q = Quantity(Decimal("1"), {})
        r = q * 0.2
        assert r.value == Decimal("0.2")

    def test_mixed_value_quantities_same_dims_add(self):
        from clausal.modules.py.units import Metre
        a = Quantity(Decimal("1.5"), {Metre: 1})
        b = Quantity(0.25, {Metre: 1})  # float-valued, same dims
        r = a + b
        assert r.value == Decimal("1.75")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_quantity_decimal.py::TestDecimalArithmeticCoercion -v`
Expected: FAIL with `TypeError: unsupported operand type(s) for *: 'decimal.Decimal' and 'float'` (and similar) on the coercion cases.

- [ ] **Step 3: Add the `_num_pair` helper**

In `clausal/terms.py`, inside `class Quantity`, next to the existing `_merge_dims`
staticmethod (~line 1869), add:

```python
    @staticmethod
    def _num_pair(a, b):
        """Return (a, b) with a plain float coerced to Decimal when the other
        operand is a Decimal, so Decimal arithmetic never raises TypeError and
        stays exact. Uses Decimal(str(f)) — never Decimal(f) — and leaves ints
        alone (Decimal op int is already exact)."""
        if isinstance(a, Decimal) and isinstance(b, float) and not isinstance(b, bool):
            return a, Decimal(str(b))
        if isinstance(b, Decimal) and isinstance(a, float) and not isinstance(a, bool):
            return Decimal(str(a)), b
        return a, b
```

- [ ] **Step 4: Apply `_num_pair` in the arithmetic methods**

Replace the eight arithmetic methods (~lines 1883–1922) with versions that coerce
before combining values. The dims logic is unchanged; only the value math is wrapped.

```python
    def __add__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            a, b = self._num_pair(self._value, other)
            return Quantity(a + b, {})
        self._require_same_dims(other, "add")
        a, b = self._num_pair(self._value, other._value)
        return Quantity(a + b, self._dims)

    def __radd__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            a, b = self._num_pair(other, self._value)
            return Quantity(a + b, {})
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            a, b = self._num_pair(self._value, other)
            return Quantity(a - b, {})
        self._require_same_dims(other, "subtract")
        a, b = self._num_pair(self._value, other._value)
        return Quantity(a - b, self._dims)

    def __rsub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            a, b = self._num_pair(other, self._value)
            return Quantity(a - b, {})
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, +1)
            a, b = self._num_pair(self._value, other._value)
            return Quantity(a * b, new_dims)
        a, b = self._num_pair(self._value, other)
        return Quantity(a * b, self._dims)

    def __rmul__(self, other):
        a, b = self._num_pair(other, self._value)
        return Quantity(a * b, self._dims)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, -1)
            a, b = self._num_pair(self._value, other._value)
            return Quantity(a / b, new_dims)
        a, b = self._num_pair(self._value, other)
        return Quantity(a / b, self._dims)

    def __rtruediv__(self, other):
        new_dims = {k: -v for k, v in self._dims.items()}
        a, b = self._num_pair(other, self._value)
        return Quantity(a / b, new_dims)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_quantity_decimal.py::TestDecimalArithmeticCoercion -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit**

```bash
git add clausal/terms.py tests/test_quantity_decimal.py
git commit -m "feat(terms): coerce plain scalars to Decimal in Quantity arithmetic"
```

---

### Task 3: Regression guard — existing units suite stays green

**Files:**
- Test: `tests/test_units.py` (existing, unchanged), `tests/test_quantity_decimal.py`

**Interfaces:**
- Consumes: the full existing `Quantity`/units behavior.
- Produces: confidence that Decimal handling did not regress float-valued quantities,
  dimension enforcement, comparisons, hashing, or unification.

- [ ] **Step 1: Add a characterization test that float quantities are unchanged**

Append to `tests/test_quantity_decimal.py`:

```python
class TestNoRegressionFloatQuantities:
    def test_float_quantity_arithmetic_unchanged(self):
        from clausal.modules.py.units import Metre, Second
        d = Quantity(20.0, {Metre: 1})
        t = Quantity(2.0, {Second: 1})
        v = d / t
        assert v.value == 10.0
        assert v.dims == {Metre: 1, Second: -1}

    def test_dimension_mismatch_still_raises(self):
        from clausal.terms import UnitsMismatch
        from clausal.modules.py.units import Metre, Second
        import pytest
        with pytest.raises(UnitsMismatch):
            _ = Quantity(1.0, {Metre: 1}) + Quantity(1.0, {Second: 1})

    def test_dimensioned_plus_plain_number_still_raises(self):
        from clausal.terms import UnitsMismatch
        from clausal.modules.py.units import Metre
        import pytest
        with pytest.raises(UnitsMismatch):
            _ = Quantity(1.0, {Metre: 1}) + 5
```

- [ ] **Step 2: Run the new file and the full units suite**

Run: `python -m pytest tests/test_quantity_decimal.py tests/test_units.py -v`
Expected: PASS (all new tests + the entire existing `tests/test_units.py`).

- [ ] **Step 3: Commit**

```bash
git add tests/test_quantity_decimal.py
git commit -m "test(terms): guard float-quantity behavior after Decimal support"
```

---

## Self-Review

**Spec coverage (this plan = §1.1 Decimal magnitudes storable + §1.4 arithmetic coercion + §1.7 rendering):**
- §1.7 Decimal rendering → Task 1. ✓
- §1.4 arithmetic value coercion (Decimal meets plain scalar without TypeError, exact) → Task 2. ✓
- §1.1 `Quantity._value` may be `Decimal` → storage already works unchanged (no `__init__` guard rejects it); exercised by Tasks 2–3. ✓
- Out of scope for this plan (deferred): currency metadata (§1.5), construction-time coercion & precision check (§1.5.2), exact literal capture (§1.2), builtins/formatting (§1.6), the vocabulary (Layer 2). These are Plans 2 and 3.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `_num_pair` defined in Task 2 and used only there; `Decimal` import added in Task 1 and reused in Task 2. `term_str` and `Quantity` signatures match the current source read at `clausal/terms.py:1787`, `:2231`, `:2494`.

---

## Roadmap — subsequent plans (written when Plan 1 lands)

**Plan 2 — Currency vocabulary, metadata & qualified naming.** Add currency metadata
(`is_currency`, `scale`, `iso_code`, `symbol`) to the unit-predicate object; author the
built-in jurisdiction modules (`european_union`, `united_states`, `japan`, …) exporting
canonical spelled-out currency predicates (one canonical home per currency, no re-exports);
register them in `_IMPORT_ALIASES` (`clausal/templating/term_rewriting.py:1392`); make
`Quantity` construction from a currency predicate coerce the value to `Decimal` (value
invariant). *Spike first (both confirmed feasible by regression tests but unverified for
Python-module currency objects in unit position): (a) `_is_unit_expr`
(`term_rewriting.py:345`) must accept `Attribute` nodes so `european_union.euro` parses in
`n(Unit)` position; (b) module-qualified reference to a Python currency object resolves as a
value in unit/term position (the `.clausal`-atom case is proven in
`tests/test_module_imports.py:261`).* Deliverable: importable currencies with dimension-safe,
Decimal-backed arithmetic (`0.1(euro)+0.2(euro)`, `euro+dollar` → `UnitsMismatch`).

**Plan 3 — Exact literal capture, precision check & money builtins.** Preserve the numeric
literal's source lexeme (`Token` already carries span but not raw text →
`clausal/tools/prolog_tokenizer.py` `_read_number`; `PNumber` gains `text` →
`clausal/tools/prolog_ast.py:30`; thread through the compiler lowering and the `n(Unit)`
sugar in `term_rewriting.py:559`) so `7.89(euro)` builds `Decimal("7.89")` from text, never a
float; add the construction-time precision check + `CurrencyPrecisionError` (§1.5.2); add the
builtins `money/3`, `money_precise/3`, `money_round/3`, `money_str/3`, `money_format/4`, the
rounding-mode-atom → `decimal` mapping, accessors `currency_scale`/`currency_code`/
`currency_symbol`, and `Quantity.__format__` currency styles (§1.6). Deliverable: end-to-end
`.clausal` currency literals, exact math, explicit-mode rounding/formatting.
