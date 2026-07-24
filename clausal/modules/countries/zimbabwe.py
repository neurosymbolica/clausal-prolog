"""Zimbabwe — gold, dollar_1980_2008, dollar_2008_2009, dollar_2009_2024."""
from clausal.modules.countries._currency import _make_currency

gold = _make_currency("gold", iso_code="ZWG", scale=2, symbol="ZWG", start="2024-06-25", end=None)
dollar_1980_2008 = _make_currency("dollar_1980_2008", iso_code="ZWD", scale=2, symbol="ZWD", start="1980-04-18", end="2008-08-01", historical=True)
dollar_2008_2009 = _make_currency("dollar_2008_2009", iso_code="ZWR", scale=2, symbol="ZWR", start="2008-08-01", end="2009-02-02", historical=True)
dollar_2009_2024 = _make_currency("dollar_2009_2024", iso_code="ZWL", scale=2, symbol="ZWL", start="2009-02-02", end="2024-08-31", historical=True)
