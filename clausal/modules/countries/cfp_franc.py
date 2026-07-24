"""Cfp Franc — franc."""
from clausal.modules.countries._currency import _make_currency

franc = _make_currency("franc", iso_code="XPF", scale=0, symbol="CFPF")
