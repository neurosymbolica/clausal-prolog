# `packages/*/tests/fixtures` still spell TitleCase heads (`Test(`, `Edge`, `Path`, `Reachable`, `Zero`)

Left out of the 2026-09-10 snake_case migration (`feat/titlecase-is-an-error-2026-09-10`)
because those optional-dependency packages' suites are dark in this environment (their
collection errors are identical on the baseline, so the migration's name-set diff could not
see them). 103 fixture files still use `Test(` heads plus a handful of TitleCase predicates.

Under the landed error severity, any environment WITH those dependencies installed will fail
to load them (loud SyntaxError naming the rename) — correct behaviour, but a surprise for
whoever runs those suites next. Migrate them with the same tools the main pass used
(`census.py` / `rename.py` shapes: rename in `.clausal`, then the Python references, then
regenerate any goldens and READ the diff), run their suites in an environment that has the
packages, and confirm 0 `ClausalTitleCaseIdentifierWarning`/errors.

---

**CLOSED 2026-09-10, same branch.** Swept with the main pass's tools: 103 `.clausal`
fixtures (14 identifiers, `Test` -> `test` dominant), 25 package doc pages (388 sites in
Clausal blocks / inline code) and 55 package Python test files (inline sources, whole-string
and attribute references).  Verified without the optional dependencies by running every
package `.clausal` through the EmbedTransformer (`_parse_clausal_source`): 0 TitleCase
reports, 0 other errors; the package doc blocks report 0 TitleCase names (the 47 that fail
to compile did so before, for the missing dependencies).  The number is now MEASURED, not
assumed: `tests/test_titlecase_gate.py` runs the lint over every `.clausal` under `clausal/`,
`tests/` and `packages/` and asserts zero offenders apart from the two witnesses, with a
positive control on the walk and on the instrument.  Still to do by whoever has the
dependencies: run the package suites once (the Python-side references were renamed by tool,
not by a green run).
