"""Malaysia — ringgit."""
from clausal.modules.countries._currency import _make_currency

ringgit = _make_currency("ringgit", iso_code="MYR", scale=2, symbol="MYR", start="1963-09-16", end=None)
