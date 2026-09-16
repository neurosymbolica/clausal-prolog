import pytest

from clausal.modules import _unit_registry as R


def test_register_and_look_up():
    R.register("testium", R.UnitInfo(name="testium"))
    assert R.info("testium").name == "testium"
    assert R.is_currency("testium") is False


def test_currency_metadata_round_trips():
    R.register("testbuck", R.UnitInfo(name="testbuck", is_currency=True,
                                      iso_code="TBK", scale=2, symbol="T$"))
    got = R.info("testbuck")
    assert (got.is_currency, got.iso_code, got.scale, got.symbol) == (True, "TBK", 2, "T$")
    assert R.is_currency("testbuck") is True


def test_unknown_atom_is_none_not_an_error():
    assert R.info("no_such_unit") is None
    assert R.is_currency("no_such_unit") is False


def test_re_registering_the_same_info_is_allowed():
    R.register("idem", R.UnitInfo(name="idem"))
    R.register("idem", R.UnitInfo(name="idem"))      # equal value, not a conflict


def test_conflicting_re_register_raises():
    R.register("clash", R.UnitInfo(name="clash", scale=2))
    with pytest.raises(ValueError, match="clash"):
        R.register("clash", R.UnitInfo(name="clash", scale=3))
