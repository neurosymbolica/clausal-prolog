"""Tajikistan — somoni, ruble."""
from clausal.modules.countries._currency import _make_currency

somoni = _make_currency("somoni", iso_code="TJS", scale=2, symbol="TJS", start="2000-10-26", end=None)
tjr = _make_currency("ruble", iso_code="TJR", scale=2, symbol="TJR", start="1995-05-10", end="2000-10-25", historical=True)
