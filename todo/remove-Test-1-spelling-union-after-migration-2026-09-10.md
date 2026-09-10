# Remove the runner's `Test/1` union once nothing can spell it

Filed 2026-09-10 with the change that made a TitleCase identifier in a Clausal
position a load-time SyntaxError (`TITLECASE_IDENTIFIER_SEVERITY = "error"` in
`clausal/templating/term_rewriting.py`).

**What the union is:** `clausal.testing.collect_tests` reads both `test/1` and the
retired `Test/1` spelling, `_test_goal_for_name` calls whichever functor the clause
carries, `_warn_deprecated_test_spelling` in `term_rewriting.py` lints the first
`Test(` clause once per file, the `_TEST_CLAUSE_RE` in `clausal/tools/doc_snippet_check.py`
accepts both spellings, and `clausal/tools/prolog_dialect.py` maps `test` to itself so a
translated `.pl` never says `Test(`.

**State on 2026-09-10:** a `.clausal` file spelling `Test(` no longer loads — the TitleCase
lint raises before the union or the once-per-file lint is reached, so both are unreachable
from source.  The engine-side witnesses now ASSERT that error:
`tests/fixtures/titlecase_test_spelling_witness.clausal` (checked-in fixture) and the
`Test/1` section of `tests/test_testing_cli.py` (`run_file` reports the single `<load>`
failure and the CLI exits 1).  The two fixtures that used to be kept on the old spelling
(`tests/fixtures/tabled_fib.clausal`, `tests/fixtures/builtins_arith.clausal`) were renamed
in the same change.

**2026-09-10, later the same day:** the `packages/*/tests/fixtures` files (103, the bulk of the
`Test(` spellings) were migrated too (`todo/done/packages-fixtures-still-titlecase-2026-09-10.md`),
and `tests/test_titlecase_gate.py` now measures the count: zero TitleCase identifiers in any
Clausal position under `clausal/`, `tests/` and `packages/`, witnesses excepted.  Nothing in this
repository can reach the union any more.

**Exit criterion (measurable):** remove the union, `_warn_deprecated_test_spelling`,
`TEST_DEPRECATED_NAME` and the `Test(` arm of `_TEST_CLAUSE_RE` in one change, when the
downstream owners report zero `Test(` clauses across their trees (each owner replies with
the lint's summary line).  The witnesses stay: the SyntaxError is the language's answer to
the spelling, not the runner's.

**Not in scope:** the TitleCase unit aliases
(`todo/remove-deprecated-TitleCase-unit-names-after-migration-2026-09-09.md`) and the bare
injected runtime aliases
(`todo/remove-bare-injected-titlecase-globals-after-deprecation-2026-09-09.md`).
