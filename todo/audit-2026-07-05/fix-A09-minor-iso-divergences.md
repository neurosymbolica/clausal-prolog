# fix(A09-F028/F030/F031): minor ISO divergences in must_be, number parsing, atom_concat errors

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F028, F030, F031

## Items

1. **F028** — `must_be/2` & `can_be/2` with an UNKNOWN type name raise
   `type_error(<bogus>, Term)` — misleading (implies Term is wrong; the TYPE
   is). ISO: `domain_error(type, Type)`. Also an unbound/non-str Type
   silently fails despite must_be's raise-on-violation contract
   (type_checks.py:296-354).
2. **F030** — number_chars/number_codes parse via Python `int()`/`float()`
   (chars.py:620-627, 670-677): accepts " 1" (whitespace), "1_0"
   (underscores), "inf"/"nan". Decide: strip-and-reject (ISO-ish) or document
   Python-lenient parsing as intended (language-is-Python contract) — either
   way make it deliberate.
3. **F031** — atom_concat/3 error behaviour is mode-dependent:
   `atom_concat(12,"a",C)` raises type_error(atom,12) (F077 fix) but
   `atom_concat(12,"a","12a")` silently fails (chars.py:444-457 — the bound
   check-mode paths never reach the F077 validation). Run the F077 type
   check on ALL bound args regardless of mode.

## Acceptance

- must_be("nonsense",5) raises domain_error; atom_concat check-mode raises
  the same error as open mode; number-parse decision recorded in
  docs/builtins.md.
