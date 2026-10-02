# Rename `dimension_of/2`

Operator, 2026-10-02: `dimension_of/2` wants a better name. It reads as
"the dimension of" a thing but answers a dims DICT, and since the same day
it also answers for a bare number (dimensionless, `{}`), so the name should
say "quantity" or "dims".

## Candidates

- `quantity_dimension/2` -- parallels `quantity_number/2`, `make_quantity/3`
- `quantity_dims/2` -- names what it answers (the dims dict)
- `dimensions_of/2` -- plural, as `dimensions(A)` in the transfer term
- `units_of/2` -- what a reader usually means; but it answers base dims, not
  the unit the value was written in

## Call sites (engine repo, 2026-10-02, `grep -r dimension_of`)

- `clausal/modules/units.py` (definition + registration; 11 occurrences
  with the impl and error contexts) and `clausal/library/units.seam` (export
  list + import, 2) -- 2 files.
- `docs/units.md` (2: the utility list and the predicate table); 2
  historical audit files under `docs/superpowers/audits/` (leave as is).
- tests: `tests/test_units.py`, `tests/test_nonpy_adapters_raise.py`,
  `tests/test_units_lowercase_names.py` (pins the public name set),
  `tests/fixtures/units_basic.clausal` -- 4 files, 17 occurrences.
- `packages/`: none.

Downstream program trees were NOT censused (outside this repo); a rename
should keep `dimension_of/2` as a deprecated alias with a warn-once, as the
TitleCase unit aliases did, until a downstream census says it is unused.
