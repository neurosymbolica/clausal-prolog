# Package Extraction Plan

Clausal has grown into a monorepo: a relational core plus bridges to three
Prolog engines (GNU Prolog, Scryer, Trealla) and ~50 wrapper modules for
third-party Python libraries (scipy, torch, jax, sklearn, sympy, spacy, ...).
Depending on all of this is wrong for most users. This plan extracts the
optional pieces into separately-published PyPI distributions so that
`pip install clausal` pulls only the core, and each wrapper / bridge is an
opt-in install.

Status: **planning only — no code changes in this plan.**

---

## 1. Goals

1. `pip install clausal` installs a small core: the DSL, import hooks,
   unifier, indexer, stdlib `.clausal` library, standard control/meta
   predicates, the built-in Python interop (`++()`, class terms, `py.`
   modules that wrap only the Python stdlib).
2. External-library wrappers (scipy, torch, jax, sklearn, sympy, spacy,
   yaml, sqlite bindings, ...) live in their own distributions. Installing them
   also makes them discoverable by `import_from(py.<name>, ...)` without
   users having to edit Clausal configuration.
3. External Prolog engine bridges (gprolog, scryer, trealla) live in their
   own distributions with their own native-build requirements. Installing
   them registers the backend with Clausal's Prolog-import machinery.
4. Every subpackage builds, versions, tests, and ships independently on
   PyPI. Core can be released without waiting on, say, a torch-API bump.
5. A convenience metapackage `clausal[everything]` (or `clausal-all`)
   re-pulls the common set for users who want today's install experience.

Non-goals for this plan:

- Renaming or redesigning individual wrapper APIs — they move as-is.
- Changing `.clausal` syntax or the import-hook user surface. From a user
  perspective the only change is `pip install clausal-torch` instead of
  getting torch support out of the box.
- Splitting the Prolog-source stdlib (`clausal/stdlib/*.clausal`) — it
  stays inside the core.

---

## 2. Current Shape (facts, not plan)

Top-level `clausal/` package contains:

| Area | Path | External deps |
|---|---|---|
| Core runtime | `terms.py`, `codegen.py`, `import_hook.py`, `_lazy_hook.py`, `logic/`, `pythonic_ast/`, `pythonic_terms.py`, `templating/`, `testing.py`, `__main__.py`, `repl.py`, `python_repl.py` | none (greenlet) |
| Stdlib (Clausal source) | `stdlib/*.clausal` | none |
| Translation tools | `tools/` (prolog ↔ clausal, dump, visualize) | none |
| Built-in example modules | `modules/*.py` (csv, json, os, random, re, uuid, sqlite, tcp, http, url, hash, hmac, pbkdf2, log, date_time, files, process, graphs, yaml_module, sympy_module, spacy_module, imperial, units, scipy_*) | **mixed** |
| `py.` wrapper layer | `modules/py/*.py` (~58 files) | **mixed — heavy** |
| Shared wrapper infra | `modules/py/_helpers.py` (~460 LOC) | stdlib only, but used by jax/torch/numpy wrappers |
| GProlog bridge | `clausal/gprolog/` + `prolog_backends/gprolog/` (C ext) | gprolog binary |
| Scryer bridge | `clausal/scryer/` + `prolog_backends/scryer/` (Rust ext) | scryer-prolog |
| Trealla bridge | `clausal/trealla/` | trealla (pip) |
| Regex helper | `clausal/regex.py` | stdlib |
| Examples | `clausal/examples/` | various |

`prolog_backends/{gprolog,scryer}/` already have their own `pyproject.toml`
scaffolds — the split was started but not finished (they do not yet build
standalone wheels that register with a published `clausal` core).

`clausal/modules/py/` totals ~19 kloc, dominated by `jax.py` (1399),
`jax_equinox.py` (746), `jax_optax.py` (477), `torch.py` (1169),
`sympy.py` (1297), `sklearn.py` (1284), and ten `scipy_*` files. The
ten JAX files alone add ~4.7 kloc. These import heavy third-party
libraries lazily but the *files* always ship.

Pyproject currently declares only two optional extras: `spacy`, `ptpython`.

---

## 3. Target Distribution Layout

### 3.1 Core — `clausal`

Ships:

- `clausal/` minus the extracted subtrees listed below
- `clausal/stdlib/*.clausal`
- `clausal/tools/` (Prolog ↔ Clausal translation is core-value, pure Python)
- `clausal/modules/` entries whose only dependency is the Python stdlib:
  `csv_mod`, `json_mod`, `os_mod`, `files_mod`, `process_mod`, `random_mod`,
  `regex`, `uuid_mod`, `url_mod`, `hash_mod`, `hmac_mod`, `pbkdf2_mod`,
  `date_time`, `log`, `tcp_mod`, `http_mod`, `sqlite`, `prolog.py`
  (re-dispatch), `imperial`, `units`, `graphs`.
- Corresponding `py/` wrappers that have no third-party dependency.
- `clausal-repl` script and `__main__` entry point.

Depends on: `greenlet`. (`pyyaml` moves out — see `clausal-yaml`.)

Python: >= 3.13 (unchanged).

### 3.2 Wrapper packages (one distribution per heavy library)

| Distribution | Provides | Depends on |
|---|---|---|
| `clausal-yaml` | `clausal/modules/yaml_module.py`, `modules/py/yaml.py` | `clausal`, `pyyaml>=6` |
| `clausal-spacy` | `modules/spacy_module.py`, `modules/py/spacy.py` | `clausal`, `spacy>=3` |
| `clausal-sympy` | `modules/sympy_module.py`, `modules/py/sympy.py` | `clausal`, `sympy` |
| `clausal-scipy` | all `modules/py/scipy_*.py` + `_scipy_units.py`, `_scipy_relations.py`, `modules/scipy_*.py` | `clausal`, `scipy`, `numpy` |
| `clausal-sklearn` | `modules/py/sklearn.py` | `clausal`, `clausal-scipy`, `scikit-learn` |
| `clausal-torch` | `modules/py/torch.py`, `torch_nn`, `torch_data`, `torch_functional`, `torch_distributions` | `clausal`, `torch` |
| `clausal-jax` | `modules/py/jax.py`, `jax_nn`, `jax_random`, `jax_transforms`, `jax_scipy`, `jax_sharding`, `jax_tree`, `jax_optax`, `jax_equinox`, `jax_flax` | `clausal`, `jax`, `jaxlib` |

Each wrapper distribution installs its files into a namespace slot such
that `import_from(py.<name>, [...])` resolves without configuration — see
§4.

### 3.3 Prolog-engine bridge packages

| Distribution | Provides | External |
|---|---|---|
| `clausal-gprolog` | `clausal/gprolog/`, `prolog_backends/gprolog/` C ext | system gprolog |
| `clausal-scryer` | `clausal/scryer/`, `prolog_backends/scryer/` Rust ext | scryer-prolog |
| `clausal-trealla` | `clausal/trealla/` | `trealla` on PyPI |

Each registers its engine with the Prolog-backend dispatcher (see §4.3).

### 3.4 Metapackages

- `clausal-all`: pulls every wrapper and bridge. For people who want the
  current monorepo install experience.
- `clausal[prolog]`, `clausal[scientific]`, `clausal[ml]`: extras on the
  core distribution that pull curated subsets. These are just dependency
  groupings — no code lives in them.

---

## 4. Discovery & Registration Mechanisms

Extraction only works if split packages still act like one system. Three
registration points are needed. All are entry-point based so installation
alone is enough — no config files, no import-order tricks.

### 4.1 `clausal.modules` entry points

Today, `import_from(py.sympy, [...])` is resolved by file lookup inside
`clausal/modules/py/sympy.py`. Replace that with:

- `clausal.modules.py` entry-point group. Each wrapper distribution
  declares `sympy = clausal_sympy.py_sympy` etc.
- The core `py.` import hook consults the entry-point table before falling
  back to in-tree files, so core and wrappers use the same mechanism.

The in-tree `clausal/modules/` and `clausal/modules/py/` directories stay
as namespace packages (PEP 420) so that each wrapper distribution can
drop files into them without colliding at install time. This is the
simplest layout: `clausal_sympy` contains
`clausal/modules/py/sympy.py` and nothing else. Installing it makes the
file appear under the core package path exactly as it does today.

Trade-off: namespace packages + entry points is one mechanism too many.
Pick one:

- **Option A (recommended): pure namespace-package drop-in.** No entry
  points. Files land under `clausal/modules/py/` via namespace package.
  The import hook already resolves by path. Simplest, but gives no hook
  to run setup code at registration time.
- **Option B: entry points only.** Wrapper distributions ship their code
  under their own top-level name (`clausal_sympy`) and register via an
  entry point. Core's import hook checks the registry first. More Pythonic,
  cleaner uninstall, but requires a small registry layer in core.

Decision deferred to Phase 1 prototype (§6). Default to B unless prototyping
surfaces a concrete pain.

### 4.2 `.clausal` stdlib discovery

Currently the `stdlib/` folder is looked up relative to the `clausal`
package. No change: stdlib stays in core. Wrapper distributions that ship
companion `.clausal` files (e.g. `reif.clausal` equivalents) declare a
`clausal.clausal_path` entry point returning additional search roots.

### 4.3 Prolog backend registration

Today `clausal/gprolog/__init__.py`, `clausal/scryer/__init__.py`, and
`clausal/trealla/__init__.py` are imported directly by whatever needs
them. Replace with:

- A `clausal.prolog_backends` entry-point group keyed by backend name
  (`gprolog`, `scryer`, `trealla`). Value points to an object implementing
  a small `ProlgBackend` protocol: `load_file`, `query`, `halt`, capability
  flags.
- The Prolog-translation tools (`clausal/tools/translate.py`,
  `PROLOG_IMPORT.md` work) stay in core and dispatch by backend name.
- If no matching backend is installed, querying that backend raises a
  clear `BackendNotInstalled("pip install clausal-gprolog")` error.

`clausal/modules/prolog.py` becomes a thin dispatcher over the registry.

---

## 5. Versioning & Release

- Semver per distribution. Breaking changes in `clausal` core (term
  repr, unifier contract, import-hook protocol) bump core major. Wrapper
  distributions pin `clausal>=X,<X+1`.
- Core publishes a `CLAUSAL_CORE_API` integer exposed at runtime
  (`clausal.__core_api__`). Each wrapper asserts it at import time and
  fails fast with an actionable message when run against an incompatible
  core.
- All distributions share a single repository and a single CI pipeline
  until a split becomes warranted. Tags: `core-v0.4.0`, `torch-v0.1.0`,
  etc. This lets one PR update core + an affected wrapper atomically.
- Per-distribution `pyproject.toml`, per-distribution `CHANGELOG.md`.

---

## 6. Phasing

Each phase is shippable. Don't start the next until the previous is
green on CI and uploaded to TestPyPI at minimum.

### Phase 0 — Inventory & boundary audit

Deliverable: a table, checked into `implementation_plans/package_extraction/`,
listing every file in `clausal/modules/` and `clausal/modules/py/` with:

- external runtime deps (actual `import` scan, not guesswork)
- which target distribution it belongs to
- whether it has `.clausal` tests, and where those tests live
- any cross-file imports into core or sibling wrappers

Catch the surprises before moving files. Expected surprises:

- `modules/py/_helpers.py` (~460 LOC) is shared infrastructure used by
  JAX, torch, and numpy wrappers (`_property_2`, `_values_equal`,
  `_any_unbound`, enhanced `_deep_deref` with tuple/NamedTuple
  preservation). It has no third-party deps and **must stay in core**.
- `_scipy_units.py`, `_scipy_relations.py` — decide whether they stay
  in core or ship with `clausal-scipy`.

### Phase 1 — Registration prototype on one wrapper ✅ DONE

Completed with `clausal-yaml`. Key lessons:

- **No `_module`/`_mod` suffix needed.** Name wrapper files after the
  library (`yaml.py`). Self-shadowing is avoided by `_import_stdlib()`.
  `ModulesFinder` interception is avoided by `_IMPORT_ALIASES` rewriting
  to fully-qualified `clausal.modules.<name>` at compile time.
- **`_IMPORT_ALIASES` (term_rewriting.py) + `_MODULE_ALIASES`
  (compiler_v2.py):** add `"<name>": "<name>"` to both. The compile-time
  rewrite generates `from clausal.modules.<name> import ...` — no runtime
  interception, no `sys.modules` pollution, Python `import <name>` stays
  untouched.
- **Do NOT add to `ModulesFinder._ALIASES`** — that intercepts all
  Python-level `import <name>` calls, causing collisions.
- **`clausal/modules/__init__.py` `__path__` extension:** extends with
  site-packages so `clausal.modules.<name>` resolves from separately-
  installed packages (non-editable install into site-packages).
- **Editable installs of two packages sharing a namespace don't work.**
  Use non-editable install for wrapper packages during development, or
  symlink.

### Phase 2 — Prolog engine bridges

GProlog, Scryer, Trealla each become their own distribution. These are
the most awkward in-tree pieces — they carry native-build requirements
that have no business in a core install.

These differ from `py.` wrapper extractions: they live under
`clausal/gprolog/`, `clausal/scryer/`, `clausal/trealla/` (subpackages
of `clausal` itself, not `clausal.modules`). Users import them as
`from clausal.gprolog import GnuProlog`. The same `__path__` extension
trick is needed but on `clausal/__init__.py` itself.

**Backend inventory (zero cross-deps, identical API surface):**

| Backend | Files | Lines | Native ext | Build |
|---|---|---|---|---|
| gprolog | 3 py + C ext | 264 + 17KB C | `_gprolog_ext` (C) | setuptools + GNU Prolog libs |
| scryer | 3 py + Rust ext | 250 + Rust | `_scryer_ext` (PyO3) | maturin + scryer-prolog |
| trealla | 4 py | 639 | ctypes (libtpl.so) | make from source |

**Tests:** 7 files, ~2.5 kloc. All already skip when the backend is
absent (`AVAILABLE` flag). Zero changes needed to skip logic.

**Steps:**

1. Extend `clausal/__init__.py` `__path__` with site-packages (same
   pattern as `clausal/modules/__init__.py`).
2. `clausal-trealla` first (simplest — pure Python, ctypes):
   - Move `clausal/trealla/` to `packages/clausal-trealla/clausal/trealla/`
   - Move `tests/test_trealla_*.py` to `packages/clausal-trealla/tests/`
   - `pyproject.toml`: depends on `clausal`
3. `clausal-gprolog`:
   - Move `clausal/gprolog/` to `packages/clausal-gprolog/clausal/gprolog/`
   - Merge `prolog_backends/gprolog/` build files (`_gprolog_ext.c`,
     `setup.py`) into the same distribution
   - Move `tests/test_gprolog_*.py`
   - `pyproject.toml`: setuptools with C extension, depends on `clausal`
4. `clausal-scryer`:
   - Move `clausal/scryer/` to `packages/clausal-scryer/clausal/scryer/`
   - Merge `prolog_backends/scryer/` build files (`Cargo.toml`, `src/`)
   - Move `tests/test_scryer_*.py`
   - `pyproject.toml`: maturin build, depends on `clausal`
5. Delete `prolog_backends/` top-level directory (absorbed into packages).
6. Add `[prolog]` extra on core pulling all three.

Tests: every existing bridge test must pass with only that one bridge
installed, and must be skipped (not fail) when the bridge is absent.

### Phase 3 — `scipy` family

Move all `scipy_*` and `_scipy_units.py`/`_scipy_relations.py` into
`clausal-scipy`. This is the biggest single chunk (~5 kloc).

Key risk: `_scipy_units.py` exports `make_quantity_aware` and propagator
constants used throughout wrapper plans (see
`EXTERNAL_WRAPPER_CHECKLIST.md` §5c). Decide:

- Move it with scipy — other numeric wrappers (torch) take a dep on
  `clausal-scipy` just to get units. Cleanest dependency graph would be
  a dedicated `clausal-quantity` package for the units machinery.
- **Recommended:** promote units to core (it's small, stdlib-only,
  widely depended on) and move only the scipy-specific bits.

### Phase 4 — `sympy`, `spacy`

Self-contained, one per distribution. Mechanical once Phase 1 is in place.

### Phase 5 — `torch` family, `jax` family, and `sklearn`

Largest wrappers.

**`clausal-torch`**: bundles `torch`, `torch_nn`, `torch_data`,
`torch_functional`, `torch_distributions` — they share term definitions.

**`clausal-jax`**: bundles all 10 JAX files: `jax` (core arrays, 1399
LOC), `jax_random`, `jax_nn`, `jax_transforms`, `jax_scipy`,
`jax_sharding`, `jax_tree`, `jax_optax`, `jax_equinox`, `jax_flax`.
These share internal helpers and term constructors heavily. `jax_optax`,
`jax_equinox`, and `jax_flax` depend on optional third-party packages
(`optax`, `equinox`, `flax`) beyond JAX itself. Two options:

- **Option A (recommended):** ship them all in `clausal-jax` and list
  `optax`, `equinox`, `flax` as optional extras:
  `pip install clausal-jax[optax,equinox,flax]`. The wrapper files
  already lazy-import these libraries, so `clausal-jax` with just
  `jax` installed works for core array/transform usage.
- **Option B:** separate `clausal-jax-optax`, `clausal-jax-equinox`,
  `clausal-jax-flax` distributions. More granular but more packages
  than anyone wants. Only worth it if the libraries are very heavy
  and rarely co-installed.

**`clausal-sklearn`**: depends on `clausal-scipy`.

### Phase 6 — Metapackage + release

1. Introduce `clausal-all` pulling every wrapper + bridge.
2. Add `[scientific]`, `[ml]`, `[prolog]` extras on core.
3. First real PyPI upload for every distribution, synchronised tags.
4. Update README and docs: split install instructions, table of what's
   in which distribution.

### Phase 7 — Cleanup

- Delete `prolog_backends/` top-level directory; it has been absorbed.
- Delete `setup.py` and `MANIFEST.in` if no longer needed.
- Revisit `dist/` and CI artefacts.
- Add a top-level `packages/` directory containing every extracted
  distribution; core moves into `packages/clausal/` too for symmetry.

---

## 7. Repository Layout (end state)

```
clausal-extract_modules/          # repo root, eventually renamed
  packages/
    clausal/                      # core distribution
      pyproject.toml
      clausal/
        ... (core only)
      tests/
    clausal-yaml/
      pyproject.toml
      clausal/modules/yaml_module.py        # PEP 420 namespace
      clausal/modules/py/yaml.py
      tests/
    clausal-scipy/
      pyproject.toml
      clausal/modules/py/scipy_*.py
      tests/
    clausal-torch/ ...
    clausal-jax/
      pyproject.toml
      clausal/modules/py/jax*.py
      tests/
    clausal-sympy/ ...
    clausal-spacy/ ...
    clausal-sklearn/ ...
    clausal-trealla/ ...
    clausal-gprolog/
      pyproject.toml
      clausal/gprolog/
      src/_gprolog_ext.c
    clausal-scryer/
      pyproject.toml
      clausal/scryer/
      Cargo.toml, src/
    clausal-all/
      pyproject.toml              # deps only
  implementation_plans/
  docs/
  tools/
  scripts/
```

During migration both the old `clausal/` tree and `packages/clausal/`
coexist briefly — Phase 0 installs a temporary symlink or editable
install trick so CI stays green. Each phase removes one more subtree
from the old location.

---

## 8. Open Questions

Flag here; resolve before the relevant phase starts.

1. **Namespace packages vs explicit registry.** ✅ Resolved: neither.
   Compile-time rewrite via `_IMPORT_ALIASES` + site-packages `__path__`
   extension. No namespace packages, no entry points, no runtime
   interception. See Phase 1 lessons.
2. **Where does `_scipy_units.py` live?** Core, `clausal-scipy`, or
   new `clausal-quantity`. §6 Phase 3.
3. **`_helpers.py` stays in core.** Resolved: it has no third-party deps
   and is used by JAX, torch, and numpy wrappers. It ships with core.
4. **Core pins on `greenlet`** — does extracting `clausal-trealla` also
   let us drop greenlet from core? Investigate in Phase 2.
5. **Clausal-level stdlib snippets shipped by wrappers.** Today only core
   ships `.clausal` source. If wrappers start shipping idiomatic Clausal
   helpers alongside their Python code, the `clausal.clausal_path` entry
   point in §4.2 needs implementing — not in initial scope, flag as
   deferred.
6. **Test organisation.** `tests/` is currently monolithic. Per-package
   tests move with their subject code; an integration `tests/` folder in
   the core distribution covers core + cross-package behaviour. Need to
   audit `conftest.py` and shared fixtures before the first extraction.
7. **Versioning cadence.** Lockstep releases for the first few months
   (every release bumps every distribution) are simpler but noisy. Worth
   the trade for the first 2-3 coordinated releases, then relax.
8. **JAX ecosystem extras.** `jax_optax`, `jax_equinox`, `jax_flax`
   depend on optional third-party libraries beyond JAX itself. Ship as
   extras on `clausal-jax` (recommended) or split into separate dists?
   §6 Phase 5.

---

## 9. Non-goals (reiterated)

- No API changes to individual predicates.
- No reshuffling of `clausal/logic/`, `clausal/pythonic_ast/`, or other
  core subtrees.
- No change to how users write `.clausal` code — only install commands.
- No migration of documentation structure; docs get install-table
  updates only.

---

## 10. Success Criteria

- `pip install clausal` yields a wheel under a few MB with only
  `greenlet` as a runtime dep.
- Each wrapper distribution installs, runs its own tests in isolation,
  and raises `BackendNotInstalled` / `ModuleNotFound`-style errors with
  pip instructions when invoked without its dependency installed.
- CI matrix covers: (core only), (core + one wrapper), (core + all),
  on Linux and macOS, Python 3.13.
- Release of core no longer requires coordinating torch/jax/scipy/sklearn
  API churn.
