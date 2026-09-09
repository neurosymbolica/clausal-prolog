# Remove the deprecated TitleCase unit spellings once nothing depends on them

Filed 2026-09-09 with the change that made the SI unit names lowercase identifiers
(`metre`, `second`, `newton`, `kilometer`, `byte`, …) under the ruling that Clausal
identifiers are lowercase or ALL_CAPS/underscore-led and TitleCase has no role. The
TitleCase spellings (`Metre`, `Second`, `Newton`, …) are kept as deprecated aliases that
warn ("will be removed in a future release"), the same pattern as `Test/1` -> `test/1`. A
deprecation without an exit criterion becomes noise everyone filters.

**What the aliases are:** `_DEPRECATED_UNIT_NAMES` in `clausal/modules/units.py` (83
names: 64 TitleCase units, 14 TitleCase physical constants -> snake_case, 5 American
`kilometer`-family spellings -> `kilometre`) plus the module `__getattr__` that resolves them (warns once per process per name),
the forwarding `__getattr__` in `clausal/modules/py/units.py`, and the units-module branch
of `_handle_import_from_directive` in `clausal/templating/term_rewriting.py` that rewrites
`-import_from(py.units, [Metre])` to `from py.units import metre as Metre` and warns once
per file (`_warn_deprecated_unit_spelling`, `_UNITS_MODULE_PATHS`,
`_deprecated_unit_renames`).

**Exit criterion (measurable):** all of the above, the `TestTitleCaseAliases` class in
`tests/test_units_lowercase_names.py`, and the one fixture deliberately kept on the old
spelling (`tests/fixtures/units_expr_sugar.clausal`) are removed in one change, when (a)
no `.clausal` or `.py` in this repository spells a TitleCase unit name except a single test
that asserts the removal error, and (b) the downstream users of `py.units` have been
migrated (their owners report zero `ClausalDeprecatedSpellingWarning`s naming a unit
across their suites).

**When removed:** `-import_from(py.units, [Metre])` should fail LOUDLY at load (an
ImportError naming the rename, which the units-module branch can raise instead of
aliasing), and `units.Metre` should raise `AttributeError` — not silently resolve to
nothing. The removal date is the operator's call.

**Not in scope:** the scipy package's own `scipy_constants` exports — see
`todo/scipy-constants-module-titlecase-exports-2026-09-09.md`.
