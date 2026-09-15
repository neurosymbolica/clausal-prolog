"""Metadata comes from the REGISTRY, not off the dimension key.

This is what makes the rekey safe. Every metadata read used to be
``getattr(key, "is_currency", False)``, which against a ``str`` atom returns
False SILENTLY -- so flipping the keys first would have turned every currency
into a non-currency with no error anywhere.
"""
from clausal.modules import _unit_registry as R
from clausal.modules import units
from clausal.modules.countries import european_union
from clausal.terms import Quantity, _currency_info


def test_every_base_unit_constant_is_registered():
    for name in ("metre", "second", "kilogram", "dimensionless"):
        assert R.info(name) is not None, f"{name} is not in the registry"


def test_a_currency_is_registered_with_its_metadata():
    got = R.info("euro")
    assert got is not None and got.is_currency
    assert (got.iso_code, got.scale, got.symbol) == ("EUR", 2, "€")


def test_a_base_unit_is_not_a_currency():
    assert R.is_currency("metre") is False


def test_currency_info_resolves_a_dimension_key():
    q = Quantity(1550.00, european_union.euro)
    (key, _exp), = q.dims.items()
    got = _currency_info(key)
    assert got is not None and got.iso_code == "EUR"


def test_currency_info_is_none_for_a_non_currency_dimension():
    q = Quantity(5, units.metre)
    (key, _exp), = q.dims.items()
    assert _currency_info(key) is None


def test_currency_info_answers_an_ATOM_too():
    # The point of taking a key rather than an atom: it must work on BOTH
    # sides of the rekey, so the flip is a one-function change.
    assert _currency_info("euro") is not None
    assert _currency_info("metre") is None


def test_money_formatting_still_works_end_to_end():
    q = Quantity(1550.00, european_union.euro)
    assert format(q, "code") == "1550.00 EUR"
    assert format(q, "symbol") == "€1550.00"
    assert format(q, "name") == "1550.00 euro"
