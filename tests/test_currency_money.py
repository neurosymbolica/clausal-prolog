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
from clausal.logic.atoms import mint


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
    # THE FLIP (2026-09-06-atoms-as-cells-strings, migration rule (c)): the
    # inline modules below MEAN STRINGS by ``"7.89"`` — a money amount is
    # text handed to ``Decimal``, not a symbol — so they read "..." as one.
    d = tempfile.mkdtemp()
    p = os.path.join(d, f"{name}.clausal")
    with open(p, "w") as f:
        f.write("-double_quotes(chars)\n" + src)
    return _load_module(name, p).__dict__["$module"]


def _succeeds(mod, pred="test"):
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
            "test <- (money(\"7.89\", euro, A), eval_(7.89(euro), B), A == B)\n")
        assert _succeeds(mod)


class TestCurrencyPrecisionErrorCatch:
    """catch/3 can catch the CurrencyPrecisionError raised by money/3 through a ++ catcher."""

    def test_uncaught_precision_error_propagates(self):
        """money/3 with over-precise string propagates as LogicException without catch/3."""
        mod = _load("nocatch_precision",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "test <- money(\"7.891\", euro, _X)\n")
        with pytest.raises(LogicException):
            list(call("test", module=mod))


class TestMoneyPrecisionCatchable:
    """Prove the real requirement: CurrencyPrecisionError is catchable via catch/3 (++ catcher)."""

    def test_money_precision_error_is_catchable(self):
        mod = _load("money_catch",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "-import_from(clausal.terms, [CurrencyPrecisionError])\n"
            "test <- catch(money(\"7.891\", euro, X), ++CurrencyPrecisionError, 1 == 1)\n")
        assert _succeeds(mod)          # the precision error is caught; recovery succeeds

    def test_valid_money_needs_no_catch(self):
        mod = _load("money_ok",
            "-import_from(currency, [money])\n"
            "-import_from(european_union, [euro])\n"
            "test <- money(\"7.89\", euro, X)\n")
        assert _succeeds(mod)


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
        with pytest.raises(LogicException):
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
        from clausal.modules.py.units import metre
        q = Quantity(5.0, {metre: 1})
        assert format(q, "") == str(q)


class TestModulePredicateBoundaryCatchers:
    """A Python exception raised inside a module predicate reaches the
    catcher chain wrapped by ``_catchable_dispatch`` as
    ``LogicException(python_error_term(exc)) from exc``.  ``catch_match``
    unwraps that shape for the Python arms of a ``++`` catcher, but ONLY
    for a catcher that is not itself (a subclass of) ``LogicException`` —
    the wrapper IS one, and ``++LogicException`` must keep matching it.
    ``money/3`` is the module predicate that raises here (``CurrencyPrecisionError``);
    the ``py.*`` wrappers fail cleanly on bad input instead of raising."""

    SRC = (
        "-import_from(currency, [money])\n"
        "-import_from(european_union, [euro])\n"
        "-import_from(clausal.terms, [CurrencyPrecisionError])\n"
        "-import_from(clausal.logic.exceptions, [LogicException])\n"
        "-private([caught])\n"
        "c_logic(R) <- catch(money(\"7.891\", euro, _P), ++LogicException, R is caught)\n"
        "c_class(R) <- catch(money(\"7.891\", euro, _P), ++CurrencyPrecisionError, R is caught)\n"
        "c_inst(M) <- catch(money(\"7.891\", euro, _P), ++CurrencyPrecisionError(M), true)\n"
        "c_super(R) <- catch(money(\"7.891\", euro, _P), ++Exception, R is caught)\n"
        "c_wrong(R) <- catch(money(\"7.891\", euro, _P), ++ValueError, R is caught)\n"
    )

    def _answers(self, pred):
        from clausal.logic.variables import Var, deref
        mod = _load("money_boundary_" + pred, self.SRC)
        out = Var()
        return [deref(out) for _ in call(pred, out, module=mod)]

    def test_logic_exception_catcher_sees_the_wrapper(self):
        assert self._answers("c_logic") == [mint("caught")]

    def test_class_catcher_sees_the_python_cause(self):
        assert self._answers("c_class") == [mint("caught")]

    def test_instance_catcher_binds_the_message(self):
        [msg] = self._answers("c_inst")
        assert "7.891" in str(msg)

    def test_python_superclass_catcher_matches(self):
        assert self._answers("c_super") == [mint("caught")]

    def test_wrong_python_class_stays_selective(self):
        with pytest.raises(LogicException):
            self._answers("c_wrong")
