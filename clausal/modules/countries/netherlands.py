"""Netherlands — guilder."""
from clausal.modules.countries._currency import _make_currency

guilder = _make_currency("guilder", iso_code="NLG", scale=2, symbol="NLG", start="1813-01-01", end="2002-02-28", historical=True)
