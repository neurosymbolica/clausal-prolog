# packages/ — the optional `clausal-*` distributions

Each `clausal-<name>/` is a separately installable distribution (its own
`pyproject.toml`, `docs/`, `tests/`) that adds modules to the engine's
namespaces. `pip install clausal` ships none of them. They live in this repo
and depend on `clausal>=0.3.1`. User-facing overview:
[../docs/packages.md](../docs/packages.md). Up: [../AGENTS.md](../AGENTS.md).

## Map

Library wrappers. Each puts Python modules under
`clausal-<name>/clausal/modules/py/`, so they import as `clausal.modules.py.<x>`;
seam code imports them as `-import_from(yaml, [...])` (rewritten to `py.yaml`).

| Package | Modules | Required third-party deps |
|---|---|---|
| `clausal-scipy` | `scipy_<sub>.py` (linalg, optimize, stats, fft, sparse, spatial, ...) + `_scipy_units.py`, `_scipy_relations.py` | numpy, scipy |
| `clausal-jax` | `jax.py`, `jax_<sub>.py` (nn, random, transforms, tree, sharding, scipy, optax, flax, equinox) | jax, jaxlib, numpy (extras: optax, equinox, flax) |
| `clausal-torch` | `torch.py`, `torch_{nn,functional,data,distributions}.py` | torch |
| `clausal-sklearn` | `sklearn.py` | scikit-learn (extra `csv`: pandas, for `load_csv/3`) |
| `clausal-opencv` | `opencv.py`, `opencv_<sub>.py`, `_opencv_handles.py` | numpy, opencv-python<5 (OpenCV 5 moved KAZE/AKAZE/BRISK, HOG, cascades to contrib) |
| `clausal-spacy` | `spacy.py` | spacy |
| `clausal-sympy` | `sympy.py` | sympy |
| `clausal-yaml` | `yaml.py` | pyyaml |

Prolog backends. Each adds a package `clausal.<name>` (outside `modules/`) that
embeds a real ISO Prolog; they have no Python deps but need a native build:

| Package | Package | Native part | Tests skip unless |
|---|---|---|---|
| `clausal-scryer` | `clausal/scryer/` | Rust/PyO3 (`src/lib.rs`, `Cargo.toml`; `maturin develop --release`) | extension built; `scryer-prolog` on PATH |
| `clausal-trealla` | `clausal/trealla/` | ctypes over `libtpl.so` (build from trealla-prolog source) | library built; `tpl` on PATH |
| `clausal-gprolog` | `clausal/gprolog/` | C extension `_gprolog_ext.c` (needs `GPROLOG_HOME`; see its `__init__.py`) | extension built |

`clausal-provenance` (`clausal/modules/provenance/`, a bottom-up Datalog engine
with semirings) is **DISABLED** since 2026-09-25: importing
`clausal.modules.provenance` raises `ImportError`, and
`clausal-provenance/tests/conftest.py` ignores every test. Reason and redesign
note: `clausal-provenance/README.md`.

## How they reach the engine

- Installed: `clausal/modules/__init__.py` and `clausal/modules/py/__init__.py`
  append site-packages dirs and setuptools editable-finder `NAMESPACES` entries
  to their `__path__`. The packages ship no `__init__.py` at `clausal/`,
  `clausal/modules/`, `clausal/modules/py/` (PEP 420 namespace dirs).
- In this repo, uninstalled: [conftest.py](conftest.py) splices every
  `packages/*/clausal{,/modules,/modules/py}` dir onto `clausal.__path__`,
  `clausal.modules.__path__`, `clausal.modules.py.__path__` right after the
  engine's own entry. It refuses (`UsageError`) if `clausal` was imported from
  anywhere but this checkout.

## Running the suites

```bash
python -m pytest packages -p no:cacheprovider --timeout-method=signal   # from the repo root
python -m pytest packages/clausal-yaml                                   # one package
```

- Run it in its OWN session. The splice is process-wide, so `conftest.py`
  raises `UsageError` if the session also collects anything outside `packages/`
  (e.g. `pytest tests packages`).
- A package whose REQUIRED dependency is not importable is skipped as a whole,
  with the missing distribution named. A failure caused by a
  `ModuleNotFoundError` for an absent declared dependency is reported as a
  skip. Test modules named `*_stubbed.py` install a fake dependency and always
  run.
- Per-package test layout: `tests/test_<pkg>_*.py`; for the library wrappers
  `tests/fixtures/*.seam` (collected by the root `../conftest.py` plugin,
  `test/1` clauses) and mostly `tests/fixtures/docs/` (doc snippet sources); and
  `tests/test_<pkg>_doc_integrity.py` (checks `docs/` with
  `clausal/tools/doc_snippet_check.py`).

## Releasing to PyPI

[`../.github/workflows/packages-release.yml`](../.github/workflows/packages-release.yml)
publishes one package per tag: bump `version` in its `pyproject.toml`, merge,
then push a tag `clausal-<name>-v<version>` (e.g. `clausal-yaml-v0.1.0`). It
builds the wheel, runs the package's tests against the engine from the same
commit with the package installed from that wheel, and publishes via PyPI
trusted publishing. Run it by hand to build and test without publishing.

- Only the pure-Python library wrappers are publishable (the workflow's
  `PUBLISHABLE` list). gprolog and scryer need native wheels, trealla needs
  `libtpl` built from source, and provenance is disabled.
- Before a package's first release, its project name needs a pending trusted
  publisher on pypi.org (workflow `packages-release.yml`, environment `pypi`).
- Once a package is on PyPI it can become an extra of `clausal` again
  (`[project.optional-dependencies]` in the root `pyproject.toml`).

## Gotchas

- A `*_stubbed.py` test runs without the package's dependencies, so the
  adapter must import them lazily (inside the function), never at module
  level -- one module-level import makes the stubbed tests error at
  collection and stops the whole `pytest packages` run.
- With every library installed (2026-10-06: numpy 2.5, scipy 1.18,
  scikit-learn 1.9, jax 0.11, torch 2.14, spaCy 3.8 + `en_core_web_sm`,
  OpenCV 4.14, pandas) the suite is 4809 passed; the skips left are the
  Scryer/Trealla/GNU Prolog backends, which need their native builds.
- The engine suite reads these sources too: `tests/test_python_predicate_name_gate.py`
  (via `tests/_predicate_name_census.py`) imports every
  `packages/*/clausal/modules/` module in a child process and rejects
  TitleCase predicate names. Predicate names are lower_snake_case; the
  2026-10-02 renames are listed in `docs/RENAMES.md` of scipy, sklearn, spacy
  and sympy.
- `clausal-opencv/tests/conftest.py` copies its PNG fixtures into `/tmp` for
  the session; its `.seam` fixtures use those absolute paths.
