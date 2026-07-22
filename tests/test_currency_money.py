import os
import tempfile
from decimal import Decimal

import pytest

from clausal.terms import Quantity, CurrencyPrecisionError
from clausal.modules.countries.european_union import euro
from clausal.modules.countries.japan import yen
from clausal.modules.countries.bahrain import dinar

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var as LVar, deref
from clausal.logic.solve import _drive_trampoline
from clausal.logic.exceptions import LogicException


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


class TestMoneyConstructorsAndAccessors:
    def test_money_from_string_is_exact(self):
        from clausal.modules.currency import money
        r = _run(money, "7.89", euro, "OUT")
        assert r[0]["OUT"] == Quantity(Decimal("7.89"), euro)

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


class TestCurrencyPrecisionErrorCatch:
    """catch/3 can catch CurrencyPrecisionError raised by money/3."""

    def test_catch_precision_error(self):
        """money/3 with over-precise string is catchable via catch/3."""
        mod = _load("catch_precision",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "Test <- catch(money(\"7.891\", euro, _X), CurrencyPrecisionError(_M), 1 == 1)\n")
        assert _succeeds(mod)

    def test_uncaught_precision_error_propagates(self):
        """money/3 with over-precise string propagates as LogicException without catch/3."""
        mod = _load("nocatch_precision",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "Test <- money(\"7.891\", euro, _X)\n")
        with pytest.raises(LogicException):
            list(call("Test", module=mod))


class TestMoneyPrecisionCatchable:
    """Prove the real requirement: CurrencyPrecisionError is catchable via catch/3."""

    def test_money_precision_error_is_catchable(self):
        mod = _load("money_catch",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "Test <- catch(money(\"7.891\", euro, X), CurrencyPrecisionError(M), 1 == 1)\n")
        assert _succeeds(mod)          # the precision error is caught; recovery succeeds

    def test_valid_money_needs_no_catch(self):
        mod = _load("money_ok",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "Test <- money(\"7.89\", euro, X)\n")
        assert _succeeds(mod)
