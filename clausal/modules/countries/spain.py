"""Spain — peseta."""
from clausal.modules.countries._currency import _make_currency

peseta = _make_currency("peseta", iso_code="ESP", scale=2, symbol="ESP", start="1800-01-01", end="2002-02-28", historical=True)
