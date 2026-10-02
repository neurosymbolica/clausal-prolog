# CLP Units Side Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let quantities and units-attributed variables take part in CLP comparisons, `in_domain/3` and `label/1`, with dimensional analysis done in a side channel before any solver runs and units reattached when the solver binds.

**Architecture:** A new module `clausal/logic/units_clp.py` analyses the two expression trees of a comparison (dimension inference + a hand-written rule table), replaces every `Quantity` by its bare solver number (`Decimal → Fraction`) and every united variable by a bare *shadow* variable, and hands the result to the unchanged solvers. Two attribute hooks couple a united variable and its shadow in both directions, so a solver binding of the shadow binds the user's variable to a `Quantity`. Errors are the ISO 13211 term `error(system_error(units_mismatch), Context)`.

**Tech Stack:** Python 3.13, the existing AttVar hook registry (`register_attr_hook`), CLP(FD)/CLP(Q)/CLP(R) in `clausal/logic/clpfd.py` / `clpq.py` / `clpr.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md`

## Global Constraints

- Run every command from `/workspace/clausal-bug-fix` with `/workspace/clausal/venv/bin/python -m pytest` (cwd wins; see memory `running-tests-in-bug-fix-clone`).
- No solver module changes: `clpq.py`, `clpr.py`, the C cores. `clpfd.py` gains call sites only.
- No float on any money path: assert the type at the shadow and at the reattached value.
- The solver's number comes back exact and unconverted (`int` or `Fraction`); never convert to `Decimal` on the way out.
- Error spelling: `error(system_error(units_mismatch), Context)`; inference failure: `error(system_error(units_undetermined), Context)`. The Python class name `UnitsMismatch` never reaches the surface from this code.
- Stage explicit paths; never `git add -A` (memory `never-git-add-A-in-the-shared-clone`).
- Every commit message ends with the session attribution lines given in the system prompt.
- `#=` opens a comment in `.clausal` source; fixtures use infix `==`, `!=`, `<`, `<=`, `>`, `>=`, which reach the same functions.

---

### Task 1: `system_error/2` helper

**Files:**
- Modify: `clausal/logic/exceptions.py` (next to `type_error`, line 245)
- Test: `tests/test_units_clp.py` (new file; later tasks append to it)

**Interfaces:**
- Produces: `system_error(code: str, context: str = "") -> Compound` building `error(system_error(Code), Context)` with `Code` minted as an atom via `_name_atom`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_units_clp.py
"""Units side channel around CLP: dimension analysis, shadows, reattachment.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md
"""
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.terms import Compound, Quantity


def _assert_system_error(ei, code):
    term = ei.value.term
    assert isinstance(term, Compound) and term.functor == "error"
    inner = term.args[0]
    assert isinstance(inner, Compound) and inner.functor == "system_error"
    assert inner.args[0] == mint(code)


class TestSystemErrorHelper:
    def test_builds_iso_shape(self):
        from clausal.logic.exceptions import system_error
        term = system_error("units_mismatch", "(==)/2: metre vs second")
        assert term.functor == "error"
        assert term.args[0].functor == "system_error"
        assert term.args[0].args == (mint("units_mismatch"),)
        assert term.args[1] == "(==)/2: metre vs second"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q`
Expected: FAIL with `ImportError: cannot import name 'system_error'`

- [ ] **Step 3: Write minimal implementation**

Add after `instantiation_error` in `clausal/logic/exceptions.py`:

```python
def system_error(code: str, context: str = "") -> Compound:
    """Build error(system_error(Code), Context).

    ISO 13211-1 §7.12.2 lists ``system_error`` for errors outside the
    standard's own catalogue; the engine puts its own error CODE inside it
    so a ``catch/3`` pattern can select one kind (``units_mismatch``,
    ``units_undetermined``, …) without matching every system error. *Code*
    is minted as an atom like the names in :func:`type_error`; *Context* is
    human text.
    """
    inner = Compound("system_error", (_name_atom(code),))
    return Compound("error", (inner, context))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/exceptions.py tests/test_units_clp.py
git commit -m "feat(exceptions): system_error/2 helper in the ISO 13211 shape"
```

---

### Task 2: Exact-number widening for currency quantities

**Files:**
- Modify: `clausal/terms.py:2014-2041` (`_check_currency_precision`, `_quantize_to_scale`) and `clausal/terms.py:2222-2232` (`Quantity.__init__` coercion)
- Test: `tests/test_units_clp.py`

**Interfaces:**
- Produces: a currency `Quantity` keeps a `Fraction` value; `_quantize_to_scale` accepts `Fraction`; `_round_fraction_to_int(fr: Fraction, rounding) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_units_clp.py`:

```python
from decimal import (ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN, ROUND_UP,
                     ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR)
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.kuwait import kwd

_MODES = [ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN, ROUND_UP,
          ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR]


class TestExactNumberCurrency:
    def test_currency_quantity_keeps_fraction(self):
        q = Quantity(Fraction(1, 3), {euro: 1})
        assert type(q.value) is Fraction and q.value == Fraction(1, 3)

    def test_decimal_and_fraction_quantities_compare_equal(self):
        assert Quantity(Decimal("1500.00"), {euro: 1}) == Quantity(Fraction(1500), {euro: 1})
        assert hash(Quantity(Decimal("1500.00"), {euro: 1})) == hash(Quantity(Fraction(1500), {euro: 1}))

    def test_tagging_terminating_fraction_passes_precision_check(self):
        q = Quantity(Fraction(3, 2), euro)          # 1.50, within scale 2
        assert q.value == Fraction(3, 2)

    def test_tagging_non_terminating_fraction_fails_precision_check(self):
        from clausal.terms import CurrencyPrecisionError
        with pytest.raises(CurrencyPrecisionError):
            Quantity(Fraction(1, 3), euro)

    @pytest.mark.parametrize("mode", _MODES)
    @pytest.mark.parametrize("num", [-27, -25, -23, -5, -1, 0, 1, 5, 23, 25, 27, 125, 135])
    def test_fraction_rounding_agrees_with_decimal_rounding(self, mode, num):
        """Positive control: on terminating fractions the Fraction rounder and
        Decimal.quantize must give the same integer for every mode."""
        from clausal.terms import _round_fraction_to_int
        fr = Fraction(num, 10)                       # x.5 ties and non-ties, both signs
        expected = int(Decimal(num).scaleb(-1).quantize(Decimal(1), rounding=mode))
        assert _round_fraction_to_int(fr, mode) == expected

    def test_quantize_fraction_third_of_a_yen(self):
        from clausal.terms import _quantize_to_scale
        assert _quantize_to_scale(Fraction(1000, 3), 0, "half_even") == Decimal("333")
        assert _quantize_to_scale(Fraction(1, 3), 3, "half_even") == Decimal("0.333")

    def test_money_round_on_fraction_quantity(self):
        from clausal.logic.variables import Trail, Var, deref
        from clausal.modules.currency import _money_round_impl
        q = Quantity(Fraction(1000, 3), {yen: 1})
        out = Var()
        assert list(_money_round_impl(q, "half_even", out, Trail())) == [None]
        assert deref(out) == Quantity(Decimal("333"), {yen: 1})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k ExactNumber`
Expected: FAIL — `TypeError: cannot coerce Fraction(1, 3) to a Decimal currency amount`, and `ImportError` for `_round_fraction_to_int`

- [ ] **Step 3: Implement**

In `clausal/terms.py` add `from fractions import Fraction` to the imports. Replace `_check_currency_precision` and `_quantize_to_scale`:

```python
def _check_currency_precision(value, currency) -> None:
    """Raise CurrencyPrecisionError if `value` carries digits below `currency`'s
    scale. Trailing zeros are allowed (7.890 == 7.89). `value` is a Decimal or
    an exact Fraction (a Fraction is in scale iff value * 10**scale is
    integral)."""
    scale = currency.scale
    if isinstance(value, Fraction):
        in_scale = (value * 10 ** scale).denominator == 1
    else:
        in_scale = value == value.quantize(Decimal(1).scaleb(-scale))
    if not in_scale:
        raise CurrencyPrecisionError(
            f"{value} has more decimal places than {currency._name} supports "
            f"(scale {scale}). Combine per-currency literals "
            f"(e.g. 0.1(euro) + 0.2(euro)), round explicitly with "
            f"money_round(V, Mode, Out), or use money_precise for deliberate "
            f"sub-scale amounts."
        )


def _round_fraction_to_int(fr: Fraction, rounding) -> int:
    """Round an exact rational to an integer under a ``decimal`` ROUND_* mode.

    Exact by construction — no intermediate Decimal division — so a CLP(Q)
    result such as a third of a yen rounds once, at the caller's chosen
    mode, and nowhere else. ``divmod`` floors, so ``q < fr < q + 1`` when the
    remainder is non-zero, and the tie test compares ``2 * rem`` with ``d``.
    """
    n, d = fr.numerator, fr.denominator
    q, rem = divmod(n, d)
    if rem == 0:
        return q
    if rounding == ROUND_FLOOR:
        return q
    if rounding == ROUND_CEILING:
        return q + 1
    if rounding == ROUND_DOWN:                    # toward zero
        return q if fr > 0 else q + 1
    if rounding == ROUND_UP:                      # away from zero
        return q + 1 if fr > 0 else q
    twice = 2 * rem
    if twice < d:
        return q
    if twice > d:
        return q + 1
    # exact tie
    if rounding == ROUND_HALF_UP:                 # away from zero
        return q + 1 if fr > 0 else q
    if rounding == ROUND_HALF_DOWN:               # toward zero
        return q if fr > 0 else q + 1
    if rounding == ROUND_HALF_EVEN:
        return q if q % 2 == 0 else q + 1
    raise ValueError(f"unsupported rounding mode {rounding!r}")


def _quantize_to_scale(value, scale, mode_str):
    """Quantize a Decimal — or an exact Fraction — to `scale` decimal places
    using a mode string. A Fraction is rounded exactly, without passing
    through a Decimal division first."""
    rounding = _MONEY_ROUNDING.get(mode_str)
    if rounding is None:
        raise ValueError(f"unknown rounding mode {mode_str!r}; expected one of "
                         f"{sorted(_MONEY_ROUNDING)}")
    unit = Decimal(1).scaleb(-scale)
    if isinstance(value, Fraction):
        units = _round_fraction_to_int(value * 10 ** scale, rounding)
        return Decimal(units).scaleb(-scale).quantize(unit)
    return value.quantize(unit, rounding=rounding)
```

In `Quantity.__init__`, change the coercion guard:

```python
        if not isinstance(self._value, (Decimal, Fraction)):
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
                    self._value = _to_decimal(self._value)
                    break
```

Update the `Quantity` class docstring's "Arithmetic" section with one line: `A currency value is an exact number: int, Fraction or Decimal. A Fraction is kept as-is (a CLP(Q) result such as a third of a yen); float is coerced through str.`

- [ ] **Step 4: Run tests to verify they pass, and the existing money tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py tests/test_currency_money.py tests/test_currency.py tests/test_currency_minor_units.py tests/test_quantity_decimal.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add clausal/terms.py tests/test_units_clp.py
git commit -m "feat(currency): a currency Quantity keeps an exact Fraction; rounding of a Fraction is exact"
```

---

### Task 3: Dimension analysis (pure, no engine wiring)

**Files:**
- Create: `clausal/logic/units_clp.py`
- Test: `tests/test_units_clp.py`

**Interfaces:**
- Produces:
  - `analyse(l, r, context: str) -> tuple[dict, dict, dict[int, dict]]` — returns `(dims_l, dims_r, env)` where `env` maps `var._id → dims dict` for every Var leaf; raises `LogicException(system_error("units_mismatch", ...))` on disagreement and `LogicException(system_error("units_undetermined", ...))` when a var's dims cannot be inferred.
  - `ground_dims(tree) -> dict` — dims of a fully ground tree (used by the positive control).
  - `has_units_material(x) -> bool` — True if `x` is a Quantity, a Var with a `units` attribute, or a tree containing either.
  - Leaf classification rule: a leaf that is none of number / Quantity / Var / expression node makes `has_units_material` and `analyse` **bail out** (`analyse` raises `_NotEngaged`; `strip_for_solver` in Task 5 turns that into `None`) so the existing non-numeric guards keep their error.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_units_clp.py`:

```python
import random

from clausal.logic.variables import Trail, Var, deref, get_attr, put_attr, unify
from clausal.modules.py.units import metre, second, ampere, volt, ohm, watt, kilogram
from clausal.terms import Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate, UnitsMismatch

M = {metre: 1}
S = {second: 1}


def _dims_of_value(v):
    return dict(v.dims) if isinstance(v, Quantity) else {}


def _eval_with_quantity_arithmetic(t):
    """Fold a ground tree with Quantity's own operators — the oracle."""
    if isinstance(t, Add):
        return _eval_with_quantity_arithmetic(t.left) + _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Sub):
        return _eval_with_quantity_arithmetic(t.left) - _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Mult):
        return _eval_with_quantity_arithmetic(t.left) * _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Div):
        return _eval_with_quantity_arithmetic(t.left) / _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Pow):
        return _eval_with_quantity_arithmetic(t.left) ** _eval_with_quantity_arithmetic(t.right)
    if isinstance(t, Negate):
        return -_eval_with_quantity_arithmetic(t.operand)
    return t


_LEAVES = [2, 3, Quantity(3, M), Quantity(5, M), Quantity(4, S), Quantity(7, {}),
           Quantity(2, {kilogram: 1})]


def _random_tree(rng, depth):
    if depth == 0 or rng.random() < 0.3:
        return rng.choice(_LEAVES)
    op = rng.choice(["add", "sub", "mult", "div", "pow", "neg"])
    if op == "neg":
        return Negate(_random_tree(rng, depth - 1))
    if op == "pow":
        return Pow(_random_tree(rng, depth - 1), rng.choice([2, 3]))
    cls = {"add": Add, "sub": Sub, "mult": Mult, "div": Div}[op]
    return cls(_random_tree(rng, depth - 1), _random_tree(rng, depth - 1))


class TestRuleTablePositiveControl:
    def test_ground_dims_agree_with_quantity_arithmetic(self):
        from clausal.logic.units_clp import ground_dims
        rng = random.Random(20260912)
        seen_ok = seen_err = 0
        for _ in range(3000):
            tree = _random_tree(rng, 3)
            try:
                expected = _dims_of_value(_eval_with_quantity_arithmetic(tree))
            except UnitsMismatch:
                with pytest.raises(LogicException) as ei:
                    ground_dims(tree)
                _assert_system_error(ei, "units_mismatch")
                seen_err += 1
                continue
            except (ZeroDivisionError, TypeError, OverflowError):
                continue          # arithmetic accident, not a units question
            assert ground_dims(tree) == expected, tree
            seen_ok += 1
        assert seen_ok > 500 and seen_err > 100   # the control actually exercised both arms

    def test_floordiv_and_mod_follow_divmod_rules(self):
        from clausal.logic.units_clp import ground_dims
        assert ground_dims(FloorDiv(Quantity(7, M), Quantity(2, M))) == {}
        assert ground_dims(Mod(Quantity(7, M), Quantity(2, M))) == M
        with pytest.raises(LogicException) as ei:
            ground_dims(FloorDiv(Quantity(7, M), 2))
        _assert_system_error(ei, "units_mismatch")


class TestInference:
    def test_fresh_var_beside_metre_in_sub_is_metre(self):
        from clausal.logic.units_clp import analyse
        x, y = Var(), Var()
        dl, dr, env = analyse(x, Sub(Quantity(3, M), y), "(==)/2")
        assert dl == M and dr == M
        assert env[x._id] == M and env[y._id] == M

    def test_product_with_one_unknown_factor_defaults_the_factor(self):
        from clausal.logic.units_clp import analyse
        total, qty = Var(), Var()
        dl, dr, env = analyse(total, Mult(Quantity(Decimal("2.00"), {euro: 1}), qty), "(==)/2")
        assert env[total._id] == {euro: 1} and env[qty._id] == {}

    def test_ohms_law_infers_volt(self):
        from clausal.logic.units_clp import analyse
        v = Var()
        _, _, env = analyse(v, Mult(Quantity(2, {ampere: 1}), Quantity(3, {ohm: 1})), "(==)/2")
        assert env[v._id] == dict(volt._dims)

    def test_product_with_two_unknown_factors_is_undetermined(self):
        from clausal.logic.units_clp import analyse
        x, y, z = Var(), Var(), Var()
        put_attr(x, "units", __import__("clausal.logic.units_constraint", fromlist=["UnitState"]).UnitState(M), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, Mult(y, z), "(==)/2")
        _assert_system_error(ei, "units_undetermined")

    def test_plain_number_beside_dimensioned_in_add_mismatches(self):
        from clausal.logic.units_clp import analyse
        with pytest.raises(LogicException) as ei:
            analyse(Var(), Add(Quantity(3, M), 1), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_mixed_currencies_mismatch_and_name_both(self):
        from clausal.logic.units_clp import analyse
        from clausal.modules.countries.united_states import usd
        with pytest.raises(LogicException) as ei:
            analyse(Var(), Add(Quantity(Decimal("1.00"), {euro: 1}), Quantity(Decimal("1.00"), {usd: 1})), "(==)/2")
        _assert_system_error(ei, "units_mismatch")
        assert "euro" in ei.value.term.args[1] and "dollar" in ei.value.term.args[1]

    def test_declared_units_var_disagreeing_with_operand_mismatches(self):
        from clausal.logic.units_clp import analyse
        from clausal.logic.units_constraint import UnitState
        x = Var()
        put_attr(x, "units", UnitState(S), Trail())
        with pytest.raises(LogicException) as ei:
            analyse(x, Quantity(3, M), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_solver_var_without_units_is_a_bare_number(self):
        from clausal.logic.units_clp import analyse
        from clausal.logic.clpfd import in_domain
        y = Var()
        assert in_domain(y, 1, 5, Trail())
        with pytest.raises(LogicException) as ei:
            analyse(Var(), Sub(Quantity(3, M), y), "(==)/2")
        _assert_system_error(ei, "units_mismatch")

    def test_dimensionless_result_is_bare(self):
        from clausal.logic.units_clp import analyse
        r = Var()
        _, _, env = analyse(r, Div(Quantity(6, M), Quantity(3, M)), "(==)/2")
        assert env[r._id] == {}

    def test_no_material_is_not_engaged(self):
        from clausal.logic.units_clp import has_units_material
        assert not has_units_material(Add(Var(), 3))
        assert has_units_material(Add(Var(), Quantity(3, M)))

    def test_non_numeric_leaf_is_not_engaged(self):
        from clausal.logic.units_clp import has_units_material
        assert not has_units_material(Add(Quantity(3, M), "banana"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k "RuleTable or Inference"`
Expected: FAIL with `ModuleNotFoundError: No module named 'clausal.logic.units_clp'`

- [ ] **Step 3: Write the module**

Create `clausal/logic/units_clp.py`:

```python
"""clausal.logic.units_clp — the units side channel around CLP.

A CLP comparison is two expression trees. Quantities and units-attributed
variables may appear anywhere in them, but the solvers (CLP(FD), CLP(Q),
CLP(R), and the C cores behind them) only ever see bare numbers and bare
variables. This module sits between the two:

  1. ``analyse``   — dimensional analysis on the trees, FIRST. Infers the
                     dims of every variable, applies one rule per node, and
                     throws ``error(system_error(units_mismatch), Ctx)``
                     before any solver runs.
  2. ``strip``     — every ``Quantity`` becomes its solver number
                     (``Decimal -> Fraction``, exact), every united variable
                     becomes its bare *shadow* variable.
  3. the link hook — when the solver binds a shadow, the user's variable is
                     bound to a ``Quantity`` with the computed dims; the
                     ``units`` hook in ``units_constraint`` does the other
                     direction.

Spec: docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md.
Written with no clpfd import at module level so a second solver front end
(CLP(Z3)'s ``_z3_arith_binary``) can call ``strip_for_solver`` unchanged.
"""

from __future__ import annotations

import numbers
from decimal import Decimal
from fractions import Fraction
from typing import Any

from clausal.logic.variables import (
    Trail, Var, deref, is_var, get_attr, put_attr, unify, register_attr_hook,
    present_number,
)
from clausal.logic.units_constraint import UNITS_KEY, UnitState, to_solver_number

LINK_KEY = "units_link"

# Lazily imported node classes (clausal.terms imports the logic package).
_Add = _Sub = _Mult = _Div = _FloorDiv = _Mod = _Pow = _Negate = _Quantity = None
_BINARY: tuple = ()


def _ensure_imports() -> None:
    global _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate, _Quantity, _BINARY
    if _Add is None:
        from clausal.terms import (Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
                                   Negate, Quantity)
        _Add, _Sub, _Mult, _Div, _FloorDiv, _Mod, _Pow, _Negate = (
            Add, Sub, Mult, Div, FloorDiv, Mod, Pow, Negate)
        _Quantity = Quantity
        _BINARY = (Add, Sub, Mult, Div, FloorDiv, Mod, Pow)


class _NotEngaged(Exception):
    """A leaf the side channel does not speak for (atom, string, date, …).
    The caller falls back to the existing guards, which own that error."""


# ── dimension algebra ────────────────────────────────────────────────────────

def _merge(a: dict, b: dict, sign: int) -> dict:
    out = dict(a)
    for k, v in b.items():
        nv = out.get(k, 0) + sign * v
        if nv:
            out[k] = nv
        else:
            out.pop(k, None)
    return out


def _scale(a: dict, n: int) -> dict:
    return {k: v * n for k, v in a.items() if v * n != 0}


def _unscale(a: dict, n: int) -> dict | None:
    """Inverse of ``_scale``; None when some exponent is not divisible by n."""
    out = {}
    for k, v in a.items():
        if v % n:
            return None
        out[k] = v // n
    return out


def _render_pair(a: dict, b: dict) -> str:
    """``metre vs second``, qualifying same-named dimensions exactly as
    ``Quantity._require_same_dims`` does (``dollar (AUD) vs dollar (USD)``)."""
    from clausal.terms import _dims_str, _colliding_dim_names  # noqa: PLC0415
    left, right = _dims_str(a), _dims_str(b)
    if left == right:
        collide = _colliding_dim_names(a, b)
        left = _dims_str(a, qualify=collide)
        right = _dims_str(b, qualify=collide)
        if left == right:
            right += " — these are different dimensions that share a name"
    return f"{left or 'dimensionless'} vs {right or 'dimensionless'}"


def _mismatch(context: str, a: dict, b: dict, what: str = "") -> Exception:
    from clausal.logic.exceptions import LogicException, system_error  # noqa: PLC0415
    detail = f"{what}: " if what else ""
    return LogicException(system_error(
        "units_mismatch", f"{context}: {detail}{_render_pair(a, b)}"))


def _undetermined(context: str, vars_: list) -> Exception:
    from clausal.logic.exceptions import LogicException, system_error  # noqa: PLC0415
    names = ", ".join(repr(v) for v in vars_)
    return LogicException(system_error(
        "units_undetermined",
        f"{context}: cannot infer the units of {names}; declare one with "
        f"has_units/2 or multiply by a unit quantity"))


# ── scanning ─────────────────────────────────────────────────────────────────

def _is_plain_number(x: Any) -> bool:
    return (isinstance(x, (numbers.Real, Decimal))
            and not isinstance(x, bool))


def has_units_material(x: Any) -> bool:
    """True if *x* holds a Quantity or a units-attributed Var anywhere, and
    every leaf is one the side channel speaks for. A foreign leaf (atom,
    string, date, …) returns False so the existing guards own the error."""
    _ensure_imports()
    try:
        return _scan(x)
    except _NotEngaged:
        return False


def _scan(x: Any) -> bool:
    x = deref(x)
    if isinstance(x, _Quantity):
        return True
    if is_var(x):
        return get_attr(x, UNITS_KEY) is not None
    if _is_plain_number(x):
        return False
    if isinstance(x, _BINARY):
        left = _scan(x.left)
        right = _scan(x.right)
        return left or right
    if isinstance(x, _Negate):
        return _scan(x.operand)
    raise _NotEngaged()


# ── analysis ─────────────────────────────────────────────────────────────────

class _Analysis:
    """One comparison's dimension inference.

    ``env`` maps ``var._id`` to a dims dict once known. Vars are known from
    a ``units`` attribute, or are dimensionless when they already carry
    solver state (they are bare numbers to the solver), or are unknown and
    inferred. Numbers are dimensionless. ``_known`` walks bottom-up and
    returns None for "not yet"; ``_push`` walks top-down with a required
    dims and assigns unknown vars. The two alternate to a fixpoint.
    """

    def __init__(self, context: str) -> None:
        self.context = context
        self.env: dict[int, dict] = {}
        self.vars: dict[int, Any] = {}
        self.unknown_order: list[int] = []

    # leaves ---------------------------------------------------------------
    def _var_dims(self, v) -> dict | None:
        vid = v._id
        if vid in self.env:
            return self.env[vid]
        if vid not in self.vars:
            self.vars[vid] = v
            state = get_attr(v, UNITS_KEY)
            if state is not None:
                self.env[vid] = dict(state.dims)
            elif _has_solver_state(v):
                self.env[vid] = {}
            else:
                self.unknown_order.append(vid)
        return self.env.get(vid)

    def _assign(self, v, dims: dict) -> None:
        self.env[v._id] = dict(dims)

    # bottom-up ------------------------------------------------------------
    def _known(self, x: Any) -> dict | None:
        x = deref(x)
        if isinstance(x, _Quantity):
            return dict(x.dims)
        if is_var(x):
            return self._var_dims(x)
        if _is_plain_number(x):
            return {}
        if isinstance(x, (_Add, _Sub, _Mod)):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None and r is not None:
                if l != r:
                    raise _mismatch(self.context, l, r, type(x).__name__)
                return l
            return l if l is not None else r
        if isinstance(x, _FloorDiv):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None and r is not None and l != r:
                raise _mismatch(self.context, l, r, "FloorDiv")
            return {}
        if isinstance(x, _Mult):
            l, r = self._known(x.left), self._known(x.right)
            return _merge(l, r, +1) if l is not None and r is not None else None
        if isinstance(x, _Div):
            l, r = self._known(x.left), self._known(x.right)
            return _merge(l, r, -1) if l is not None and r is not None else None
        if isinstance(x, _Pow):
            n = self._exponent(x)
            base = self._known(x.left)
            return _scale(base, n) if base is not None else None
        if isinstance(x, _Negate):
            return self._known(x.operand)
        raise _NotEngaged()

    def _exponent(self, x) -> int:
        e = deref(x.right)
        if isinstance(e, _Quantity):
            if e.dims:
                raise _mismatch(self.context, dict(e.dims), {}, "exponent")
            e = e.value
        if isinstance(e, bool) or not isinstance(e, int):
            raise _mismatch(self.context, {}, {}, f"exponent must be a ground int, got {e!r}")
        return e

    # top-down -------------------------------------------------------------
    def _push(self, x: Any, want: dict) -> None:
        x = deref(x)
        if isinstance(x, _Quantity):
            if dict(x.dims) != want:
                raise _mismatch(self.context, dict(x.dims), want)
            return
        if is_var(x):
            have = self._var_dims(x)
            if have is None:
                self._assign(x, want)
            elif have != want:
                raise _mismatch(self.context, have, want)
            return
        if _is_plain_number(x):
            if want:
                raise _mismatch(self.context, {}, want, "plain number")
            return
        if isinstance(x, (_Add, _Sub, _Mod)):
            self._push(x.left, want)
            self._push(x.right, want)
            return
        if isinstance(x, _FloorDiv):
            if want:
                raise _mismatch(self.context, {}, want, "FloorDiv")
            l, r = self._known(x.left), self._known(x.right)
            if l is not None:
                self._push(x.right, l)
            elif r is not None:
                self._push(x.left, r)
            return
        if isinstance(x, _Mult):
            l, r = self._known(x.left), self._known(x.right)
            if l is not None:
                self._push(x.right, _merge(want, l, -1))
            if r is not None:
                self._push(x.left, _merge(want, r, -1))
            return
        if isinstance(x, _Div):
            l, r = self._known(x.left), self._known(x.right)
            if r is not None:
                self._push(x.left, _merge(want, r, +1))
            if l is not None:
                self._push(x.right, _merge(l, want, -1))
            return
        if isinstance(x, _Pow):
            n = self._exponent(x)
            base = _unscale(want, n)
            if base is None:
                raise _mismatch(self.context, want, {}, f"not a {n}th power")
            self._push(x.left, base)
            return
        if isinstance(x, _Negate):
            self._push(x.operand, want)
            return
        raise _NotEngaged()

    # driver ---------------------------------------------------------------
    def _fixpoint(self, l, r) -> None:
        while True:
            before = len(self.env)
            dl, dr = self._known(l), self._known(r)
            if dl is not None:
                self._push(l, dl)
                self._push(r, dl)
            if dr is not None:
                self._push(r, dr)
                self._push(l, dr)
            if len(self.env) == before:
                return

    def _default_one_factor(self, x: Any) -> bool:
        """Default the single unknown bare-var factor of a Mult/Div whose
        result is unknown to dimensionless. Returns True if one was found."""
        x = deref(x)
        if isinstance(x, (_Mult, _Div)):
            l, r = deref(x.left), deref(x.right)
            kl, kr = self._known(l), self._known(r)
            if kl is None and kr is not None and is_var(l):
                self._assign(l, {})
                return True
            if kr is None and kl is not None and is_var(r):
                self._assign(r, {})
                return True
            return self._default_one_factor(l) or self._default_one_factor(r)
        if isinstance(x, _BINARY):
            return self._default_one_factor(x.left) or self._default_one_factor(x.right)
        if isinstance(x, _Negate):
            return self._default_one_factor(x.operand)
        return False

    def run(self, l, r) -> tuple[dict, dict]:
        self._fixpoint(l, r)
        while any(vid not in self.env for vid in self.unknown_order):
            if not (self._default_one_factor(l) or self._default_one_factor(r)):
                missing = [self.vars[v] for v in self.unknown_order if v not in self.env]
                raise _undetermined(self.context, missing)
            self._fixpoint(l, r)
        dl, dr = self._known(l), self._known(r)
        self._push(l, dl)
        self._push(r, dr)
        if dl != dr:
            raise _mismatch(self.context, dl, dr)
        return dl, dr


def _has_solver_state(v) -> bool:
    return (get_attr(v, "fd") is not None or get_attr(v, "clpq") is not None
            or get_attr(v, "real") is not None)


def analyse(l: Any, r: Any, context: str) -> tuple[dict, dict, dict[int, dict]]:
    """Dimensions of both sides and of every Var leaf; raises the ISO term."""
    _ensure_imports()
    a = _Analysis(context)
    dl, dr = a.run(l, r)
    return dl, dr, a.env


def ground_dims(tree: Any) -> dict:
    """Dims of a fully ground tree — the positive-control entry point."""
    _ensure_imports()
    a = _Analysis("ground")
    d = a._known(tree)
    a._push(tree, d)
    return d
```

Add to `clausal/logic/units_constraint.py` (before the hook), so both modules share one spelling:

```python
def to_solver_number(v):
    """The bare number a solver receives for a Quantity value: a Decimal is
    an exact rational spelled in decimal notation, so it becomes a Fraction
    (exact at every scale); an integral rational presents as int, as
    everywhere in the engine; int/float/Fraction pass through."""
    from fractions import Fraction  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415
    from clausal.logic.variables import present_number  # noqa: PLC0415
    if isinstance(v, Decimal):
        return present_number(Fraction(v))
    if type(v) is Fraction:
        return present_number(v)
    return v
```

Note the attribute keys `"fd"`, `"clpq"`, `"real"` are `FD_KEY`, `Q_KEY`, `REAL_KEY` in their modules; they are spelled literally here to keep the module free of solver imports. Task 5's tests pin that the spellings agree.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q`
Expected: all passed. If the positive control finds a disagreement, the rule table is wrong, not the oracle — fix `_known`/`_push`.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/units_clp.py clausal/logic/units_constraint.py tests/test_units_clp.py
git commit -m "feat(units): dimension analysis for CLP comparisons, checked against Quantity arithmetic"
```

---

### Task 4: Shadows and the two-way link

**Files:**
- Modify: `clausal/logic/units_constraint.py` (`UnitState`, `_units_hook`)
- Modify: `clausal/logic/units_clp.py` (append `shadow_for`, `Link`, `_link_hook`, `strip`)
- Test: `tests/test_units_clp.py`

**Interfaces:**
- Produces:
  - `UnitState(dims, shadow=None)`; `.shadow` slot; equality still by dims.
  - `units_clp.shadow_for(var, dims, trail) -> Var` — creates or returns the shadow.
  - `units_clp.strip(tree, env, trail) -> tree'` — rebuilds with solver numbers and shadows.
  - `units_clp.Link(user, dims)` under attribute key `units_link` on the shadow.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_units_clp.py`:

```python
from clausal.logic.units_constraint import UNITS_KEY, UnitState


class TestShadowLink:
    def test_shadow_created_once_and_trailed(self):
        from clausal.logic.units_clp import shadow_for, LINK_KEY
        t = Trail()
        x = Var()
        mark = t.mark()
        s = shadow_for(x, M, t)
        assert shadow_for(x, M, t) is s
        assert get_attr(x, UNITS_KEY).shadow is s
        assert get_attr(s, LINK_KEY).user is x
        t.undo(mark)
        assert get_attr(x, UNITS_KEY) is None and get_attr(s, LINK_KEY) is None

    def test_binding_shadow_binds_user_to_quantity(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        assert unify(s, 5, t)
        assert deref(x) == Quantity(5, M)

    def test_binding_shadow_to_fraction_gives_exact_currency(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, {euro: 1}, t)
        assert unify(s, Fraction(1, 3), t)
        v = deref(x)
        assert v.dims == {euro: 1} and type(v.value) is Fraction and v.value == Fraction(1, 3)

    def test_binding_user_to_quantity_binds_shadow(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, {euro: 1}, t)
        assert unify(x, Quantity(Decimal("1550.00"), {euro: 1}), t)
        assert deref(s) == 1550 and type(deref(s)) is int

    def test_binding_user_to_wrong_dims_fails_whole_unification(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        assert not unify(x, Quantity(5, S), t)
        assert is_var_unbound(x) and is_var_unbound(s)

    def test_two_united_vars_unify_merges_shadows(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x, y = Var(), Var()
        sx, sy = shadow_for(x, M, t), shadow_for(y, M, t)
        assert unify(x, y, t)
        assert unify(sx, 7, t)
        assert deref(y) == Quantity(7, M) and deref(sy) == 7

    def test_shadow_bound_to_foreign_var_transfers_link(self):
        from clausal.logic.units_clp import shadow_for, LINK_KEY
        t = Trail()
        x, w = Var(), Var()
        s = shadow_for(x, M, t)
        assert unify(s, w, t)
        assert get_attr(w, LINK_KEY).user is x
        assert unify(w, 9, t)
        assert deref(x) == Quantity(9, M)

    def test_strip_replaces_quantities_and_united_vars(self):
        from clausal.logic.units_clp import analyse, strip
        t = Trail()
        x = Var()
        tree = Sub(Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("0.01"), {euro: 1}))
        _, _, env = analyse(x, tree, "(==)/2")
        l2, r2 = strip(x, env, t), strip(tree, env, t)
        assert get_attr(x, UNITS_KEY).shadow is l2
        assert isinstance(r2, Sub) and r2.left == 1550 and type(r2.left) is int
        assert r2.right == Fraction(1, 100) and type(r2.right) is Fraction

    def test_backtracking_undoes_shadow_binding(self):
        from clausal.logic.units_clp import shadow_for
        t = Trail()
        x = Var()
        s = shadow_for(x, M, t)
        mark = t.mark()
        assert unify(s, 5, t)
        t.undo(mark)
        assert is_var_unbound(x) and is_var_unbound(s)


def is_var_unbound(v):
    from clausal.logic.variables import is_var
    return is_var(deref(v))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k ShadowLink`
Expected: FAIL with `ImportError: cannot import name 'shadow_for'`

- [ ] **Step 3: Implement**

In `clausal/logic/units_constraint.py`, replace `UnitState` and `_units_hook`:

```python
class UnitState:
    """Dimensional constraint for an unbound variable.

    Immutable for trail safety — constrain_var_dims always creates a new
    instance rather than mutating an existing one. ``shadow`` is the bare
    variable a CLP solver sees in this variable's place (see
    ``clausal.logic.units_clp``); None until the variable first takes part
    in a constraint. Equality is by dims only: two states with the same
    dims are the same constraint whether or not a shadow exists yet.
    """

    __slots__ = ("dims", "shadow")

    def __init__(self, dims: dict, shadow=None) -> None:
        self.dims = {k: v for k, v in dims.items() if v != 0}
        self.shadow = shadow

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UnitState) and self.dims == other.dims

    def __repr__(self) -> str:
        return f"UnitState({self.dims!r})"


def _units_hook(attr_value: UnitState, bound_to, trail: Trail) -> bool:
    """Called when an AttVar with a ``"units"`` attribute is unified.

    *attr_value* — the UnitState carried by the variable being bound.
    *bound_to*   — the value (or variable) the AttVar was unified with.

    With a shadow present, a Quantity binding is forwarded to the shadow
    through the CLP dispatch (``fd_eq``, not ``unify``, so an FD shadow
    meeting a rational is promoted exactly as a plain var would be), and
    two united variables unifying equate their shadows the same way.
    """
    # Import here to avoid circular imports at module load time.
    from clausal.terms import Quantity

    bound_to = deref(bound_to)

    if isinstance(bound_to, Quantity):
        # Binding to a ground measurement — check dimensions match.
        if bound_to.dims != attr_value.dims:
            return False
        if attr_value.shadow is not None:
            from clausal.logic.clpfd import fd_eq  # noqa: PLC0415  (module-level: C wrapper when loaded)
            return fd_eq(attr_value.shadow, to_solver_number(bound_to.value), trail)
        return True

    if is_var(bound_to):
        # Unified with another variable — transfer or check constraint.
        other = get_attr(bound_to, UNITS_KEY)
        if other is None:
            put_attr(bound_to, UNITS_KEY, attr_value, trail)
            return True
        # Both constrained — dims must be identical (no intersection for units).
        if other.dims != attr_value.dims:
            return False
        if attr_value.shadow is not None and other.shadow is not None:
            if attr_value.shadow is other.shadow:
                return True
            from clausal.logic.clpfd import fd_eq  # noqa: PLC0415
            return fd_eq(attr_value.shadow, other.shadow, trail)
        if attr_value.shadow is not None:
            put_attr(bound_to, UNITS_KEY, attr_value, trail)   # inherit the shadow
        return True

    if isinstance(bound_to, (int, float)) and not isinstance(bound_to, bool):
        # Plain number allowed only for a dimensionless constraint.
        return not attr_value.dims

    return False
```

Append to `clausal/logic/units_clp.py`:

```python
# ── shadows ──────────────────────────────────────────────────────────────────

class Link:
    """What a shadow knows: the user's variable and the dims to reattach."""
    __slots__ = ("user", "dims")

    def __init__(self, user, dims: dict) -> None:
        self.user = user
        self.dims = dict(dims)

    def __repr__(self) -> str:
        return f"Link({self.user!r}, {self.dims!r})"


def shadow_for(var, dims: dict, trail: Trail):
    """The bare variable the solver sees for united *var*; created (and
    trailed) on first use."""
    state = get_attr(var, UNITS_KEY)
    if state is not None and state.shadow is not None:
        return state.shadow
    shadow = Var()
    put_attr(var, UNITS_KEY, UnitState(dims, shadow=shadow), trail)
    put_attr(shadow, LINK_KEY, Link(var, dims), trail)
    return shadow


def _link_hook(link: Link, bound_to, trail: Trail) -> bool:
    """The shadow was bound. A number reattaches the dims onto the user's
    variable — exactly as the solver produced it, through ``present_number``,
    never converted to Decimal; another variable inherits the link, or is
    equated with the other link's user."""
    _ensure_imports()
    bound_to = deref(bound_to)
    if is_var(bound_to):
        other = get_attr(bound_to, LINK_KEY)
        if other is None:
            put_attr(bound_to, LINK_KEY, link, trail)
            return True
        if other.user is link.user:
            return True
        return unify(link.user, other.user, trail)
    if not _is_plain_number(bound_to):
        return False
    value = present_number(bound_to)
    user = deref(link.user)
    if is_var(user):
        return unify(user, _Quantity(value, link.dims), trail)
    return isinstance(user, _Quantity) and dict(user.dims) == link.dims and user.value == value


register_attr_hook(LINK_KEY, _link_hook)


# ── strip ────────────────────────────────────────────────────────────────────

def strip(x: Any, env: dict[int, dict], trail: Trail) -> Any:
    """Rebuild *x* with every Quantity replaced by its solver number and every
    united Var (non-empty dims in *env*) replaced by its shadow. A Var whose
    dims are empty is a bare number already and stays itself."""
    _ensure_imports()
    x = deref(x)
    if isinstance(x, _Quantity):
        return to_solver_number(x.value)
    if is_var(x):
        dims = env.get(x._id, {})
        return shadow_for(x, dims, trail) if dims else x
    if isinstance(x, _BINARY):
        return type(x)(strip(x.left, env, trail), strip(x.right, env, trail))
    if isinstance(x, _Negate):
        return type(x)(strip(x.operand, env, trail))
    return x
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py tests/test_units.py -q`
Expected: all passed (the `test_units.py` AttVar tests pin the unchanged hook behaviour)

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/units_clp.py clausal/logic/units_constraint.py tests/test_units_clp.py
git commit -m "feat(units): shadow variables couple a united var to the bare var a solver sees"
```

---

### Task 5: Wire the comparators

**Files:**
- Modify: `clausal/logic/clpfd.py` — Python `fd_eq` (≈1885), `fd_ne` (≈1954), `fd_lt` (≈1989), `fd_le` (≈2030) and the four C wrappers (≈3304-3355)
- Modify: `clausal/logic/units_clp.py` (append `strip_for_solver`)
- Modify: `clausal/logic/builtins/__init__.py:72` (import `units_clp` for its hook registration)
- Test: `tests/test_units_clp.py`

**Interfaces:**
- Produces: `strip_for_solver(l, r, context, trail) -> tuple | None` — `None` when not engaged; otherwise `(l', r')` with no Quantity and no united Var.
- Consumes: `analyse`, `strip`, `has_units_material` from Tasks 3–4.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_units_clp.py`:

```python
class TestComparatorsEngine:
    """Through the module-level fd_* (the C wrappers when loaded)."""

    def _fd(self):
        import clausal.logic.clpfd as clpfd
        return clpfd

    def test_eq_var_against_quantity_binds(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, Quantity(5, M), t)
        assert deref(x) == Quantity(5, M)

    def test_money_subtraction_binds_exact_euro(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        tree = Sub(Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("50.00"), {euro: 1}))
        assert clpfd.fd_eq(x, tree, t)
        v = deref(x)
        assert v == Quantity(Decimal("1500.00"), {euro: 1})
        assert not isinstance(v.value, float)

    def test_money_division_by_three_is_exact_fraction(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, Div(Quantity(Decimal("1000"), {yen: 1}), 3), t)
        v = deref(x)
        assert type(v.value) is Fraction and v.value == Fraction(1000, 3)

    def test_lt_then_bind(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_lt(x, Quantity(Decimal("1550.00"), {euro: 1}), t)
        assert unify(x, Quantity(Decimal("3.00"), {euro: 1}), t)
        assert not unify(Var(), None, t) or True     # keep the trail alive
        t2, y = Trail(), Var()
        assert clpfd.fd_lt(y, Quantity(Decimal("1550.00"), {euro: 1}), t2)
        assert not unify(y, Quantity(Decimal("2000.00"), {euro: 1}), t2)

    def test_ne_then_bind(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_ne(x, Quantity(3, M), t)
        assert not unify(x, Quantity(3, M), t)
        assert unify(x, Quantity(4, M), t)

    def test_mixed_currencies_throw_before_any_solver_runs(self):
        clpfd = self._fd()
        from clausal.modules.countries.united_states import usd
        t, x = Trail(), Var()
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(x, Add(Quantity(Decimal("1.00"), {euro: 1}), Quantity(Decimal("1.00"), {usd: 1})), t)
        _assert_system_error(ei, "units_mismatch")
        assert get_attr(x, UNITS_KEY) is None      # nothing was posted

    def test_metre_minus_second_throws(self):
        clpfd = self._fd()
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(Var(), Sub(Quantity(3, M), Quantity(2, S)), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_ground_both_sides(self):
        clpfd = self._fd()
        t = Trail()
        assert clpfd.fd_eq(Sub(Quantity(Decimal("1550.00"), {euro: 1}), Quantity(Decimal("50.00"), {euro: 1})),
                           Quantity(Decimal("1500.00"), {euro: 1}), t)
        assert not clpfd.fd_lt(Quantity(5, M), Quantity(3, M), t)

    def test_declared_var_then_constraint(self):
        clpfd = self._fd()
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        assert clpfd.fd_eq(x, Add(Quantity(3, M), Quantity(1, M)), t)
        assert deref(x) == Quantity(4, M)

    def test_inferred_var_in_sub_then_bind_other(self):
        clpfd = self._fd()
        t, x, y = Trail(), Var(), Var()
        assert clpfd.fd_eq(x, Sub(Quantity(Decimal("1550.00"), {euro: 1}), y), t)
        assert unify(y, Quantity(Decimal("50.00"), {euro: 1}), t)
        assert deref(x) == Quantity(Decimal("1500.00"), {euro: 1})

    def test_dimensionless_result_is_plain_number(self):
        clpfd = self._fd()
        t, r = Trail(), Var()
        assert clpfd.fd_eq(r, Div(Quantity(6, M), Quantity(3, M)), t)
        assert deref(r) == 2 and not isinstance(deref(r), Quantity)

    def test_units_var_against_atom_keeps_existing_type_error(self):
        clpfd = self._fd()
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, M, t)
        with pytest.raises(LogicException) as ei:
            clpfd.fd_eq(x, mint("banana"), t)
        assert ei.value.term.args[0].functor == "type_error"

    def test_plain_constraints_untouched(self):
        clpfd = self._fd()
        t, x = Trail(), Var()
        assert clpfd.fd_eq(x, Add(2, 3), t)
        assert deref(x) == 5 and get_attr(x, UNITS_KEY) is None

    def test_attr_key_spellings_agree(self):
        from clausal.logic.clpfd import FD_KEY
        from clausal.logic.clpq import Q_KEY
        from clausal.logic.clpr import REAL_KEY
        assert (FD_KEY, Q_KEY, REAL_KEY) == ("fd", "clpq", "real")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k ComparatorsEngine`
Expected: FAIL — `LogicException ... type_error(evaluable|integer, Quantity(...))`

- [ ] **Step 3: Implement**

Append to `clausal/logic/units_clp.py`:

```python
# ── entry point for solver front ends ───────────────────────────────────────

def strip_for_solver(l: Any, r: Any, context: str, trail: Trail):
    """The side channel, in one call, for a comparison ``l <op> r``.

    Returns None when neither side holds a Quantity or a united Var (the
    caller's existing path is untouched), or when a leaf is something the
    side channel does not speak for (the caller's guards own that error).
    Otherwise runs the dimension analysis — throwing the ISO term on
    disagreement — and returns ``(l', r')`` holding only bare numbers, bare
    Vars and shadows.
    """
    _ensure_imports()
    l, r = deref(l), deref(r)
    try:
        if not (_scan(l) or _scan(r)):
            return None
        _, _, env = analyse(l, r, context)
    except _NotEngaged:
        return None
    return strip(l, env, trail), strip(r, env, trail)
```

In `clausal/logic/clpfd.py`, next to `_ensure_exc_imports`:

```python
_strip_for_solver = None


def _units_strip(l, r, context, trail):
    """The units side channel (clausal.logic.units_clp): None when no
    Quantity / united Var is involved, else the stripped (l, r)."""
    global _strip_for_solver
    if _strip_for_solver is None:
        from clausal.logic.units_clp import strip_for_solver  # noqa: PLC0415
        _strip_for_solver = strip_for_solver
    return _strip_for_solver(l, r, context, trail)
```

In each Python comparator, right after the `# ── end fast path ──` line and BEFORE `_resolve` (which raises on a Quantity leaf):

```python
    stripped = _units_strip(l, r, "(==)/2", trail)      # "(!=)/2" / "(<)/2" / "(=<)/2"
    if stripped is not None:
        l, r = stripped
```

In each C wrapper, as the first statement (before the guard), using the deref'd operands:

```python
    def fd_eq(l, r, trail, _c_impl=_c_fd_eq):
        stripped = _units_strip(l, r, "(==)/2", trail)
        if stripped is not None:
            l, r = stripped
        # A12-F002: ...
```

Same for `fd_ne` (`"(!=)/2"`), `fd_lt` (`"(<)/2"`), `fd_le` (`"(=<)/2"`). `fd_gt`/`fd_ge` delegate to `fd_lt`/`fd_le` with swapped operands and need nothing.

In `clausal/logic/builtins/__init__.py` after line 72:

```python
import clausal.logic.units_clp                      # noqa: F401  (registers the units_link hook)
```

- [ ] **Step 4: Run tests to verify they pass, plus the guard and CLP suites**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py tests/test_units.py tests/test_clpq.py tests/test_clpfd.py tests/iso/test_iso_compare_errors.py tests/audit_2026_07_05/test_12_seams.py tests/test_date_time_ordering.py -q`
Expected: everything passes except the tests that pin the old Quantity refusal — measured in execution: FOUR in `test_12_seams.py` (eq operand, ne operand, quantity leaf in a tree, ground quantity tree vs var), `test_date_time_ordering.py::test_var_lt_quantity`, and `test_units.py::test_compare_metre_with_second_raises` (a ground comparison now throws the ISO term instead of the Python class). They flip in the same commit. The `clpsat`/`clportools` failures are missing optional packages and pre-existing. If `tests/test_clpfd.py` does not exist under that name, run `tests/test_clp*.py`.

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpfd.py clausal/logic/units_clp.py clausal/logic/builtins/__init__.py tests/test_units_clp.py
git commit -m "feat(clp): quantities and united vars take part in CLP comparisons via the units side channel"
```

---

### Task 6: `in_domain/3` and `label/1` on united variables

**Files:**
- Modify: `clausal/logic/clpfd.py` — `in_domain` (≈2182), `label` (≈2236)
- Modify: `clausal/logic/units_clp.py` (append `in_domain_units`, `label_targets`)
- Test: `tests/test_units_clp.py`

**Interfaces:**
- Produces:
  - `in_domain_units(var_or_list, lo, hi, trail) -> bool | None` — `None` when neither bound is a Quantity; else posts the stripped bounds on the shadows (`clpfd.in_domain` for ints, `clpq.in_q` otherwise) and returns the result.
  - `label_targets(vars_list) -> list` — the same list with every united var replaced by its shadow.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_units_clp.py`:

```python
class TestDomainAndLabel:
    def test_in_domain_with_money_bounds_then_label(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], Quantity(Decimal("1"), {yen: 1}), Quantity(Decimal("3"), {yen: 1}), t)
        seen = []
        for _ in clpfd.label([x], t):
            seen.append(deref(x))
        assert seen == [Quantity(1, {yen: 1}), Quantity(2, {yen: 1}), Quantity(3, {yen: 1})]
        assert all(not isinstance(q.value, float) for q in seen)

    def test_in_domain_with_metre_bounds_and_constraint(self):
        import clausal.logic.clpfd as clpfd
        t, w, h = Trail(), Var(), Var()
        assert clpfd.in_domain([w, h], Quantity(1, M), Quantity(6, M), t)
        area = Var()
        assert clpfd.fd_eq(area, Mult(w, h), t)
        assert clpfd.fd_eq(area, Quantity(12, {metre: 2}), t)
        assert clpfd.fd_eq(w, Quantity(3, M), t)
        for _ in clpfd.label([w, h], t):
            assert deref(h) == Quantity(4, M)
            break
        else:
            pytest.fail("no solution")

    def test_in_domain_plain_bound_beside_quantity_bound_throws(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], 1, Quantity(3, M), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_in_domain_bounds_disagreeing_throws(self):
        import clausal.logic.clpfd as clpfd
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([Var()], Quantity(1, M), Quantity(3, S), Trail())
        _assert_system_error(ei, "units_mismatch")

    def test_in_domain_on_declared_var_with_other_dims_throws(self):
        import clausal.logic.clpfd as clpfd
        from clausal.logic.units_constraint import constrain_var_dims
        t, x = Trail(), Var()
        assert constrain_var_dims(x, S, t)
        with pytest.raises(LogicException) as ei:
            clpfd.in_domain([x], Quantity(1, M), Quantity(3, M), t)
        _assert_system_error(ei, "units_mismatch")

    def test_plain_in_domain_and_label_untouched(self):
        import clausal.logic.clpfd as clpfd
        t, x = Trail(), Var()
        assert clpfd.in_domain([x], 1, 2, t)
        assert [deref(x) for _ in clpfd.label([x], t)] == [1, 2]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k DomainAndLabel`
Expected: FAIL — `TypeError: in_domain bounds must be integers`

- [ ] **Step 3: Implement**

Append to `clausal/logic/units_clp.py`:

```python
# ── in_domain / label ────────────────────────────────────────────────────────

def in_domain_units(var_or_list, lo, hi, trail: Trail):
    """``in_domain/3`` with quantity bounds. None when neither bound is a
    Quantity (the caller's plain path). Both bounds must be quantities of
    one dimension; every target becomes a united var of that dimension
    (a target already declared with other dims throws) and the stripped
    bounds are posted on its shadow — ``in_domain`` for integer bounds,
    ``in_q`` otherwise, so money bounds take the exact rational route."""
    _ensure_imports()
    lo, hi = deref(lo), deref(hi)
    lo_q, hi_q = isinstance(lo, _Quantity), isinstance(hi, _Quantity)
    if not (lo_q or hi_q):
        return None
    ctx = "in_domain/3"
    if not (lo_q and hi_q):
        q, plain = (lo, hi) if lo_q else (hi, lo)
        raise _mismatch(ctx, dict(q.dims), {}, f"bound {plain!r}")
    if dict(lo.dims) != dict(hi.dims):
        raise _mismatch(ctx, dict(lo.dims), dict(hi.dims))
    dims = dict(lo.dims)
    targets = deref(var_or_list)
    if not isinstance(targets, list):
        targets = [targets]
    shadows = []
    for v in targets:
        v = deref(v)
        if isinstance(v, _Quantity):
            if dict(v.dims) != dims:
                raise _mismatch(ctx, dict(v.dims), dims)
            shadows.append(to_solver_number(v.value))
            continue
        if not is_var(v):
            raise _mismatch(ctx, {}, dims, f"target {v!r}")
        state = get_attr(v, UNITS_KEY)
        if state is not None and state.dims != dims:
            raise _mismatch(ctx, state.dims, dims)
        if state is None and _has_solver_state(v):
            raise _mismatch(ctx, {}, dims, f"target {v!r} is already a bare solver variable")
        shadows.append(shadow_for(v, dims, trail))
    lo_n, hi_n = to_solver_number(lo.value), to_solver_number(hi.value)
    if type(lo_n) is int and type(hi_n) is int:
        from clausal.logic.clpfd import in_domain  # noqa: PLC0415
        return in_domain(shadows, lo_n, hi_n, trail)
    from clausal.logic.clpq import in_q  # noqa: PLC0415
    return in_q(shadows, lo_n, hi_n, trail)


def label_targets(vars_list) -> list:
    """``label/1``'s list with every united var replaced by its shadow. A
    united var with no shadow yet has no domain and is left alone (label
    skips it, as it skips any var without FD state)."""
    out = []
    for v in vars_list:
        dv = deref(v)
        if is_var(dv):
            state = get_attr(dv, UNITS_KEY)
            if state is not None and state.shadow is not None:
                out.append(state.shadow)
                continue
        out.append(v)
    return out
```

In `clausal/logic/clpfd.py`, at the top of `in_domain` (before the integer check):

```python
    from clausal.logic.units_clp import in_domain_units  # noqa: PLC0415
    united = in_domain_units(var_or_list, lo, hi, trail)
    if united is not None:
        return united
```

In `label`, after `vars_list` is normalised to a list:

```python
    from clausal.logic.units_clp import label_targets  # noqa: PLC0415
    vars_list = label_targets(vars_list)
```

Then verify the recursion `yield from label(vars_list, trail)` passes the already-substituted list (it does; substitution is idempotent on shadows).

- [ ] **Step 4: Run tests to verify they pass**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py tests/test_clp*.py -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add clausal/logic/clpfd.py clausal/logic/units_clp.py tests/test_units_clp.py
git commit -m "feat(clp): in_domain/3 and label/1 accept quantity bounds and united variables"
```

---

### Task 7: Surface-language acceptance fixture and the two flipped tests

**Files:**
- Create: `tests/fixtures/units_clp_side_channel.seam`
- Modify: `tests/audit_2026_07_05/test_12_seams.py:271-277`, `tests/test_date_time_ordering.py:197-202`
- Test: `tests/test_units_clp.py`

- [ ] **Step 1: Write the fixture and the runner test**

`tests/fixtures/units_clp_side_channel.seam`:

```
-import_from(py.units, [metre, second, ampere, volt, ohm, watt, dimensionless, strip_units])
-import_from(european_union, [euro])
-import_from(united_states, [usd])
-import_from(japan, [yen])
-import_from(kuwait, [kwd])
-import_from(currency, [money_round])

# Units inside CLP comparisons: dimensional analysis runs first in a side
# channel, the solvers see bare numbers, units are reattached on binding.
# `#=` opens a comment on this surface, so the infix spellings are used;
# they reach the same functions.

# ── money ────────────────────────────────────────────────────────────────

test("money comparison") <- (
    X == 3.00(euro),
    X < 1550.00(euro)
)  # nv

test("money subtraction binds the result with its unit") <- (
    X == 1550.00(euro) - 50.00(euro),
    X == 1500.00(euro)
)  # nv

test("money subtraction with an inferred operand") <- (
    X == 1550.00(euro) - Y,
    Y == 50.00(euro),
    X == 1500.00(euro)
)  # nv

test("mixed currencies throw the ISO units_mismatch term") <- (
    catch(
        (_ == 1.00(euro) + 1.00(usd)),
        error(system_error(CODE), _),
        CODE is 'units_mismatch',
    )
)  # nv

test("a third of 1000 yen is exact and the caller rounds") <- (
    X == 1000(yen) / 3,
    money_round(X, 'half_even', R),   # strict atoms: quote the mode
    R == 333(yen)
)  # nv

test("a third of one dinar keeps three places after explicit rounding") <- (
    X == 1.000(kwd) / 3,
    money_round(X, 'half_up', R),
    R == 0.333(kwd)
)  # nv

test("money bounds with in_domain and label") <- (
    in_domain([X], 1(yen), 3(yen)),
    findall(X, label([X]), XS),
    XS == [1(yen), 2(yen), 3(yen)]
)  # nv

# ── SI electrical ────────────────────────────────────────────────────────

test("ohm's law: V = I * R infers volt") <- (
    V == 2(ampere) * 3(ohm),
    has_units(V, volt),
    V == 6(volt)
)  # nv

test("ohm's law solved for the current") <- (
    12(volt) == I * 4(ohm),
    I == 3(ampere)
)  # nv

test("power P = V * I") <- (
    P == 12(volt) * 2(ampere),
    has_units(P, watt),
    strip_units(P, 24)
)  # nv

test("power loss P = I^2 * R") <- (
    I == 3(ampere),
    P == I * I * 5(ohm),
    P == 45(watt)
)  # nv

test("power P = V^2 / R") <- (
    P == 12(volt) ** 2 / 4(ohm),
    P == 36(watt)
)  # nv

test("resistance from integer domain") <- (
    in_domain([R], 1(ohm), 10(ohm)),
    12(volt) == 3(ampere) * R,
    label([R]),
    R == 4(ohm)
)  # nv

# ── dimensional rules ────────────────────────────────────────────────────

test("metre minus second throws") <- (
    catch(
        (_ == 3(metre) - 2(second)),
        error(system_error(CODE), _),
        CODE is 'units_mismatch',
    )
)  # nv

test("plain number beside a length in a sum throws") <- (
    catch(
        (_ == 3(metre) + 1),
        error(system_error(CODE), _),
        CODE is 'units_mismatch',
    )
)  # nv

test("two unknown factors are undetermined") <- (
    has_units(X, metre),
    catch(
        (X == Y * Z),
        error(system_error(CODE), _),
        CODE is 'units_undetermined',
    )
)  # nv

test("dimensionless ratio is a plain number") <- (
    R == 6(metre) / 3(metre),
    R == 2
)  # nv

test("disequality on quantities") <- (
    X != 3(metre),
    X == 4(metre)
)  # nv

test("declared unit variable then constrained") <- (
    has_units(X, metre),
    X == 3(metre) + 1(metre),
    X == 4(metre)
)  # nv

test("backtracking undoes a unit binding") <- (
    findall(X, (in_(N, [1, 2]), X == N * 1(metre)), XS),
    XS == [1(metre), 2(metre)]
)  # nv
```

Append to `tests/test_units_clp.py`:

```python
import os


class TestSurfaceFixture:
    def test_fixture_passes_every_test_clause(self):
        from clausal.testing import run_file
        path = os.path.join(os.path.dirname(__file__), "fixtures", "units_clp_side_channel.seam")
        results = run_file(path)
        failed = [(r.name, r.error) for r in results.results if not r.passed]
        assert not failed, failed
        assert len(results.results) >= 20      # the runner actually collected the clauses
```

Flip the two pinned tests. In `tests/audit_2026_07_05/test_12_seams.py` replace `test_eq_quantity_operand_raises_catchable_type_error` with:

```python
    def test_eq_quantity_operand_binds_via_units_side_channel(self):
        # 2026-09-12: a Quantity is numeric to the comparators now (spec
        # docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md);
        # the broken-FD-var defect this test pinned cannot recur because the
        # solver never sees the Quantity.
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        from clausal.logic.variables import deref
        v, t = Var(), Trail()
        assert fd_eq(v, Quantity(5, {metre: 1}), t)
        assert deref(v) == Quantity(5, {metre: 1})
```

In `tests/test_date_time_ordering.py` replace `test_var_lt_quantity` with:

```python
    def test_var_lt_quantity(self):
        # 2026-09-12: quantities order through the units side channel now.
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        from clausal.logic.variables import unify, deref
        v, t = Var(), Trail()
        assert fd_lt(v, Quantity(5, {metre: 1}), t)
        assert unify(v, Quantity(3, {metre: 1}), t)
        assert deref(v) == Quantity(3, {metre: 1})
```

- [ ] **Step 2: Run the fixture test to see which clauses fail**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/test_units_clp.py -q -k SurfaceFixture`
Expected: it may PASS outright; if a clause fails, the failure list names it. Likely culprits and their fixes: (a) `1000(yen) / 3` — the surface `n(Unit)` sugar and `/` reach `fd_eq` as `Div(Quantity, 3)`; if the sugar is folded before the comparison as `eval_`, the test still holds; (b) `'units_mismatch'` atom identity — `CODE is 'units_mismatch'` compares the minted atom with the quoted atom; if it fails, spell it `CODE == 'units_mismatch'` as `tests/fixtures/dict_set_patterns.seam:182-186` does with `TY is 'dict'`; (c) `findall` over `label` — if unavailable, replace with three explicit `label` solutions via `not (label([X]), X != 1(yen), X != 2(yen), X != 3(yen))`.

- [ ] **Step 3: Run the flipped tests**

Run: `/workspace/clausal/venv/bin/python -m pytest tests/audit_2026_07_05/test_12_seams.py tests/test_date_time_ordering.py -q`
Expected: all passed

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/units_clp_side_channel.seam tests/test_units_clp.py tests/audit_2026_07_05/test_12_seams.py tests/test_date_time_ordering.py
git commit -m "test(units): surface acceptance for units inside CLP; flip the two tests that pinned the refusal"
```

---

### Task 8: Suite gate, review, and closing the todo

**Files:**
- Move: `todo/clp-units-side-channel-2026-09-12.md` → `todo/done/`
- Create: `todo/ground-arithmetic-units-mismatch-iso-term-2026-09-12.md`, `todo/clpz3-units-side-channel-second-target-2026-09-12.md`

- [ ] **Step 1: Regenerate the baseline in the SAME tree and diff failure sets**

Follow memory `running-tests-in-bug-fix-clone` exactly: stash-free approach is to check out `64f04898` in a worktree for the baseline. Run:

```bash
git worktree add /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/base 64f04898
cd /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/base && /workspace/clausal/venv/bin/python setup.py build_ext --inplace -q 2>&1 | tail -1
/workspace/clausal/venv/bin/python -m pytest tests -q -x --continue-on-collection-errors -p no:cacheprovider --color=no 2>&1 | grep -E "^(FAILED|ERROR)" | sort > ../base-failures.txt
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest tests -q --continue-on-collection-errors -p no:cacheprovider --color=no 2>&1 | grep -E "^(FAILED|ERROR)" | sort > /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/new-failures.txt
wc -l /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/*-failures.txt
comm -13 /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/base-failures.txt /tmp/claude-1000/-workspace-clausal-bug-fix/ad6921c4-271b-46c4-abfd-99c87a389c6a/scratchpad/new-failures.txt
```

Drop `-x` from the baseline command (it is shown for illustration only; the baseline must run to completion). Expected: both files non-empty (assert this — an empty file means the extraction failed, not that the suite is green), and `comm` prints NO new failures. Remove the worktree afterwards with `git worktree remove --force <path>`.

- [ ] **Step 2: Roborev review of the branch commits**

Run `/workspace/roborev/roborev review HEAD~7..HEAD` per memory `roborev-review-invocation`; fix any real finding (verify each against the code first, per memory `verify-agent-and-review-claims-before-acting`).

- [ ] **Step 3: Close the todo and file the two follow-ups**

```bash
git mv todo/clp-units-side-channel-2026-09-12.md todo/done/clp-units-side-channel-2026-09-12.md
```

Append to the moved file: `**Done 2026-09-12.** Landed on clone main; spec docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md; plan docs/superpowers/plans/2026-09-12-clp-units-side-channel.md.` Stage the destination path explicitly after the append (memory `git-mv-after-append-drops-content`).

`todo/ground-arithmetic-units-mismatch-iso-term-2026-09-12.md`:

```
# Ground arithmetic should throw error(system_error(units_mismatch), Ctx)

**Filed 2026-09-12.** Ruled by the operator after discussion with Markus
Triska: units mismatches are thrown in the ISO 13211 `system_error` shape with
the code `units_mismatch`. The CLP side channel (clausal/logic/units_clp.py)
does this. The ground path — `Quantity.__add__` and friends, reached through
`is/2`, `eval_/2`, `sum_list/2`, `max_/min_`, `divmod_/4` … — still raises the
raw Python `UnitsMismatch`, which `catch/3` cannot select.

Do: translate at the builtin boundary (one helper, applied where
`UnitsMismatch propagates` is documented in clausal/logic/builtins/arithmetic.py)
so the same term is thrown from both paths, with the same context text
(`_render_pair` in units_clp is the spelling). Keep the Python class as the
internal signal. Pin the term in a fixture next to
tests/fixtures/units_clp_side_channel.seam.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.
```

`todo/clpz3-units-side-channel-second-target-2026-09-12.md`:

```
# CLP(Z3): second target for the units side channel

**Filed 2026-09-12.** Operator's suggestion: the Z3 wrapper is an opaque solver
and the test of whether the side channel is solver-independent.
clausal/logic/clpz3.py routes z3_eq … z3_ge through `_z3_arith_binary(l, r,
trail, op)`; one `strip_for_solver(l, r, ctx, trail)` call before
`clausal_to_z3` is the whole change — `label_z3` binds vars by `unify`, so the
`units_link` hook reattaches units without Z3 knowing. `in_z3` gets the
`in_domain_units` treatment (its bounds are floats/ints; use a Z3 Real sort for
money). Acceptance: the SI and money clauses of
tests/fixtures/units_clp_side_channel.seam re-spelled with z3 predicates,
skipped when z3-solver is not installed.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.
```

- [ ] **Step 4: Commit**

```bash
git add todo/done/clp-units-side-channel-2026-09-12.md todo/ground-arithmetic-units-mismatch-iso-term-2026-09-12.md todo/clpz3-units-side-channel-second-target-2026-09-12.md docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md docs/superpowers/plans/2026-09-12-clp-units-side-channel.md
git commit -m "todo: units side channel done; ground-path ISO term and CLP(Z3) second target filed"
```

- [ ] **Step 5: Report** — the three claims separately (memory `instruments-that-fail-open`): engine suite failure-set diff (with the two line counts), the fixture clause count, and that no corpus or oracle claim is made by this work.
