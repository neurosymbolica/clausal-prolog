# tests/fixtures/ — test programs and test data

About 300 `.seam` programs (plus a few `.py`, `.txt`, `.json` and the `.pl`/`.seam`
golden pairs) that the Python tests import and that the root plugin also
collects on their own: each `test/1` clause in a fixture is a pytest item.
There are no `.clausal` (Clausal Prolog) files here; tests that need one write
it under `tmp_path`. Up: [../AGENTS.md](../AGENTS.md).

## How fixtures are reached

- `../../conftest.py` puts this directory on `sys.path`, so a fixture is
  importable by bare name (`import wfs_fact_cycle`) and fixtures can
  `-import_from` each other. Tests also import them as `tests.fixtures.<name>`
  (the import hook compiles `.seam` on import).
- Name a fixture from Python with `tests._suffix.seam_path(...)` /
  `SEAM`, not a hardcoded suffix.
- `python -m pytest tests/fixtures/<name>.seam` runs just that program's
  `test/1` clauses.

## Map

| Files | What they are |
|---|---|
| `builtins_*.seam` | `test/1` suites for builtins by area (arith, call, db, dif, lists, types, ...). |
| `<prefix>_lib.seam` + `<prefix>_use.seam` (and `_owner`/`_importer`, `_a`/`_b`) | Multi-module scenarios: one module exports, another imports. Prefixes: `impexp_` (import/export diagnostics), `impord_` (import ordering), `impclob_` (clobbering an imported predicate), `callsite_` (call-site specialization), `global_atoms_` (atoms are global by spelling), `ia_`/`arimp_`/`atompivot_`/`atomshadow_`, `t4f2_`/`t5b_`/`t6_` (dated plan tasks). |
| `gate_*.seam` | The mutation gate (which loads may write which predicates). |
| `wfs_*.seam`, `tabled_*.seam` | Tabling and well-founded negation. |
| `specialize_*.seam` | The specializer. |
| `z3_*.seam`, `ortools_*.seam`, `pysat_boolean.seam` | Solver bindings. They FAIL, not skip, without `z3-solver` / `ortools` / `python-sat` installed. |
| `deep_index.seam`, `edge_graph.seam`, ... | Codegen subjects pinned by `../golden/*.codegen.txt`. |
| `atom_index_pkg/`, `ia_pkg/`, `ia_reexp/` | Small seam packages (`__init__.seam`) for package-import tests. |
| `docs/` | Snippet sources for `docs/*.md` (`<page>_sigs.txt` display sections, `<page>_examples.seam`, `<page>_sig_tests.seam` tests), pulled into the docs with `--8<-- "tests/fixtures/docs/<file>:<section>"`. Checked by `../test_doc_snippet_integrity.py` / `../test_doc_snippet_coverage.py`. |
| `prolog_golden/` | `.pl` ⇄ `.seam` translator goldens for `../test_prolog_golden.py` / `../test_prolog_import.py`; its `conftest.py` stops them being collected. |
| `spec_target_goldens.txt`, `spec_target_unfold_goldens.json` | Specializer output goldens for `../test_spec_target_is_data.py`. |
| `clause2_bump.py`, `foreign_dispatch_impl.py`, `impexp_pyraiser.py` | Python helpers some fixtures import. |

## Gotchas

- **`# clausal: no-collect`** in the first 30 lines keeps a fixture out of
  collection. About 40 fixtures carry it: support modules and files that are
  meant to be refused at load (diagnostic tests import them and check the
  error). Add the marker to any new fixture that should not load cleanly.
- Fixture comments and `prolog_golden/conftest.py` still say `.clausal` for
  seam files: that is pre-flip (2026-10-02) naming.
- A rename here breaks importers by module name; grep `tests/` for the stem
  (both `tests.fixtures.<stem>` and the bare stem) before renaming.
