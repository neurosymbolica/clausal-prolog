"""Brazil — real, cruzado_1986_1989, cruzeiro_1942_1967, cruzeiro_1990_1993, cruzeiro_1993_1994, new_cruzado, new_cruzeiro."""
from clausal.modules.countries._currency import _make_currency

real = _make_currency("real", iso_code="BRL", scale=2, symbol="R$", start="1994-07-01", end=None)
cruzado_1986_1989 = _make_currency("cruzado_1986_1989", iso_code="BRC", scale=2, symbol="BRC", start="1986-02-28", end="1989-01-15", historical=True)
cruzeiro_1942_1967 = _make_currency("cruzeiro_1942_1967", iso_code="BRZ", scale=2, symbol="BRZ", start="1942-11-01", end="1967-02-13", historical=True)
cruzeiro_1990_1993 = _make_currency("cruzeiro_1990_1993", iso_code="BRE", scale=2, symbol="BRE", start="1990-03-16", end="1993-08-01", historical=True)
cruzeiro_1993_1994 = _make_currency("cruzeiro_1993_1994", iso_code="BRR", scale=2, symbol="BRR", start="1993-08-01", end="1994-07-01", historical=True)
new_cruzado = _make_currency("new_cruzado", iso_code="BRN", scale=2, symbol="BRN", start="1989-01-15", end="1990-03-16", historical=True)
new_cruzeiro = _make_currency("new_cruzeiro", iso_code="BRB", scale=2, symbol="BRB", start="1967-02-13", end="1986-02-28", historical=True)
