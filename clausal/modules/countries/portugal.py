"""Portugal — escudo."""
from clausal.modules.countries._currency import _make_currency

pte = _make_currency("escudo", iso_code="PTE", scale=2, symbol="PTE", start="1911-05-22", end="2002-02-28", historical=True)
