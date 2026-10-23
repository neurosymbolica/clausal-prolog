# An exported constant declaration pairs the BASE magnitude with the DECLARED unit

**Status: FIXED 2026-10-23 (commit 5fbfcdc7).** Operator ruling
2026-10-23 ("all as recommended"): option 1, the export declares the pair as written
(`155000, usd_cent`), as the engine's constant_number_units/3 reports it; use sites still fold
to the base value. The ISO `facts` form now writes `constant_number_units/3` and
`module_constant_units/4` facts, the same two the Scryer/Trealla preludes expand the directive
into, with currency recorded under `constant_number_units`, so the accessor answers in every
dialect. Pinned in tests/test_prolog_constants_prelude.py::test_the_exported_program_answers_what_the_engine_answers,
::test_every_dialect_declares_the_pair_as_written and
::test_the_exporters_own_output_runs_unmodified, and
tests/test_exporter_constants_dialect.py::test_the_iso_FACTS_form_runs_and_answers_the_pair.

Filed 2026-10-22, found fixing the expansion preludes so that
`constant_number_units/3` answers in an exported module. Severity: high once
the accessor is used (a 100x wrong pair for a minor unit); needs a ruling.

## What / Repro

```seam
-module(sc, [look(N, U)])
-import_from(united_states, [usd_cent])
-constant_number_currency(cap, 155000, usd_cent)
look(N, U) <- constant_number_units(cap, N, U)
```

Engine: `look(N, U)` -> `N = 155000, U = usd_cent`, the DECLARED pair
(operator ruling 2026-09-11, `register_constant_units`).

Export (scryer): `:- constant_number_currency(cap, 1550.00, usd_cent).`, so the
exported `look/2` answers `1550.0, usd_cent`: 1550 cents, not 155000. The
exporter scales the declaration to the base magnitude on purpose
(`_collect_constant`, option 3 of
`docs/superpowers/specs/2026-09-13-exporter-option-3-design.md`; pinned by
`tests/test_prolog_constants_prelude.py::test_the_exporters_own_output_runs_unmodified`),
but keeps the declared unit, so the pair is neither the declared one nor the
base one. Use sites are not affected: they fold separately to the base value.

Pre-existing for `constant_number_units` under Trealla and in a module-less
Scryer program; reachable from inside a named Scryer module, and for
currency constants, since the 2026-10-22 prelude fix.

## Options

1. Declare the DECLARED pair (`155000, usd_cent`), as the engine reports it.
   Use sites already fold to the base value on their own. Changes the pinned
   test above. Recommended.
2. Declare the BASE pair (`1550.00, usd`): consistent, but not what the
   engine's `constant_number_units/3` answers.

## Also: the `facts` capability has no accessor

Under `Dialect.iso()` (constants capability `facts`) the declaration crosses
as a 4-ary fact, `constant_number_units(m, name, N, U)` or
`constant_number_currency(m, name, N, U)`, and nothing defines
`constant_number_units/3`, so a body call to it raises existence_error.
The expansion dialects record a currency declaration under
`constant_number_units` (as the engine does); the facts form still spells it
`constant_number_currency/4`. Making the two agree (emit currency as a
`constant_number_units/4` fact, and/or emit a module-local 3-ary accessor)
is part of the same decision.
