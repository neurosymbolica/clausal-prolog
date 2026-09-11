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
def currency_bindings(records):
    """The identifier each currency is BOUND to in its jurisdiction module.

    A currency keeps its everyday word when that word names exactly one
    CURRENT currency; otherwise it is bound by its lowercase ISO 4217 code.
    `dinar` is the word of eight current currencies, so it names none of them
    and bahrain's is `bhd`, kuwait's `kwd`. `euro`, `yen` and `baht` are
    unshared and are untouched (operator, 2026-09-11).

    Keeping the word for a SOLE CURRENT user is the convention this generator
    already applies within a jurisdiction -- "the current currency keeps the
    plain word" -- extended across them. It earns its place twice over: a
    legal text says "lira", not "TRY", and `try` is a Python keyword that
    could never be an identifier at all. TRY is the only current lira, so the
    code is never needed.

    The word survives as the currency's `_name` either way: this changes the
    identifier a rulebase WRITES, not the word the system PRINTS.
    """
    users = {}
    for r in records:
        users.setdefault(r["name"], []).append(r)
    out = {}
    for r in records:
        sharers = users[r["name"]]
        current = [x for x in sharers if not x["historical"]]
        sole = len(current) == 1 and current[0]["code"] == r["code"]
        out[r["code"]] = r["name"] if (len(sharers) == 1 or sole) else r["code"].lower()
    return out


# Curated subunit WORDS, one per currency whose minor unit a rulebase writes.
# EUR and USD first (operator, 2026-09-11), widened the same day to AUD, THB
# and GBP after a corpus census found 139 identifiers carrying a minor-unit
# scale in their NAMES across 27 domains -- 6 of which used a currency with no
# minor unit here. ISO 4217 carries the SCALE but not the WORD, so these are
# curated; the FACTOR is never written, `_make_minor_unit` derives it from the
# currency's own scale.
#
# Words are SINGULAR, as every unit name in the vocabulary is (`metre`, not
# `metres`): GBP's subunit is `penny`, though the corpus spells its identifiers
# `_pence` (operator, 2026-09-11).
MINOR_UNIT_WORDS = {"AUD": "cent", "EUR": "cent", "GBP": "penny",
                    "THB": "satang", "USD": "cent"}


def minor_unit_names(words):
    """Resolve curated subunit words to the names actually bound.

    A word belonging to more than one currency names none of them, so it
    takes its ISO code as a prefix: `cent` is AUD's, EUR's and USD's alike
    and becomes `eur_cent`/`usd_cent`/`aud_cent`. A word belonging to one
    currency stays bare -- `satang` is Thailand's alone (operator,
    2026-09-11).

    This closes two holes by construction rather than guarding them. Two
    jurisdictions can no longer bind the same bare minor-unit name, which
    `-import_from` resolves silently last-one-wins; and because
    `constant_number_units/3` reports the declared SPELLING, the spelling
    now carries the currency -- previously EUR and USD cents both answered
    `cent`, and the qualified `united_states.cent` that would have
    disambiguated records nothing at all (`_units_ast_to_term` returns None
    for an Attribute).
    """
    shared = {w for w in words.values()
              if sum(1 for x in words.values() if x == w) > 1}
    return {code: (f"{code.lower()}_{word}" if word in shared else word)
            for code, word in words.items()}


MINOR_UNITS = minor_unit_names(MINOR_UNIT_WORDS)


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

    bindings = currency_bindings(recs)
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
        f.write("\n#: The identifier each currency is BOUND to: its everyday\n"
                "#: word when that word names exactly one CURRENT currency,\n"
                "#: otherwise its lowercase ISO 4217 code. The word survives\n"
                "#: as `_name` for display either way.\n")
        f.write("CURRENCY_BINDINGS = {\n")
        for code in sorted(bindings):
            f.write(f"    {py(code)}: {py(bindings[code])},\n")
        f.write("}\n")
        f.write("\n#: Curated subunit WORDS (ISO 4217 carries the scale, "
                "not the word).\n")
        f.write("MINOR_UNIT_WORDS = {\n")
        for code in sorted(MINOR_UNIT_WORDS):
            f.write(f"    {py(code)}: {py(MINOR_UNIT_WORDS[code])},\n")
        f.write("}\n")
        f.write("\n#: The names actually bound: a word shared by more than "
                "one currency\n#: takes its ISO code as a prefix, a unique "
                "word stays bare.\n")
        f.write("MINOR_UNITS = {\n")
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
                f.write(f'{bindings[r["code"]]} = _make_currency({args})\n')
            for r in minor:
                f.write(f'{MINOR_UNITS[r["code"]]} = '
                        f'_make_minor_unit({bindings[r["code"]]})\n')

    cur = sum(1 for r in recs if not r["historical"])
    print(f"wrote _data.py + {len(jurisdictions)} modules; "
          f"{cur} current + {len(recs) - cur} historical = {len(recs)} currencies")


if __name__ == "__main__":
    main()
