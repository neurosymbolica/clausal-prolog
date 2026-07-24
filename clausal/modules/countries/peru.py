"""Peru — sol, inti, sol_1863_1985."""
from clausal.modules.countries._currency import _make_currency

sol = _make_currency("sol", iso_code="PEN", scale=2, symbol="PEN", start="1991-07-01", end=None)
inti = _make_currency("inti", iso_code="PEI", scale=2, symbol="PEI", start="1985-02-01", end="1991-07-01", historical=True)
sol_1863_1985 = _make_currency("sol_1863_1985", iso_code="PES", scale=2, symbol="PES", start="1863-02-14", end="1985-02-01", historical=True)
