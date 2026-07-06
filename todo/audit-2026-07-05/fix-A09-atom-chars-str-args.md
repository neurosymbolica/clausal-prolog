# fix(A09-F017): atom_chars/atom_codes/number_chars/number_codes reject str/bytes sequence args

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F017
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F017_atom_chars_str_arg, ::test_F017_atom_codes_bytes_arg (xfail — flip to pass), ::test_F017_regression_list_forms_work

## Bug

The Chars/Codes-bound branches demand `isinstance(vc, list)` and raise
type_error("list", …) otherwise (chars.py:354, 396-397, 610-611, 658-659).
Under strings-as-lists a str IS a char list ("abc" ≡ ["a","b","c"]) and under
bytes-as-codes a bytes IS a code list — `atom_chars(A,"abc")` should bind
A="abc" (it is how the forward mode's own output reads back!), and
`atom_codes(A, b"ab")` should bind A="ab".

## Fix direction

Route the sequence arg through `_as_items` (lists.py) instead of the bare
isinstance-list check, in all four predicates (covers str, bytes, ground
Seg*). Element validation logic unchanged.

## Acceptance

- Both xfails pass; list forms regression green; type_error still raised for
  genuinely non-sequence args (42).
