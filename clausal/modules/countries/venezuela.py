"""Venezuela — bolivar, bolivar_1871_2008, bolivar_2008_2018."""
from clausal.modules.countries._currency import _make_currency

bolivar = _make_currency("bolivar", iso_code="VES", scale=2, symbol="VES", start="2018-08-20", end=None)
bolivar_1871_2008 = _make_currency("bolivar_1871_2008", iso_code="VEB", scale=2, symbol="VEB", start="1871-05-11", end="2008-06-30", historical=True)
bolivar_2008_2018 = _make_currency("bolivar_2008_2018", iso_code="VEF", scale=2, symbol="VEF", start="2008-01-01", end="2018-08-20", historical=True)
