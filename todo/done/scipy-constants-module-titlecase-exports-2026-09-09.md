# The scipy package's `scipy_constants` module still exports TitleCase names

Filed 2026-09-09 when the units module's physical constants went snake_case
(`speed_of_light`, …) with the TitleCase names as warned aliases.
`packages/clausal-scipy/clausal/modules/py/scipy_constants.py` defines its OWN constants
from `scipy.constants` under TitleCase names (`SpeedOfLight`, `PlanckConstant`,
`ReducedPlanckConstant`, `GravitationalConstant`, `AvogadroConstant`, `BoltzmannConstant`,
`ElementaryCharge`, `ElectronMass`, `ProtonMass`, `ElectronVolt`, `StandardAtmosphere`,
`Pi`, `Kilo`, `Mega`, `Giga`) — a separate API, not uses of the units module's names — and
its tests, fixture (`scipy_constants_tests.clausal`), docs page and generated signature
files (`tests/fixtures/docs/scipy_constants_sigs.txt`) all spell them that way.

Not renamed in that change because the package is not importable in the engine
environment (its `clausal.modules.py.scipy_constants` namespace is uninstalled, so its
suite is dark) and the signature fixtures would need regenerating. Same ruling applies
(TitleCase has no role): rename to snake_case, keep the old names as warned aliases with
the same `__getattr__` + `-import_from` mechanism (`_deprecated_unit_renames` keys on the
module path, so the scipy module needs its own table and path entry), regenerate the
signature fixtures, and run its suite where scipy is installed.

**Done 2026-10-04** (ruled the same day, D13 W4): renamed to lower_snake_case
with a `scipy_` prefix and NO aliases (the plain spellings collide with
`py.units`' `speed_of_light`, `kilo`, ... and the arithmetic `pi`); table in
`packages/clausal-scipy/docs/RENAMES.md`. The registry name gate now reads
exported data names too, so a TitleCase constant fails it.
