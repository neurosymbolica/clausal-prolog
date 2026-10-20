# fix(A09-F013): char_type/2 digit/space/punct enumeration is ASCII-only while test-mode is Unicode

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F013
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F013_char_type_{digit,space,punct}_consistency (xfail — flip to pass), ::test_F013_regression_alpha_enum_unicode

## Bug

The F072 fix added `_UNICODE_TYPES = {"alpha","alnum","upper","lower","print"}`
(chars.py:109) claiming ASCII "is already exhaustive" for the rest — false
for `digit` (str.isdigit: '٣', '²'…), `space` (NBSP '\xa0'…), and `punct`
('¡'…). Test-mode `char_type('٣',"digit")` succeeds; enumeration
`char_type(C,"digit")` yields only the 10 ASCII digits — the relation is
mode-inconsistent, the exact bug class F072 fixed for alpha.

## Fix direction

Move digit/space/punct into `_UNICODE_TYPES` (BMP walk is cached per type,
<100ms once). `ascii` and `control` genuinely are exhaustive (classifier is
codepoint-bounded) — leave them. Check the C `is_digit` (ISDECIMAL||ISDIGIT)
vs Python `str.isdigit` for residual divergence while there.

## Acceptance

- Three xfails pass; alpha regression stays green; enumeration counts for
  ascii/control unchanged.
