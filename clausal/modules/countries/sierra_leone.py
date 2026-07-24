"""Sierra Leone — leone, leone_1964_2023."""
from clausal.modules.countries._currency import _make_currency

leone = _make_currency("leone", iso_code="SLE", scale=2, symbol="SLE", start="2022-07-01", end=None)
leone_1964_2023 = _make_currency("leone_1964_2023", iso_code="SLL", scale=2, symbol="SLL", start="1964-08-04", end="2023-12-31", historical=True)
