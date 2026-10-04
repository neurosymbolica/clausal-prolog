# Remove the deprecated TitleCase unit spellings once nothing depends on them

Filed 2026-09-09 with the change that made the SI unit names lowercase identifiers
(`metre`, `second`, `newton`, `kilometre`, `byte`, …) under the ruling that Clausal
identifiers are lowercase or ALL_CAPS/underscore-led and TitleCase has no role. The
TitleCase spellings (`Metre`, `Second`, `Newton`, …) are kept as deprecated aliases that
warn ("will be removed in a future release"), the same pattern as `Test/1` -> `test/1`. A
deprecation without an exit criterion becomes noise everyone filters.
Note that the PRINTED labels (`str()`, `write/1`, `UnitsMismatch` text, predicate `repr`)
changed to the lowercase names in the same change with no alias path — a behaviour change,
recorded in docs/units.md ("Printed labels changed").

**What the aliases are:** `_DEPRECATED_UNIT_NAMES` in `clausal/modules/units.py` (102
names: 64 TitleCase units, 14 TitleCase physical constants -> snake_case, 5 American
`kilometer`-family spellings -> `kilometre`, and -- added 2026-10-04 by ruling D16-X2 --
the 19 SI dimension vectors `SI_Force` -> `si_force`, `SI_Velocity` -> `si_velocity`,
`SI_MagneticFluxDensity` -> `si_magnetic_flux_density`, … whose tests are the
`TestSIDimensionVectors` class in the same test file) plus the module `__getattr__` that resolves them (warns once per process per name),
the forwarding `__getattr__` in `clausal/modules/py/units.py`, and the units-module branch
of `_handle_import_from_directive` in `clausal/templating/term_rewriting.py` that rewrites
`-import_from(py.units, [Metre])` to `from py.units import metre as Metre` and warns once
per file (`_warn_deprecated_unit_spelling`, `_UNITS_MODULE_PATHS`,
`_deprecated_unit_renames`; since 2026-10-04 `_UNITS_MODULE_PATHS` also holds
`clausal.library.units`, the generated facade, which carries the current names only).

**State on 2026-09-10:** a TitleCase identifier in a Clausal position is a load-time
SyntaxError.  A TitleCase unit name used BARE no longer loads; the engine-side witness now
ASSERTS that error — `tests/fixtures/titlecase_unit_spelling_witness.clausal`, checked by
`TestTitleCaseAliases::test_bare_titlecase_unit_name_is_a_syntax_error` in
`tests/test_units_lowercase_names.py`.  The fixture that used to be kept on the old
spelling (`tests/fixtures/units_expr_sugar.clausal`) was renamed to the lowercase names.
Names in an `-import_from(py.units, [...])` list are exempt from the lint, so the alias
path (rewrite + once-per-file warning) is still the only way the old spelling reaches a
file, and it is what downstream still uses.

**Exit criterion (measurable):** all of the above and the alias-path tests in the
`TestTitleCaseAliases` class (and the alias half of `TestSIDimensionVectors`) in
`tests/test_units_lowercase_names.py` are removed in one
change, when (a) no `.clausal` or `.py` in this repository spells a TitleCase unit name
except the witness fixture and the single test that asserts the removal error, and (b) the
downstream users of `py.units` have been migrated (their owners report zero
`ClausalDeprecatedSpellingWarning`s naming a unit across their suites).

**When removed:** `-import_from(py.units, [Metre])` should fail LOUDLY at load (an
ImportError naming the rename, which the units-module branch can raise instead of
aliasing), and `units.Metre` should raise `AttributeError` — not silently resolve to
nothing. The removal date is the operator's call.

**Not in scope:** the scipy package's own `scipy_constants` exports — see
`todo/scipy-constants-module-titlecase-exports-2026-09-09.md`.
