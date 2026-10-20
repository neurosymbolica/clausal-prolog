# fix(A10-F006): arrow-lambda inner TermTransformer drops source_lines (and atoms)

**Problem.** `_build_arrow_lambda` (clausal/templating/term_rewriting.py:807-811)
constructs the body transformer as
`TermTransformer(import_remap=…, bare_atom_refs=…)` — without `source_lines`
and without `atoms`. Consequence: arrow detection inside lambda bodies falls
back to the column-gap≤2 heuristic, so `X< -3` (a legal Lt guard at top level,
where the exact source check applies) is misparsed as a nested arrow lambda and
the module fails to load with `NotImplementedError: terms_to_goalop … (Lambda)`.
Atoms currently still resolve via module_dict (probed OK), but the omission is
fragile.

**Repro/test.** test_10_rewriting_import.py::test_F006_lambda_body_lt_negative_literal
(xfail); guards ::test_F006_guard_top_level_lt_negative_literal,
::test_F006_guard_lambda_body_spaced_comparison, ::test_F006_guard_module_atom_in_lambda_body.

**Fix.** Pass `source_lines=transformer._source_lines` and
`atoms=transformer.atoms` through to the inner TermTransformer. Audit the
other TermTransformer construction sites for the same omission
(`_StarQueryTransformer._rewrite` in import_hook.py:696 is IPython-only and
has no source lines by nature — document that one).
