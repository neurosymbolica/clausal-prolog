"""Finland — markka."""
from clausal.modules.countries._currency import _make_currency

markka = _make_currency("markka", iso_code="FIM", scale=2, symbol="FIM", start="1963-01-01", end="2002-02-28", historical=True)
