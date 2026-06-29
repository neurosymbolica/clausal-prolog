# Big Rename Reference Index

This directory mirrors `/workspace/clausal/implementation_plans/big_rename/results/`.
Each `.md` file documents the TitleCase names found in the corresponding source file,
classified as: renamed, possibly-missed, Python class, user predicate, or other.

**Result files processed:** 526  
**Reference files written:** 526  
**Skipped (no TitleCase matches):** 0

## Classification Legend

| Category | Meaning |
|----------|---------|
| **Renamed** | Builtin predicate correctly renamed from TitleCase to snake_case |
| **POSSIBLY MISSED** | Builtin predicate still TitleCase in renamed file — verify |
| **Kept — Python class** | Class defined in bigrename — intentionally TitleCase |
| **Kept — user pred** | User-defined predicate in .clausal/.pl — not a builtin |
| **Kept — other** | Natural language, comment, stdlib type, or non-predicate |

## Possibly Missed Renames

**23 (file, name) pairs** where a builtin predicate may not have been fully renamed:

| File | Predicate Name |
|------|----------------|
| `clausal/examples/lambdas.clausal` | `CallGoal` |
| `clausal/logic/builtins/higher_order.py` | `CallGoal` |
| `clausal/logic/builtins/translations_builtin.py` | `Translate` |
| `clausal/tools/clausal_to_prolog.py` | `Translate` |
| `clausal/tools/prolog_to_clausal.py` | `Translate` |
| `clausal/tools/translate.py` | `Translate` |
| `docs/builtins.md` | `CallGoal` |
| `docs/coroutining.md` | `CallGoal` |
| `docs/directives.md` | `Labeling` |
| `docs/exceptions.md` | `CallGoal` |
| `docs/for_ai_agents.md` | `Labeling` |
| `docs/for_prolog_programmers.md` | `Labeling` |
| `docs/for_python_programmers.md` | `Labeling` |
| `docs/higher_order.md` | `CallGoal` |
| `docs/lambdas.md` | `CallGoal` |
| `docs/meta_predicates.md` | `CallGoal` |
| `docs/prolog_translation.md` | `Translate` |
| `docs/syntax.md` | `CallGoal` |
| `tests/clausal_modules/lambdas.clausal` | `CallGoal` |
| `tests/conformity/test_iso_arithmetic.py` | `CallGoal` |
| `tests/fixtures/translations_basic.clausal` | `Translate` |
| `tests/test_lambdas.py` | `CallGoal` |
| `tests/test_meta.py` | `CallGoal` |

## Directory Structure

- [`clausal/`](clausal/) — main source and stdlib
- [`tests/`](tests/) — test files
- [`docs/`](docs/) — documentation
