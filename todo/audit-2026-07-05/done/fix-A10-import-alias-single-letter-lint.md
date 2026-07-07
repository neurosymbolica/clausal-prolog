# fix(A10-F017): -import_from alias to a logic-var-shaped name should fail at the directive

**Problem.** docs/import.md documents that alias names must be TitleCase
("Single uppercase letters like R are treated as logic variables … will not
work"), but `_handle_import_from_directive` (term_rewriting.py:2954-2966)
accepts `alias(twice, T)` without validation. The remap entry for `T` is
unreachable (`visit_Name` checks `_is_logic_var_name` first), so the module
loads and the call site fails later with
`NotImplementedError: terms_to_goalop … Call(func=AttVar…)` — the same class
of late failure as the mixed-case-name trap
(todo/audit-tests-input-output-mode-coverage.md meta-finding).

**Repro/test.** test_10_rewriting_import.py::test_F017_single_letter_alias_rejected_at_load
(xfail); guard ::test_F017_guard_titlecase_alias_works.

**Fix.** In the alias branch: `if _is_logic_var_name(local_name): raise
SyntaxError(f"-import_from alias {local_name!r} is a logic-variable name; "
"use a TitleCase alias (e.g. Reach)")`. Same check for plain (non-alias)
import names is unnecessary (they name real predicates) but harmless.
