"""Uganda — shilling, shilling_1966_1987."""
from clausal.modules.countries._currency import _make_currency

shilling = _make_currency("shilling", iso_code="UGX", scale=0, symbol="UGX", start="1987-05-15", end=None)
shilling_1966_1987 = _make_currency("shilling_1966_1987", iso_code="UGS", scale=2, symbol="UGS", start="1966-08-15", end="1987-05-15", historical=True)
