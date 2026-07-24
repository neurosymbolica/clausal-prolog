"""Israel — shekel."""
from clausal.modules.countries._currency import _make_currency

shekel = _make_currency("shekel", iso_code="ILS", scale=2, symbol="₪")
