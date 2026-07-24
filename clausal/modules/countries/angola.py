"""Angola — kwanza, kwanza_1977_1991, new_kwanza, readjusted_kwanza."""
from clausal.modules.countries._currency import _make_currency

kwanza = _make_currency("kwanza", iso_code="AOA", scale=2, symbol="AOA", start="1999-12-13", end=None)
kwanza_1977_1991 = _make_currency("kwanza_1977_1991", iso_code="AOK", scale=2, symbol="AOK", start="1977-01-08", end="1991-03-01", historical=True)
new_kwanza = _make_currency("new_kwanza", iso_code="AON", scale=2, symbol="AON", start="1990-09-25", end="2000-02-01", historical=True)
readjusted_kwanza = _make_currency("readjusted_kwanza", iso_code="AOR", scale=2, symbol="AOR", start="1995-07-01", end="2000-02-01", historical=True)
