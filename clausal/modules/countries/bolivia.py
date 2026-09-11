"""Bolivia — boliviano, boliviano_1863_1963, peso."""
from clausal.modules.countries._currency import _make_currency

boliviano = _make_currency("boliviano", iso_code="BOB", scale=2, symbol="BOB", start="1987-01-01", end=None)
boliviano_1863_1963 = _make_currency("boliviano_1863_1963", iso_code="BOL", scale=2, symbol="BOL", start="1863-06-23", end="1963-01-01", historical=True)
bop = _make_currency("peso", iso_code="BOP", scale=2, symbol="BOP", start="1963-01-01", end="1986-12-31", historical=True)
