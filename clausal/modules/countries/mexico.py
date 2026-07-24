"""Mexico — peso."""
from clausal.modules.countries._currency import _make_currency

peso = _make_currency("peso", iso_code="MXN", scale=2, symbol="MX$")
