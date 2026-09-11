"""Maldives — rufiyaa, rupee."""
from clausal.modules.countries._currency import _make_currency

rufiyaa = _make_currency("rufiyaa", iso_code="MVR", scale=2, symbol="MVR", start="1981-07-01", end=None)
mvp = _make_currency("rupee", iso_code="MVP", scale=2, symbol="MVP", start="1947-01-01", end="1981-07-01", historical=True)
