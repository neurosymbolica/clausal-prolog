"""Bulgaria — lev, hard_lev, lev_1879_1952, socialist_lev."""
from clausal.modules.countries._currency import _make_currency

lev = _make_currency("lev", iso_code="BGN", scale=2, symbol="BGN", start="1999-07-05", end=None)
hard_lev = _make_currency("hard_lev", iso_code="BGL", scale=2, symbol="BGL", start="1962-01-01", end="1999-07-05", historical=True)
lev_1879_1952 = _make_currency("lev_1879_1952", iso_code="BGO", scale=2, symbol="BGO", start="1879-07-08", end="1952-05-12", historical=True)
socialist_lev = _make_currency("socialist_lev", iso_code="BGM", scale=2, symbol="BGM", start="1952-05-12", end="1962-01-01", historical=True)
