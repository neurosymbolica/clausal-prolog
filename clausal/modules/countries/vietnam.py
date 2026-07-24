"""Vietnam — dong, dong_1978_1985."""
from clausal.modules.countries._currency import _make_currency

dong = _make_currency("dong", iso_code="VND", scale=0, symbol="₫", start="1985-09-14", end=None)
dong_1978_1985 = _make_currency("dong_1978_1985", iso_code="VNN", scale=2, symbol="VNN", start="1978-05-03", end="1985-09-14", historical=True)
