"""Ukraine — hryvnia, karbovanets."""
from clausal.modules.countries._currency import _make_currency

hryvnia = _make_currency("hryvnia", iso_code="UAH", scale=2, symbol="UAH", start="1996-09-02", end=None)
karbovanets = _make_currency("karbovanets", iso_code="UAK", scale=2, symbol="UAK", start="1992-11-13", end="1993-10-17", historical=True)
