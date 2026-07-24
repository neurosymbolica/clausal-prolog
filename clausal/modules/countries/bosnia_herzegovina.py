"""Bosnia Herzegovina — mark, dinar_1992_1994, new_dinar."""
from clausal.modules.countries._currency import _make_currency

mark = _make_currency("mark", iso_code="BAM", scale=2, symbol="BAM", start="1995-01-01", end=None)
dinar_1992_1994 = _make_currency("dinar_1992_1994", iso_code="BAD", scale=2, symbol="BAD", start="1992-07-01", end="1994-08-15", historical=True)
new_dinar = _make_currency("new_dinar", iso_code="BAN", scale=2, symbol="BAN", start="1994-08-15", end="1997-07-01", historical=True)
