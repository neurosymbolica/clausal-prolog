# fix(A09-F014): char_type/2 char-bound Python fallback is ASCII-table-only

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F014
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F014_char_type_python_fallback_non_ascii (xfail — flip to pass), ::test_F014_regression_char_type_c_path_non_ascii

## Bug

Char-bound, Type-unbound mode: the C helper tests non-ASCII chars dynamically
(_chars_core.c:166-179), but the pure-Python fallback (chars.py:191-197) does
`_CHAR_TO_TYPES.get(vc, [])` over a precomputed ASCII table → on a build
without the C extension, `char_type('α', T)` enumerates NOTHING (C build:
alpha/alnum/lower/print). Latent C-vs-Python divergence.

## Fix direction

In the Python fallback, fall back to testing each `_CHAR_TYPES` classifier
dynamically when `vc` is non-ASCII (mirror the C branch):
`[t for t, fn in _CHAR_TYPES.items() if fn(vc)]`.

## Acceptance

- xfail passes (with `_c_char_type_find_types` monkeypatched to None);
  C-path regression green.
