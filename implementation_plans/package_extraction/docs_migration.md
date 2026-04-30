# Package-Docs Migration Plan

Follow-up to `PACKAGE_EXTRACTION.md`. The recent extractions
(`46cce77` yaml, `7b67ae6` sympy/spacy, `ebe7f74` prolog backends,
`621abc7` scipy/torch/jax, `ea39af8` sklearn) moved each wrapper's
**code, tests, and doc fixtures** into `packages/clausal-<pkg>/`,
but left the **docs** (`docs/<pkg>.md`) and the **integrity tests**
(`tests/test_doc_snippet_integrity.py`, `tests/test_doc_snippet_coverage.py`)
in core. The docs still reference fixture paths that no longer
exist in core, so 3 tests fail at every test run.

This plan migrates the docs and their integrity coverage to live
with their packages. Core's `docs/` becomes a directory of packages
plus its own (non-package) content.

---

## 1. Goal

After this migration:

1. `docs/<pkg>.md` files for extracted packages **do not exist in core**.
2. Each `packages/clausal-<pkg>/` owns:
   - `docs/<pkg>.md` (and any sub-pages, e.g. `jax_*.md`)
   - `tests/fixtures/docs/<pkg>_sigs.txt` etc. (already true today)
   - `tests/test_doc_integrity.py` running the same checks as core's tests
3. Core's `docs/` has a single page (`docs/packages.md`) that lists
   each extracted package with a one-line description and a link out.
4. `mkdocs.yml` no longer references extracted-package docs in `nav:`.
5. `tests/test_doc_snippet_integrity.py` and `tests/test_doc_snippet_coverage.py`
   pass with zero broken references against the slimmed core docs.
6. The shared check logic lives in **one place**, imported by both
   core's tests and each package's tests — no copy-paste of the
   integrity-check code.

Non-goals:

- Rewriting any package's actual doc content. Pages move as-is.
- Building a single unified docs site that assembles per-package
  docs at build time. That's a separate project — see §6.
- Versioning/publishing changes for the packages.

---

## 2. Current State

```
clausal/
├── docs/
│   ├── yaml.md, sympy.md, spacy.md, sklearn.md           ← extracted, broken refs
│   ├── jax.md, jax_equinox.md ... jax_tree.md            ← 10 jax docs
│   ├── scipy_special.md ... scipy_cluster.md             ← 14 scipy docs
│   ├── torch.md, torch_data.md, torch_distributions.md,
│   │   torch_functional.md, torch_nn.md                  ← 5 torch docs
│   ├── gprolog.md, scryer.md, trealla.md                 ← 3 prolog backends
│   └── (rest: core docs)
├── tests/
│   ├── test_doc_snippet_integrity.py  ← scans docs/, hardcoded
│   └── test_doc_snippet_coverage.py   ← scans docs/, hardcoded
└── packages/
    ├── clausal-yaml/tests/fixtures/docs/yaml_sigs.txt    ← already moved
    ├── clausal-torch/tests/fixtures/docs/torch_*.txt     ← already moved
    ├── clausal-jax/tests/fixtures/                       ← already moved
    └── ...
```

Total docs to migrate: **36 files** across 10 packages.

| Package | Doc files |
|---|---|
| clausal-jax | 10 |
| clausal-scipy | 14 |
| clausal-torch | 5 |
| clausal-gprolog, scryer, trealla | 1 each |
| clausal-sklearn, spacy, sympy, yaml | 1 each |

---

## 3. Target State

```
clausal/
├── docs/
│   ├── packages.md   ← NEW: directory page listing packages
│   └── (core docs only — no jax/torch/scipy/etc.)
├── tests/
│   ├── test_doc_snippet_integrity.py  ← scans core docs only
│   └── test_doc_snippet_coverage.py   ← scans core docs only
├── clausal/tools/
│   └── doc_snippet_check.py  ← NEW: shared check helpers
└── packages/clausal-<pkg>/
    ├── docs/
    │   └── <pkg>.md (and sub-pages)
    └── tests/
        ├── fixtures/docs/         ← already there
        └── test_doc_integrity.py  ← NEW: per-package wrapper
```

The shared module `clausal/tools/doc_snippet_check.py` exposes
parameterised check functions:

```python
def collect_snippet_refs(docs_dir: Path) -> list[Ref]: ...
def check_files_exist(refs: list[Ref], project_root: Path) -> list[str]: ...
def check_sections_exist(refs: list[Ref], project_root: Path) -> list[str]: ...
def check_clausal_fixtures_have_tests(refs: list[Ref], project_root: Path) -> list[str]: ...
def check_no_skip_blocks(docs_dir: Path) -> list[str]: ...
def check_no_raw_untested_blocks(docs_dir: Path) -> list[str]: ...
```

Each package's `test_doc_integrity.py` is ~30 lines: it computes
its own `docs_dir` and `project_root`, calls each check function,
and asserts the result lists are empty. Core's existing test files
become equivalent thin wrappers.

---

## 4. Per-Package Recipe

For each `<pkg>` in `{yaml, sympy, spacy, sklearn, gprolog, scryer,
trealla, torch, scipy, jax}`:

### 4.1 Move docs

```bash
mkdir -p packages/clausal-<pkg>/docs
git mv docs/<pkg>.md packages/clausal-<pkg>/docs/<pkg>.md
# For multi-page packages (jax, scipy, torch), repeat for each <pkg>_*.md
```

### 4.2 Verify snippet references resolve

The `--8<--` references in the moved docs already point to
`tests/fixtures/docs/<pkg>_*.txt`. After the move, those paths
resolve relative to the **package's** project root
(`packages/clausal-<pkg>/`), where the fixtures already live
from the original extraction. No edit needed inside the .md files.

If any doc references a fixture that did *not* move with the
package (rare; possible for `scipy_optimize.md` referencing
`scipy_special` content, etc.), copy or symlink as needed and
record the dependency in the package's `pyproject.toml`.

### 4.3 Add per-package integrity test

Create `packages/clausal-<pkg>/tests/test_doc_integrity.py`:

```python
from pathlib import Path
from clausal.tools.doc_snippet_check import (
    collect_snippet_refs,
    check_files_exist,
    check_sections_exist,
    check_clausal_fixtures_have_tests,
    check_no_skip_blocks,
    check_no_raw_untested_blocks,
)

PKG_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PKG_ROOT / "docs"


def test_all_snippet_files_exist():
    refs = collect_snippet_refs(DOCS_DIR)
    missing = check_files_exist(refs, PKG_ROOT)
    assert not missing, "Missing files:\n" + "\n".join(missing)

# ... same shape for the other five checks
```

### 4.4 Remove core nav entry

Delete the `<pkg>.md` line from the `nav:` block in `mkdocs.yml`.

### 4.5 Add a stub link in `docs/packages.md`

Append one row to the directory page (created in §5):

```markdown
| **clausal-<pkg>** | One-line description | [docs](https://gitlab.com/MikeAmy/clausal-<pkg>/-/blob/main/docs/<pkg>.md) |
```

The link target is open: GitLab URL once each package has its own
repo, or a relative `../packages/clausal-<pkg>/docs/<pkg>.md`
during the source-tree-monorepo phase. See §6.

### 4.6 Verify

```bash
pytest packages/clausal-<pkg>/tests/test_doc_integrity.py -q
pytest tests/test_doc_snippet_integrity.py tests/test_doc_snippet_coverage.py -q
```

Both must pass before moving to the next package.

---

## 5. Shared Infrastructure (do this first)

### 5.1 Build `clausal/tools/doc_snippet_check.py`

Extract the check logic that currently lives in
`tests/test_doc_snippet_integrity.py` and `test_doc_snippet_coverage.py`
into a module under `clausal/tools/`. Each function returns a list
of violation strings (empty list = pass). Test files do the
asserting.

Required functions:

| Function | Replaces in core | Returns |
|---|---|---|
| `collect_snippet_refs(docs_dir)` | private helper | `list[(md_path, lineno, file_ref, section)]` |
| `check_files_exist(refs, project_root)` | `test_all_snippet_files_exist` | violation strings |
| `check_sections_exist(refs, project_root)` | `test_all_snippet_sections_exist` | violation strings |
| `check_clausal_fixtures_have_tests(refs, project_root)` | `test_clausal_fixtures_have_tests` | violation strings |
| `check_no_skip_blocks(docs_dir)` | `test_no_skip_blocks` | violation strings |
| `check_no_raw_untested_blocks(docs_dir)` | `test_no_raw_untested_blocks` | violation strings |

### 5.2 Rewire core's test files

`tests/test_doc_snippet_integrity.py` becomes a thin wrapper:
imports from `clausal.tools.doc_snippet_check`, configures
`DOCS_DIR = repo_root/"docs"` and `PROJECT_ROOT = repo_root`,
calls the check functions, asserts. Same for the coverage file.

After this step, core tests are still green and behaviourally
identical — purely a refactor.

### 5.3 Create `docs/packages.md`

Single page listing each extracted package with a one-line
description and a link out. This is what the (now-empty) "Standard
Library" / "Prolog backends" / etc. nav sections become for the
extracted entries.

Add to `mkdocs.yml` `nav:` once, in place of the per-package
entries that get removed in §4.4.

---

## 6. Open Question — Docs Site Assembly

Currently `bash docs/serve-docs.sh` runs mkdocs over the core
`docs/` folder. After this migration, that produces a unified
site for the *core* only. Three options for end-user docs:

**A. Per-package independent sites.** Each `packages/clausal-<pkg>/`
grows its own `mkdocs.yml`. Users navigate from core's
`packages.md` to each package's standalone site. Simplest;
matches the per-distribution model. Worst for cross-doc search.

**B. Monorepo plugin.** Use `mkdocs-monorepo-plugin` (or write a
build script) to assemble core + all `packages/*/docs/` into one
site at build time. Keeps the "one site to read" UX. Couples
the build to having all packages checked out, but that's already
true of `packages/` today.

**C. Symlink the package docs into core's `docs/` at build time.**
Build script runs before mkdocs and `ln -s ../packages/<pkg>/docs/<pkg>.md docs/<pkg>.md`
for each known package. Simple, but the symlinks are not part of
the source tree — easy to forget.

**Recommendation: A for v1, revisit B once packages are published
to PyPI**. Independent sites are the honest representation of how
users will install and use the packages once they're separate
distributions. The unified-site nostalgia can wait.

This decision is **not blocking** the migration — every option
above works given the target state in §3. Pick when there's a
concrete request.

---

## 7. Rollout Order

Do §5 first (shared infrastructure). Then migrate one package as
a pilot, then the rest in size order so any per-package surprises
surface on small packages first:

| Order | Package | Why |
|---|---|---|
| 5 (prep) | shared `doc_snippet_check.py` | unblocks everything |
| 1 (pilot) | yaml | smallest (1 doc), already pilot-extracted, low blast radius |
| 2 | sklearn | 1 doc, fixtures already moved |
| 3 | sympy | 1 doc |
| 4 | spacy | 1 doc, has known fixture-naming quirks (sees `spacy_module` legacy refs) |
| 5 | gprolog | 1 doc, separate dep stack |
| 6 | scryer | 1 doc |
| 7 | trealla | 1 doc |
| 8 | torch | 5 docs |
| 9 | scipy | 14 docs (largest single migration) |
| 10 | jax | 10 docs (most cross-page references — verify last) |

After each step, the full test suite runs clean. If a package's
migration breaks something downstream, the bad commit is small
and revertable.

---

## 8. Success Criteria

- `pytest tests/ -q` passes with zero failures.
- For each `<pkg>`: `pytest packages/clausal-<pkg>/tests/ -q`
  passes including the new `test_doc_integrity.py`.
- `docs/` contains no `<pkg>.md` for any extracted package.
- `mkdocs.yml` has no `nav:` entries pointing at extracted-package
  docs.
- `clausal/tools/doc_snippet_check.py` exists and is the only
  place the check logic is defined.
- `docs/packages.md` exists and lists all 10 packages.
- One commit per package (plus one for §5) — the migration is
  reviewable as a series of small, mechanical changes.

---

## 9. Issues

Surfaced during the rollout. Each is filed as a follow-up todo
under `implementation_plans/package_extraction/todo/`.

### Editable installs don't expose package modules

`pip install -e packages/clausal-<pkg>` "succeeds" but
`import clausal.modules.<pkg>` fails. The PEP 660 finder doesn't
extend an existing `clausal.modules.__path__`; non-editable
installs work because they copy files under
`<site-packages>/clausal/modules/`. Per-package
`test_doc_integrity.py` requires the package to be installed
non-editably for its inline-block compile-checks to pass.

Workaround used during migration: `pip install packages/clausal-<pkg>`
(no `-e`) before running per-package tests. Filed at
[`todo/editable_install.md`](todo/editable_install.md) — proper
fix wants its own design pass (PEP 420 namespace packaging is
the right answer).

### Docs site assembly is now an open question

After this migration, `mkdocs build` produces 54 broken-link
warnings because core docs (`index.md`, `architecture.md`,
`constraints.md`, etc.) link directly to extracted-package docs
that no longer live in core's `docs/`. `mkdocs build --strict`
aborts.

§6 of this plan punted the assembly decision; it can no longer
be punted. Filed at
[`todo/docs_site_assembly.md`](todo/docs_site_assembly.md) with
a recommended short-term path (rewrite cross-doc links to
`packages.md`) and a long-term path (`mkdocs-monorepo-plugin`).

### Path-prefixed snippet refs in sympy.md

`sympy.md` was the only migrated doc that used
`packages/clausal-sympy/tests/fixtures/docs/...` as the snippet
prefix. That worked when the doc lived in core (where
`_PROJECT_ROOT` was the repo root) but broke after the move into
the package (where `_PKG_ROOT` is `packages/clausal-sympy/`).

Fixed in `ec6a771` by stripping the prefix. Migration of the
other 9 packages used package-relative refs from the start;
no further occurrences expected.

### Stale `py.<pkg>` legacy snippets in spacy and scipy_differentiate

Both `spacy.md` and `scipy_differentiate.md` carried "Or via the
`py.<pkg>` alias" snippets that referenced an import alias that
existed before extraction and was removed when the packages
extracted. The bare-name alias (e.g. `spacy`) is now the canonical
import.

Fixed inline during their respective migration commits (`e224f99`,
`7936192`). Other migrated docs were checked; no further legacy
snippets remained.

### 103 pre-existing uncompilable inline blocks in jax docs

Most `.md` files in clausal-jax carry partial display fragments
and pseudo-code that don't compile standalone. These were
already in this state before extraction — they made up the bulk
of core's pre-migration `test_no_raw_untested_blocks` failure.

Mitigated with a `_KNOWN_UNCOMPILABLE` allowlist in
`packages/clausal-jax/tests/test_doc_integrity.py` (annotated as
"do not grow"). Cleanup tracked at
[`todo/jax_doc_cleanup.md`](todo/jax_doc_cleanup.md).

### Latent translator bugs surfaced by golden roundtrip

Two unrelated bugs in the prolog translator were exposed by
exercising the regenerated goldens:

1. `_emit_compound` and `_emit_list` called `emit_term` without
   `context_prec`, defaulting to 1201 (no parens for any
   operator). Args separated by `,` (prec 1000) sit at
   context_prec 999, so any contained `;`/`->`/`:-` operator
   needed parens. Fixed in `ecc6252`.
2. `prolog_to_clausal` emitted Prolog `true`/`false`/`fail`
   verbatim, but Clausal uses Python `True`/`False`. Fixed in
   `08c50e0` with a `_BUILTIN_ATOM_REWRITES` mapping.

Neither was caused by the migration; the migration made them
visible. Both fixes are independently good.

### `docs/builtins.md` had a YAML section pointing at deleted fixtures

When `clausal-yaml` extracted in `46cce77`, the YAML sections
in `tests/fixtures/docs/builtins_sigs.txt` were deleted, but
the corresponding YAML section in `docs/builtins.md` (with 7
`--8<--` references) was not. The section was pointing at
non-existent fixtures and survived undetected because the
old core integrity tests only tracked which were broken, not
when they became broken.

Fixed in `248d20a` by deleting the stale YAML section from
core's `builtins.md`. The yaml docs are now at
`packages/clausal-yaml/docs/yaml.md` (migrated in `9af34bc`).
