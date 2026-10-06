# tests/ — the engine's test suite

Pytest tests for the `clausal` package, plus `test/1` clauses inside `.seam`,
`.clausal` and `.pl` programs that the root plugin turns into pytest items.
About 540 entries at the top level (513 `test_*.py`); a full run is ~23,000 items and
takes about 10 minutes.
The optional `clausal-*` packages have their own suite: see
[../packages/AGENTS.md](../packages/AGENTS.md). Up: [../AGENTS.md](../AGENTS.md).

## Running it

```bash
python -m pytest tests -p no:cacheprovider --timeout-method=signal \
    --continue-on-collection-errors                                     # from the repo root
python -m pytest tests/test_wfs.py -q                                   # one file
python -m pytest tests/fixtures/wfs_fact_cycle.seam                     # one program's test/1 clauses
```

- Run from the repository root with this checkout importable (`pythonpath = ["."]`
  in `pyproject.toml`). `tests/iso/conftest.py`'s `run_clausal` fixture asserts
  `os.getcwd()` is in `clausal.__file__`.
- The session begins by deleting every `__pycache__` in the repo (autouse
  fixture in `../conftest.py`).
- Compare against a baseline run by test name, not by count: failures are
  expected in a bare environment (see Gotchas).

## How source-file tests are collected

[../conftest.py](../conftest.py) is a pytest plugin. Every `.seam`, `.clausal`
and `.pl` file it finds (`clausal._suffixes.SOURCE_SUFFIXES`) is loaded and each
`test/1` (or `test(Name, fail)`) clause becomes one item, e.g.
`tests/fixtures/fibonacci.seam::fib(5) = 5`. A file that fails to load is one
failing `<load>` item. It also collects ```` ```seam ```` blocks in `docs/*.md`
(only when `docs/` is on the command line). Opt-outs:

- `# clausal: no-collect` (`% clausal: no-collect` in `.pl`) in a file's first
  30 lines: the file is support data or is *meant* to fail at load.
- A directory's `conftest.py` with `collect_ignore` / `collect_ignore_glob`
  (used by `iso_l3/`, `iso_diff/`, `fixtures/prolog_golden/`).

The `test/1` convention itself: [../docs/testing.md](../docs/testing.md).

## Map

| Path | What it is |
|---|---|
| `test_*.py` (top level) | Tests by topic; the filename names the feature or the bug. Big families: `test_prolog_*` (the `.pl` ⇄ seam translators `clausal/tools/prolog_to_clausal.py`, `clausal_to_prolog.py`), `test_pl_*` (`.pl` import), `test_seam_*`, `test_import_*`, `test_bytes_*`, `test_clpz*`/`test_clpq*`/`test_clpr*`/`test_clpb*`, `test_reflection_*`, `test_testing_*` (the test runner `clausal.testing`), `test_doc_*` (docs snippets), `test_lint_*`, `*_gate.py` (repo-wide lints). Dated names (`test_triage_batch1_2026_09_28.py`) are regression batches. |
| [fixtures/](fixtures/AGENTS.md) | ~300 `.seam` programs used by the Python tests and collected on their own; also doc-snippet sources and translator goldens. |
| `clausal_modules/` | Small `.seam` modules whose `test/1` clauses are behaviour tests; `test_clausal_modules.py` keeps the Python-level leftovers. |
| `conformity/` | ISO conformity as `iso_*.seam` programs plus Python-level helpers (`test_iso_*.py`). |
| `iso/` | ISO answers checked against Scryer (`*_scryer.py`) and engine-only twins. Its `conftest.py` `scryer` fixture FAILS (not skips) when the binary is missing unless `CLAUSAL_ISO_ALLOW_NO_SCRYER=1`. |
| [iso_l3/](iso_l3/AGENTS.md) | The native `.pl` front end (`CLAUSAL_PL_FRONTEND=native`, `clausal/tools/iso_l3.py`), slice by slice. |
| `iso_diff/` | Differential sweep: area `.pl` files run under the native front end and under Scryer; `KNOWN` table of accepted divergences in `test_iso_diff.py`. Skips without Scryer. |
| `golden/` | Pinned generated Python (`*.codegen.txt`) for `test_tagged_terms.py`; regenerate with `CLAUSAL_REGEN_GOLDEN=1 pytest tests/test_tagged_terms.py -k golden`. |
| `audit_2026_05_25/` | String-audit findings, each `xfail(strict=True)`; a pass means the fix landed, so remove the marker. |
| `audit_2026_07_05/` | Partition-audit suite (`test_00_smoke.py` … `test_12_seams.py`) with leak/refcount fixtures in its `conftest.py`. |
| `rewrite/`, `fmt/` | The `clausal-rewrite` and `clausal-fmt` tools (`clausal/rewrite/`, `clausal/fmt/`). |
| `toklex/` | The table-driven lexer and ISO reader (`clausal/tools/toklex/`). |
| `predmeta_p1/`, `predmeta_p2/`, `shared_rows/` | The migration from `PredicateMeta` classes to Database rows (P1/P2 plans). |
| `value_terms/`, `tuple_tag/` | Python values ⇄ terms (dates, quantities, the `'()'` tuple tag). |
| `tools/` | Tests for repo scripts under `../tools/`. |

Support modules (imported by tests, not tests themselves):

| File | Role |
|---|---|
| `_oracles.py` | The ONE place the Scryer/Trealla paths live (`CLAUSAL_SCRYER`, `CLAUSAL_TREALLA`) and `run_scryer()`. `test_oracle_paths.py` fails if a test hardcodes a path. |
| `_scryer_toplevel.pl`, `_scryer_end_module.pl` | Scryer-side plumbing consulted by `_oracles.py` (no-collect). |
| `_suffix.py` | `SEAM` (the seam extension) and `seam_path()`; write seam files with `SEAM`, never a literal suffix. |
| `_predicate_name_census.py` | Child-process census of Python-registered predicate names, for `test_python_predicate_name_gate.py` (reads `packages/` too). |
| `tagged_terms_support.py`, `predicate_api_support.py`, `load_write_spy_support.py` | Shared helpers (term normaliser; `term_ctor`/`RowPredicate` replacing the retired `make_predicate`; a `Database.mutate` write counter). |

## Where to start

- New behaviour of a builtin or library predicate: add `test/1` clauses to a
  `.seam` fixture or a Python test next to the existing `test_<topic>.py`.
- A test that needs a temporary program: write it under `tmp_path` with the
  suffix from `_suffix.SEAM` (seam) or `.clausal` / `.pl`, and import it.
- An ISO question: prefer an oracle test in `iso/` using the `scryer` fixture.

## Gotchas

- **pytest-timeout**: `pyproject.toml` sets `timeout = 10` with
  `timeout_method = "thread"`; when `pytest-timeout` is installed one slow test
  kills the whole run. Pass `--timeout-method=signal`.
- **Editable install**: with `pip install -e .`, an editable install's RECORD
  makes `test_python_bridges.py::test_engine_shipped` fail; run from a checkout
  on `PYTHONPATH` instead.
- **Optional deps**: z3, OR-Tools and python-sat are not dependencies.
  Without them these `.seam` items FAIL rather than skip: `fixtures/z3_*.seam`,
  `ortools_*.seam`, `pysat_boolean.seam`, and the z3 tests in
  `first_class_constraints.seam`. Python test modules skip
  (`importorskip("z3")` / `("ortools")` / `("pysat")`, `needs_ortools`,
  `needs_pysat`).
- **Bare-environment baseline** (2026-10-06, no z3/ortools/pysat/Scryer,
  before the OR-Tools/pysat test modules skipped): 225 failed, 122 errors,
  22,657 passed. Most are the items above and `iso/`.
- **Scryer binary**: default path in `_oracles.py`; `tests/iso/` fails without
  it (see above), most other `*_scryer.py` tests skip.
- **Line-number pins**: `test_funnel_lint.py`'s `ALLOWLIST` holds line ranges in
  engine files (e.g. `clausal/terms.py`), and `test_doc_snippet_coverage.py`'s
  `_KNOWN_UNCOMPILABLE` holds fence line numbers in `docs/import.md`. Moving
  code or prose above them breaks the test: shift the pin and record why.
- **Stale vocabulary**: before the 2026-10-02 extension flip `.clausal` meant
  seam, so many docstrings here say ".clausal file" for what is now `.seam`.
- `audit_2026_07_05/conftest.py` says "run these PER FILE only — `pytest tests/`
  OOM-SIGKILLs on this box"; that refers to the machine it was written on.
