"""Philippines — peso."""
from clausal.modules.countries._currency import _make_currency

peso = _make_currency("peso", iso_code="PHP", scale=2, symbol="₱", start="1946-07-04", end=None)
