#!/usr/bin/env python3
"""Generate the ISO-4217 currency vocabulary for clausal.modules.countries.

Includes CURRENT, HISTORICAL (withdrawn/superseded), and any FUTURE (scheduled
but not yet in use) currencies — legal rulebases must reason about obligations
denominated in defunct currencies (a pre-euro Deutsche Mark contract) and about
currencies with a known in-service date range.

Each currency carries an in-service range: ``start`` / ``end`` (ISO date strings,
or None for open-ended). ``historical`` is True once ``end`` has passed.

Naming — one country reuses a currency word across successive currencies
(Zimbabwe dollar x3, Brazilian cruzeiro x4), and old words collide with the
current one (Mexico MXP vs MXN peso), so within a jurisdiction:
  * a unique currency word is used as-is (``euro``, ``mark``, ``new_kwanza``);
  * the CURRENT currency keeps the plain word (``brazil.real``);
  * colliding older ones are discriminated by the distinguishing term from
    their official name (``brazil.cruzeiro_real``, ``angola.new_kwanza``);
  * where only the date distinguishes them, the in-service years are appended
    (``zimbabwe.dollar_1980_2008``).
The ISO code is always available as metadata (``iso_code``) regardless of name.

Scale for CURRENT currencies is the authoritative ISO 4217 minor unit (NOT
babel/CLDR display precision, which diverges — IQD is 3 in ISO, 0 in CLDR).
Historical currencies default to 2 (best-effort; most were 2).

Run:  python scripts/gen_currencies.py
Writes: clausal/modules/countries/_data.py + one module per jurisdiction.
Runtime has no babel dependency — only the generated files are imported.
"""
from __future__ import annotations

import os
import re
import unicodedata
from collections import defaultdict

from babel import Locale
from babel.core import get_global
from babel.numbers import get_currency_symbol

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "clausal", "modules", "countries")

en = Locale("en")
t2c = get_global("territory_currencies")

ISO_SCALE0 = {"BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG",
              "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}
ISO_SCALE3 = {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}

REGIONAL = {"XOF": "west_african_cfa", "XAF": "central_african_cfa",
            "XPF": "cfp_franc", "XCD": "east_caribbean",
            "XCG": "dutch_caribbean"}
SPECIAL_HOME = {"EUR": "european_union"}

# Canonical base-word overrides where the last word of the name is a qualifier,
# not the currency noun (or to match the documented starter set).
OVERRIDE_NAME = {"GBP": "sterling", "VES": "bolivar"}
OVERRIDE_SYMBOL = {"BHD": "BD"}

# Minor-unit NAMES are curated here because ISO 4217 does not carry them: the
# standard gives only the NUMBER of decimal places (the `scale` field), not the
# word for the subunit. Currencies whose minor unit a rulebase actually writes
# get an entry; the rest simply have no minor unit name, which is honest --
# EUR and USD first (operator, 2026-09-11), widened the same day to AUD, THB
# and GBP after a corpus census found 139 identifiers carrying a minor-unit
# scale in their NAMES across 27 domains -- 6 of which used a currency with no
# minor unit here, so their amounts could not be declared in the unit their
# own names claimed. The FACTOR is never written here: `_make_minor_unit`
# derives it from the currency's own scale.
#
# Names are SINGULAR, as every unit name in the vocabulary is (`metre`, not
# `metres`): GBP's subunit is `penny`, though the corpus spells its
# identifiers `_pence` (operator, 2026-09-11).
MINOR_UNITS = {"AUD": "cent", "EUR": "cent", "GBP": "penny",
               "THB": "satang", "USD": "cent"}


def iso_scale(code):
    return 0 if code in ISO_SCALE0 else 3 if code in ISO_SCALE3 else 2


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()


def _ascii(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def name_tokens(code):
    """Lowercased word tokens of the currency's display name, date removed."""
    disp = _ascii(en.currencies.get(code, code))
    disp = re.sub(r"\(.*?\)", "", disp)  # drop trailing "(1980–2008)"
    return [w.lower() for w in re.findall(r"[A-Za-z]+", disp)]


def base_word(code):
    if code in OVERRIDE_NAME:
        return OVERRIDE_NAME[code]
    toks = name_tokens(code)
    return toks[-1] if toks else code.lower()


def symbol(code):
    if code in OVERRIDE_SYMBOL:
        return OVERRIDE_SYMBOL[code]
    return re.sub(r"\s+", " ", get_currency_symbol(code, locale="en")).strip()


def home(code):
    if code in SPECIAL_HOME:
        return SPECIAL_HOME[code]
    if code in REGIONAL:
        return REGIONAL[code]
    terr = en.territories.get(code[:2])
    return slug(terr) if terr else None


# in-service span per code, aggregated across territories -------------------
_spans = defaultdict(list)
for _terr, _ents in t2c.items():
    if len(_terr) == 2 and _terr.isalpha():
        for _code, _start, _end, _tender in _ents:
            if _tender:
                _spans[_code].append((_start, _end))


def _fmt(d):
    if not d:
        return None
    y = d[0]; m = d[1] if len(d) > 1 else 1; day = d[2] if len(d) > 2 else 1
    return f"{y:04d}-{m:02d}-{day:02d}"


def service(code):
    spans = _spans.get(code, [])
    starts = [s for s, _ in spans if s]
    ends = [e for _, e in spans]
    start = _fmt(min(starts)) if starts else None
    end = None if any(e is None for e in ends) else _fmt(max(e for e in ends if e))
    return start, end


def _year(datestr):
    return datestr.split("-")[0] if datestr else "x"


def build_records():
    current, historical = {}, {}
    for terr, entries in t2c.items():
        if len(terr) != 2 or not terr.isalpha():
            continue
        for code, _start, end, tender in entries:
            if tender:
                (current if end is None else historical).setdefault(code, True)
    for code in list(historical):
        if code in current:
            del historical[code]

    raw = []  # (code, jurisdiction, base, is_current, start, end)
    for code in sorted(current):
        if code.startswith("X") and code not in REGIONAL:
            continue
        j = home(code)
        if j:
            s, e = service(code)
            raw.append({"code": code, "jurisdiction": j, "base": base_word(code),
                        "current": True, "start": s, "end": e})
    for code in sorted(historical):
        if code.startswith("X"):
            continue
        j = home(code)
        if j:
            s, e = service(code)
            raw.append({"code": code, "jurisdiction": j, "base": base_word(code),
                        "current": False, "start": s, "end": e})

    # discriminate names within (jurisdiction, base) groups
    groups = defaultdict(list)
    for r in raw:
        groups[(r["jurisdiction"], r["base"])].append(r)

    recs = []
    for (j, base), members in groups.items():
        if len(members) == 1:
            members[0]["name"] = base
        else:
            common = set.intersection(*[set(name_tokens(m["code"])) for m in members])
            used = set()
            # the single current member keeps the plain base word
            currents = [m for m in members if m["current"]]
            plain = currents[0] if len(currents) == 1 else None
            if plain:
                plain["name"] = base; used.add(base)
            for m in members:
                if m is plain:
                    continue
                disc = [t for t in name_tokens(m["code"]) if t not in common]
                cand = slug("_".join(disc + [base])) if disc else None
                if not cand or cand in used:
                    cand = slug(f"{base}_{_year(m['start'])}_{_year(m['end'])}")
                    if cand in used:
                        cand = slug(f"{base}_{m['code']}")  # last resort
                m["name"] = cand; used.add(cand)
        for m in members:
            recs.append({
                "jurisdiction": j, "name": m["name"], "code": m["code"],
                "scale": iso_scale(m["code"]) if m["current"] else 2,
                "symbol": symbol(m["code"]), "historical": not m["current"],
                "start": m["start"], "end": m["end"],
            })
    recs.sort(key=lambda r: (r["jurisdiction"], r["historical"], r["name"]))
    return recs


def py(v):
    if v is None:
        return "None"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return str(v)
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    recs = build_records()
    seen = set()
    for r in recs:
        key = (r["jurisdiction"], r["name"])
        assert key not in seen, f"duplicate {key}"
        seen.add(key)
    jurisdictions = sorted({r["jurisdiction"] for r in recs})

    fields = ("jurisdiction", "name", "code", "scale", "symbol", "historical",
              "start", "end")
    with open(os.path.join(OUT, "_data.py"), "w", encoding="utf-8") as f:
        f.write('"""Generated ISO-4217 currency data. Edit scripts/gen_currencies.py, not this."""\n\n')
        f.write("CURRENCIES = [\n")
        for r in recs:
            f.write("    {" + ", ".join(f'"{k}": {py(r[k])}' for k in fields) + "},\n")
        f.write("]\n\n")
        f.write("JURISDICTIONS = [\n")
        for j in jurisdictions:
            f.write(f"    {py(j)},\n")
        f.write("]\n")
        # Readable without importing any jurisdiction module -- the Prolog
        # exporter needs the minor-unit NAMES to refuse a quantity it cannot
        # export faithfully, and importing 181 modules to learn two strings
        # would be absurd.
        f.write("\nMINOR_UNITS = {\n")
        for code in sorted(MINOR_UNITS):
            f.write(f"    {py(code)}: {py(MINOR_UNITS[code])},\n")
        f.write("}\n")

    by_j = defaultdict(list)
    for r in recs:
        by_j[r["jurisdiction"]].append(r)
    for j, items in by_j.items():
        title = j.replace("_", " ").title()
        with open(os.path.join(OUT, f"{j}.py"), "w", encoding="utf-8") as f:
            f.write(f'"""{title} — {", ".join(r["name"] for r in items)}."""\n')
            minor = [r for r in items if r["code"] in MINOR_UNITS]
            for r in minor:
                # A minor unit shares the jurisdiction module's namespace with
                # the currencies, so a subunit word that is also a currency
                # word in the same jurisdiction would silently shadow one.
                assert MINOR_UNITS[r["code"]] not in {i["name"] for i in items}, (
                    f'minor unit {MINOR_UNITS[r["code"]]!r} collides with a '
                    f'currency name in {j}')
            imports = "_make_currency"
            if minor:
                imports += ", _make_minor_unit"
            f.write(f"from clausal.modules.countries._currency import {imports}\n\n")
            for r in items:
                args = (f'{py(r["name"])}, iso_code={py(r["code"])}, '
                        f'scale={r["scale"]}, symbol={py(r["symbol"])}, '
                        f'start={py(r["start"])}, end={py(r["end"])}')
                if r["historical"]:
                    args += ", historical=True"
                f.write(f'{r["name"]} = _make_currency({args})\n')
            for r in minor:
                f.write(f'{MINOR_UNITS[r["code"]]} = _make_minor_unit({r["name"]})\n')

    cur = sum(1 for r in recs if not r["historical"])
    print(f"wrote _data.py + {len(jurisdictions)} modules; "
          f"{cur} current + {len(recs) - cur} historical = {len(recs)} currencies")


if __name__ == "__main__":
    main()
