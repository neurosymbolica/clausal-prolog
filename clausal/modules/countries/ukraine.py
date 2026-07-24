"""Ukraine — hryvnia."""
from clausal.modules.countries._currency import _make_currency

hryvnia = _make_currency("hryvnia", iso_code="UAH", scale=2, symbol="UAH")
