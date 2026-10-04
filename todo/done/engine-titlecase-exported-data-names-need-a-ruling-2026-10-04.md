# Engine modules export 22 TitleCase data names -- needs a ruling

Found 2026-10-04 by the registry name gate's new DATA-name reading
(`tests/_predicate_name_census.py`, `tests/test_python_predicate_name_gate.py`):
`-import_from` compiles to `from M import name`, so it offers every public
attribute, and it exempts a TitleCase name from its variable check -- the hole
`scipy_constants` (`SpeedOfLight`, ...) sat in. The package names are renamed;
these are ENGINE names, held in `_ENGINE_DATA_PENDING_RULING` (exact list: a
new one or a stale one fails the gate) instead of renamed.

- `clausal.modules.prolog`: `TruncDiv/2`, `TruncMod/2`, `Rem/2` -- plain
  functions (term constructors / qualified operator helpers). The `.pl`
  translator emits `prolog.TruncDiv` etc. (`clausal/tools/clausal_to_prolog.py`
  maps them back to `//`), and `term_rewriting` names `prolog.TruncDiv` as a
  supported qualified form. A rename touches the translator's tables.
- `clausal.modules.units`: 19 `SI_*` derived-unit vectors (`SI_Force =
  newton(1)`, `SI_Velocity = metre(1) / second(1)`, ...).
  `clausal/library/units.seam` imports all of them. They are NOT among the 83
  retired TitleCase unit spellings (`_DEPRECATED_UNIT_NAMES`, served by the
  module `__getattr__` with a warning), which the gate does not count.

Question: rename (to what? `si_force`, ... and `trunc_div`, `trunc_mod`, `rem`
-- `rem` would meet the ISO evaluable `rem/2`), with or without the warned-alias
mechanism the units module already has, or rule them exempt.
Blocks nothing; when ruled, edit the list in the gate test.

## Ruled and done 2026-10-04 (D16-X2)

- `prolog.TruncDiv/TruncMod/Rem` -> private `_trunc_div`, `_trunc_mod`,
  `_rem`, NO aliases. Nothing emitted them any more (both `.pl` front ends
  write the quoted ISO evaluables since 2f8c12b6); the exporter's reverse
  mapping and the translator's `-import_module(prolog)` preamble went with
  them.
- `units.SI_*` -> `units.si_*` (snake_case), the old names warned aliases
  in `_DEPRECATED_UNIT_NAMES`; added to
  `todo/remove-deprecated-TitleCase-unit-names-after-migration-2026-09-09.md`.
- The gate's `_ENGINE_DATA_PENDING_RULING` list was emptied and then
  DELETED: an engine TitleCase data name now fails like any other
  (`test_control_an_engine_titlecase_data_name_fails`).
