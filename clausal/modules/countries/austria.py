"""Austria — schilling."""
from clausal.modules.countries._currency import _make_currency

schilling = _make_currency("schilling", iso_code="ATS", scale=2, symbol="ATS", start="1947-12-04", end="2002-02-28", historical=True)
