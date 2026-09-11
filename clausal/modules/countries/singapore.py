"""Singapore — dollar."""
from clausal.modules.countries._currency import _make_currency

sgd = _make_currency("dollar", iso_code="SGD", scale=2, symbol="SGD", start="1967-06-12", end=None)
