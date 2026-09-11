"""Mauritius — rupee."""
from clausal.modules.countries._currency import _make_currency

mur = _make_currency("rupee", iso_code="MUR", scale=2, symbol="MUR", start="1934-04-01", end=None)
