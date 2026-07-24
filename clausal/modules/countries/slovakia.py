"""Slovakia — koruna."""
from clausal.modules.countries._currency import _make_currency

koruna = _make_currency("koruna", iso_code="SKK", scale=2, symbol="SKK", start="1992-12-31", end="2009-01-01", historical=True)
