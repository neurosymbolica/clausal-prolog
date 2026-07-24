#!/usr/bin/env python3
"""Generate the ISO-4217 currency vocabulary for clausal.modules.countries.

Source of truth for *scale* is ISO 4217 minor units (NOT babel/CLDR display
precision, which diverges — e.g. IQD is 3 in ISO but 0 in CLDR). Names, symbols,
and home territories come from babel; a small OVERRIDE table pins canonical
choices (e.g. GBP -> sterling) and the regional/supranational homes.

Run:  python scripts/gen_currencies.py
Writes: clausal/modules/countries/_data.py  and one module per jurisdiction.
Regenerate whenever the currency set changes; commit the results. Runtime has
no babel dependency — only the generated files are imported.
"""
from __future__ import annotations

import os
import re
import unicodedata

from babel import Locale
from babel.core import get_global
from babel.numbers import get_currency_symbol

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "clausal", "modules", "countries")

en = Locale("en")
t2c = get_global("territory_currencies")

# Authoritative ISO 4217 minor-unit exceptions; everything else is 2.
ISO_SCALE0 = {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
              "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
ISO_SCALE3 = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

# Homes that are not a single country (code[:2] is not an ISO-3166 country).
REGIONAL = {"XOF": "west_african_cfa", "XAF": "central_african_cfa",
            "XPF": "cfp_franc", "XCD": "east_caribbean",
            "XCG": "dutch_caribbean"}  # Caribbean guilder (Curaçao + Sint Maarten)
SPECIAL_HOME = {"EUR": "european_union"}

# Canonical overrides (name/symbol) to match the documented starter set.
OVERRIDE_NAME = {"GBP": "sterling"}
OVERRIDE_SYMBOL = {"BHD": "BD"}


def iso_scale(code: str) -> int:
    return 0 if code in ISO_SCALE0 else 3 if code in ISO_SCALE3 else 2


def slug(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def bare_name(code: str) -> str:
    if code in OVERRIDE_NAME:
        return OVERRIDE_NAME[code]
    disp = en.currencies.get(code, code)
    disp = unicodedata.normalize("NFKD", disp).encode("ascii", "ignore").decode()
    words = re.findall(r"[A-Za-z]+", disp)
    return words[-1].lower() if words else code.lower()


def symbol(code: str) -> str:
    if code in OVERRIDE_SYMBOL:
        return OVERRIDE_SYMBOL[code]
    s = get_currency_symbol(code, locale="en")
    # collapse odd unicode spaces (e.g. 'F CFA') to a plain space
    return re.sub(r"\s+", " ", s).strip()


def home(code: str) -> str | None:
    if code in SPECIAL_HOME:
        return SPECIAL_HOME[code]
    if code in REGIONAL:
        return REGIONAL[code]
    terr = en.territories.get(code[:2])
    return slug(terr) if terr else None


def build_records():
    active = {}
    for terr, entries in t2c.items():
        if len(terr) != 2 or not terr.isalpha():
            continue
        for cur, _start, end, tender in entries:
            if end is None and tender:
                active.setdefault(cur, True)
    recs = []
    for code in sorted(active):
        if code.startswith("X") and code not in REGIONAL:
            continue  # supranational non-regional (XDR/XAU/XSU/XCG/...) — skip
        j = home(code)
        if not j:
            continue
        recs.append({"jurisdiction": j, "name": bare_name(code),
                     "code": code, "scale": iso_scale(code), "symbol": symbol(code)})
    recs.sort(key=lambda r: r["jurisdiction"])
    return recs


def py_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    recs = build_records()
    jurisdictions = sorted({r["jurisdiction"] for r in recs})
    # collision guards
    assert len(jurisdictions) == len(recs), "a jurisdiction issues >1 currency — needs handling"

    # 1) authoritative data module (runtime, no babel)
    with open(os.path.join(OUT, "_data.py"), "w", encoding="utf-8") as f:
        f.write('"""Generated ISO-4217 currency data. Edit scripts/gen_currencies.py, not this."""\n\n')
        f.write("CURRENCIES = [\n")
        for r in recs:
            f.write("    {"
                    f'"jurisdiction": {py_str(r["jurisdiction"])}, '
                    f'"name": {py_str(r["name"])}, '
                    f'"code": {py_str(r["code"])}, '
                    f'"scale": {r["scale"]}, '
                    f'"symbol": {py_str(r["symbol"])}'
                    "},\n")
        f.write("]\n\n")
        f.write("JURISDICTIONS = [\n")
        for j in jurisdictions:
            f.write(f"    {py_str(j)},\n")
        f.write("]\n")

    # 2) one self-contained module per jurisdiction
    title = {r["jurisdiction"]: r["jurisdiction"].replace("_", " ").title() for r in recs}
    for r in recs:
        path = os.path.join(OUT, f"{r['jurisdiction']}.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f'"""{title[r["jurisdiction"]]} — {r["name"]}."""\n')
            f.write("from clausal.modules.countries._currency import _make_currency\n\n")
            f.write(f'{r["name"]} = _make_currency({py_str(r["name"])}, '
                    f'iso_code={py_str(r["code"])}, scale={r["scale"]}, '
                    f'symbol={py_str(r["symbol"])})\n')

    print(f"wrote _data.py + {len(recs)} jurisdiction modules; jurisdictions={len(jurisdictions)}")


if __name__ == "__main__":
    main()
