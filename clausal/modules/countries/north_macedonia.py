"""North Macedonia — denar, denar_1992_1993."""
from clausal.modules.countries._currency import _make_currency

denar = _make_currency("denar", iso_code="MKD", scale=2, symbol="MKD", start="1993-05-20", end=None)
denar_1992_1993 = _make_currency("denar_1992_1993", iso_code="MKN", scale=2, symbol="MKN", start="1992-04-26", end="1993-05-20", historical=True)
