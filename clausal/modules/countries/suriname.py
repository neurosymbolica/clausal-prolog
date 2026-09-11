"""Suriname — dollar, guilder."""
from clausal.modules.countries._currency import _make_currency

srd = _make_currency("dollar", iso_code="SRD", scale=2, symbol="SRD", start="2004-01-01", end=None)
srg = _make_currency("guilder", iso_code="SRG", scale=2, symbol="SRG", start="1940-05-10", end="2003-12-31", historical=True)
