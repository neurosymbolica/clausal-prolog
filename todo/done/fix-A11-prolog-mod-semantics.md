# fix(A11-F020): Prolog `mod` translated with `rem` semantics (docstring inverts ISO)

ISO 13211-1 §9.1.3: `mod` is FLOORED (sign follows divisor): `-7 mod 3 =:= 2`.
`clausal/modules/prolog.py:27-37` implements TruncMod ≡ Rem (truncating,
`TruncMod(-7,3) = -1`) and its docstring claims "ISO mod: sign follows
dividend" — that is `rem`. Python `%` already IS ISO mod, so `mod` needs no
qualified helper at all (`iso_prolog_compatibility_report.md:242` even says
`X mod Y` → `X % Y`, contradicting its own :253 and the code).

**Fix** (A11-D009): translate `mod` → Python `%`; keep `rem` as the
trunc-remainder helper (int-exact, see fix-A11-prolog-truncdiv-bignum.md);
fix the docstring and the compat report.

**Test**: test_F020_mod_is_floored (xfail).
