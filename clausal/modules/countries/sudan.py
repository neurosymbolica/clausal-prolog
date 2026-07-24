"""Sudan — pound, dinar, pound_1957_1998."""
from clausal.modules.countries._currency import _make_currency

pound = _make_currency("pound", iso_code="SDG", scale=2, symbol="SDG", start="2007-01-10", end=None)
dinar = _make_currency("dinar", iso_code="SDD", scale=2, symbol="SDD", start="1992-06-08", end="2007-06-30", historical=True)
pound_1957_1998 = _make_currency("pound_1957_1998", iso_code="SDP", scale=2, symbol="SDP", start="1957-04-08", end="1998-06-01", historical=True)
