"""Greece — drachma."""
from clausal.modules.countries._currency import _make_currency

drachma = _make_currency("drachma", iso_code="GRD", scale=2, symbol="GRD", start="1954-05-01", end="2002-02-28", historical=True)
