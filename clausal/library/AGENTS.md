# clausal/library/ — generated `library(...)` facades over the Python modules

Clausal Prolog (`.clausal`) may not import Python modules directly. It reaches
them through these `.seam` files, imported Scryer-style:
`:- use_module(library(datetime), [date_add/3]).` Each facade is a pure
re-export (a `-module(...)` export list plus `-import_from(clausal.modules..., [...])`)
of one module under [../modules/](../modules/AGENTS.md): its predicates
(same names and arities) and its values (units, currencies, numbers). No
clauses of its own. A `.pl` can also use them.

Up: [../AGENTS.md](../AGENTS.md)

## Map

| Path | Wraps | Notes |
|---|---|---|
| `<name>.seam` (`datetime`, `json`, `re`, `hash`, `hmac`, `http`, `logging`, `pbkdf2`, `sqlite`, `tcp`, `url`) | `clausal.modules.py.<name>` | `py/` level dropped |
| `py_<name>.seam` (`py_csv`, `py_files`, `py_os`, `py_process`, `py_random`, `py_uuid`) | `clausal.modules.py.<name>` | prefixed because Scryer has a `library(<name>)` of its own |
| `units.seam`, `imperial.seam`, `currency.seam`, `graphs.seam`, `reflection.seam` | `clausal.modules.<name>` | |
| `countries/<jurisdiction>.seam` (181) | `clausal.modules.countries.<j>` | values only (currencies, minor units) |
| `__init__.py` | — | **Hand-written.** `SCRYER_LIBRARIES` (names a facade must not take), `facade_path()` (`os` -> `py_os`), `is_value()` (what counts as a re-exported value). |
| `countries/__init__.py` | — | Hand-written package marker. |

Related outside this folder: `clausal/_py_facades.py` (generated, import-free
tuple `PY_FACADE_LIBS` of every facade name).

## How it works

- Generator: [`../tools/gen_library_facades.py`](../tools/gen_library_facades.py). Predicates come from `clausal.logic.solve.module_signatures`, values from `clausal.library.is_value`. Modules with neither (`prolog.py`, the `countries` package) get no facade; `py/units.py`/`py/imperial.py` share the top-level module's facade.
- Resolution: `iso_l3_directives._library_facade` (native front end; the translator in `prolog_to_clausal.py` calls the same function). A library the front end already knows (`lists`, `clpz`, `reif`, ...) is never shadowed by a facade.
- Import policy for `.clausal` importers (facades and other engine-shipped files are allowed): `clausal/python_bridges.py`.

## Common tasks

```sh
python -m clausal.tools.gen_library_facades           # regenerate after changing clausal/modules
python -m clausal.tools.gen_library_facades --check   # exit 1 on drift
python -m clausal.tools.gen_library_facades --census  # module -> library(...) table
```

`--modules DIR --out DIR` point it at an extension package's modules and a facade directory of its own.

## Gotchas

- Every `.seam` here and `clausal/_py_facades.py` are GENERATED (header says so): never hand-edit; regenerate. The generator deletes facades whose module no longer exists. `tests/iso_l3/test_l3_library_facades.py` fails on drift.
- Changing a public predicate or value in `clausal/modules` (including regenerating currencies with `scripts/gen_currencies.py`) requires regenerating facades.
- Adding a name to `SCRYER_LIBRARIES` renames that facade to `py_<name>` and breaks existing `library(<name>)` imports.
- No extension package under `packages/` currently ships facades, so their `py/` wrappers are not reachable from `.clausal` via `library(...)`.

## Docs

[../../docs/clausal_prolog.md](../../docs/clausal_prolog.md), [../../docs/importing_prolog.md](../../docs/importing_prolog.md), [../../docs/for_prolog_programmers.md](../../docs/for_prolog_programmers.md).
