"""Luxembourg — franc."""
from clausal.modules.countries._currency import _make_currency

franc = _make_currency("franc", iso_code="LUF", scale=2, symbol="LUF", start="1944-09-04", end="2002-02-28", historical=True)
