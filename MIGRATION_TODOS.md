# Migration TODOs

Outstanding issues deferred from Phase 1 and Phase 2. Not blockers — the
suite is green against baseline — but worth a sweep pass before claiming
the migration complete.

## Duplication between new .clausal tests and sibling fixtures

The dedup report grew across migrations (86 → 89 groups, 1562 → 1637 copies
of duplicate .clausal Test bodies) because new Test clauses were added to
the most topically-obvious file without cross-referencing the rest of the
tree.

- **Sign/Gcd/DivMod** tests added to `iso_arithmetic.clausal` likely
  overlap `builtins_arith.clausal`.
- **pairs_keys_values/_keys/_values** tests in `phase5_builtins.clausal`
  may overlap existing pair fixtures (if any).
- General consolidation pass: walk `DUPLICATE_TESTS.md`, pick the
  canonical home for each duplicated body, delete the rest.

Action: ~30 minutes of `DUPLICATE_TESTS.md` grooming.

## `list_patterns_edge_cases.clausal` re-declares library predicates

The new fixture re-declares `CaptureAll`, `ThreeAndRest`, `HeadTail`, etc.,
which already live in `tests/clausal_modules/{list_edge_cases,anon,multistar}.clausal`.
If the library definitions drift, the tests silently pass against a stale
copy.

Action: replace inline definitions with `-import_from(list_edge_cases, [...])`
(or equivalent for each module). Requires checking that the library modules
use `-module` declarations.

## Unused-import sweep across slimmed test files

Spot checks after Phase 2 slim found many orphan imports (e.g.
`test_exceptions.py` had 16). Cleaned up in:

- `tests/test_builtins.py`
- `tests/test_exceptions.py`
- `tests/conformity/test_iso_term_manipulation.py`

Not yet swept across the whole tree. Run
`python -c "..."` ref-check (see commit `ebe0e10` discussion) over
every `tests/**/test_*.py` that was modified since the migration started.

Action: ~10 min global sweep with `ruff --select F401 tests/`.

## `test_mutable_dict_set.py` was classified without being read

10 tests, marked "keep as infra" in `MIGRATION_STATUS.md` without
actually opening the file. Might contain behavior tests exercising
`dict_put!` / `set_add!` mutations that could go to `.clausal`.

Action: open the file, spot-check intent.

## `.clausal` tests without `# nv` annotation

The original annotation pass covered every Test clause in `.clausal` files
at the time. Test clauses added since (in `list_patterns_edge_cases.clausal`,
`phase5_builtins.clausal`, `io_to_string.clausal`, `catch_test.clausal`
extensions, `dict_set_builtins.clausal` extensions, `term_inspection.clausal`
extensions, `iso_arithmetic.clausal` Sign/Gcd/DivMod block, `iso_database.clausal`,
and the Phase-1 additions to other iso files) have `# nv` on the ones I
added by hand — not comprehensively.

Action: re-run `python scripts/test_audit/annotate_clausal.py` (script is
idempotent — it skips clauses that already have the marker).

## V2-2 dispatch staleness after assertz

`iso_database.clausal` worked around a real bug: `findall(X, Pred(X), L)`
with an unbound first argument observes stale compiled dispatch after a
runtime `assertz(Pred(...))` of a new clause. I documented this in the
file header and routed tests to use direct-membership queries instead of
findall+comparison. The underlying bug is not fixed.

Action: open an issue / ROADMAP entry for V2-2 + assertz interaction.
Non-trivial to fix (involves groundness-keyed dispatch invalidation).

## `_load_module`-per-test files — full migration deferred

Three Phase-3 files use the same idiom: each test dynamically builds a
`.clausal` source string, writes it to a temp file, loads it, then
introspects `module_dict` or calls predicates.

- `test_regex.py` (53 migratable tests) — covered by `regex_basic.clausal`
  + `regex_autobind.clausal`
- `test_dcg.py` (56 tests) — `dcg_grammar.clausal` is thin (5 tests)
- `test_edcg.py` (28 tests) — `edcg_counter.clausal` is thin

The scaffolding is arguably *integration infra* (exercising the import
hook + DCG/EDCG/regex compile passes), but the bulk of each test is
plain Clausal behavior. Proper migration = design a matrix of small
grammar/pattern fixtures with Test clauses covering the same matrix of
inputs. Significant effort, medium-priority.

## No full git history for the migration

One atomic commit (`ebe0e10`) bundles: audit tooling + `# nv` annotations
+ Phase 1 + Phase 2. Future phases should commit per-phase so the diff
stays reviewable.
