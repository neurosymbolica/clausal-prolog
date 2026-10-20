# fix(A10-F012): malformed -private / -module arguments are silently ignored

**Problem.** `-private(helper(X))` (missing list) hits
`_handle_private_directive`'s `export_list is None` branch
(term_rewriting.py:2797-2800) and silently becomes `Pass()`; `-module` with a
non-Name module name (e.g. a string) or a non-list export arg silently drops
those parts (:2748-2751). Every other directive
(`-import_from`, `-overwrites`, `-edcg_*`, `-translations`, pred/arity
directives) raises SyntaxError on malformed arguments. A dropped `-private`
declaration means the predicate signature is later inferred from the first
clause — subtly different field names, no warning.

**Repro/test.** test_10_rewriting_import.py::test_F012_malformed_private_raises,
::test_F012_malformed_module_exports_raise (xfail); guards
::test_F012_guard_unknown_directive_raises, ::test_F012_guard_import_from_arity_errors.

**Fix.** Raise SyntaxError with the expected shape in both handlers:
`-private requires a list: -private([atom, pred(A, B), …])`;
`-module requires a name and an export list: -module(name, [ …])`. Also
consider rejecting non-Name/non-Call items inside the lists (currently
silently skipped by the isinstance chain).
