# fix(A09-F016): must_be/can_be "list" rejects str — strings-as-lists violation

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F016
**Tests:** tests/audit_2026_07_05/test_09_builtins.py::test_F016_must_be_list_string (xfail — flip to pass)

## Bug

`_check_type` (type_checks.py:310-311): `type_name == "list"` →
`isinstance(term, list)` only. `must_be("list","abc")` raises
type_error(list,"abc") while `is_list("abc")` succeeds (F080 lock-in) —
the two type vocabularies contradict on the language's core Liskov rule.

## Fix direction

Align `_check_type("list", ...)` with `is_list/1`: accept list, str, bytes,
and ground Seg*. Consider adding "chars"/"codes" names mapping to
is_chars/is_codes for completeness.

## Acceptance

- xfail passes; `must_be("list",[1])` still succeeds;
  `must_be("list",42)` still raises.
