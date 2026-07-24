"""Ghana — cedi, cedi_1979_2007."""
from clausal.modules.countries._currency import _make_currency

cedi = _make_currency("cedi", iso_code="GHS", scale=2, symbol="GHS", start="2007-07-03", end=None)
cedi_1979_2007 = _make_currency("cedi_1979_2007", iso_code="GHC", scale=2, symbol="GHC", start="1979-03-09", end="2007-12-31", historical=True)
