# Physical constants and `SI_*` unit vectors are still TitleCase

Filed 2026-09-09 when the SI unit names went lowercase. `clausal/modules/units.py` still
exports 14 physical constants (`SpeedOfLight`, `PlanckConstant`, `ReducedPlanck`,
`BoltzmannConstant`, `AvogadroConstant`, `ElementaryCharge`, `StandardGravity`,
`GravitationalConstant`, `AtomicMassUnit`, `ElectronMass`, `ProtonMass`,
`VacuumPermeability`, `VacuumPermittivity`, `StefanBoltzmann`) and 19 `SI_*` unit vectors
(`SI_Force`, `SI_Velocity`, …) with TitleCase in the name. They are `Quantity` values, not
unit predicates, and are used as identifiers in `.clausal` files
(`-import_from(py.units, [SpeedOfLight, StandardGravity])` in
`tests/fixtures/units_basic.clausal`; the scipy package's `scipy_constants` module mirrors
the same names). `tests/test_units_lowercase_names.py::test_every_unit_is_lowercase` pins
the 14 constants as the only TitleCase `Quantity` exports, so it shrinks when this is done.

**Design question for the operator (not decided here):** what is the lowercase spelling of
a constant? Options seen in the tree:

1. `speed_of_light`, `planck_constant`, `si_force` — plain lowercase like the units; reads
   as a predicate/atom name in Clausal, which is how `metre` reads too.
2. `_SPEED_OF_LIGHT_` — the `-constants` lexical class (`_PI_`), which is what a Clausal
   author would write for a module constant; but these are Python-defined values imported
   through `-import_from`, and the constant-import branch of the directive binds them as
   ground values rather than functors (check that a `Quantity` survives that path).
3. Leave them: they are not unit names and the ruling's examples were unit names.

Whichever is chosen, the same alias mechanism (`_DEPRECATED_UNIT_NAMES` + module
`__getattr__` + the `-import_from` rewrite) extends to them with a second table, and the
`scipy_constants` module must move in the same change (its tests import both).
