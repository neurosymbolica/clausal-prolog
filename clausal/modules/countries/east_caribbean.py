"""East Caribbean — dollar."""
from clausal.modules.countries._currency import _make_currency

xcd = _make_currency("dollar", iso_code="XCD", scale=2, symbol="EC$", start="1965-10-06", end=None)
