# `__init__.clausal` — directory-as-package module resolution

**Motivation:** Unblocks the clausify-domains **module namespace migration** — moving 54 legal domains off
flat, hand-prefixed module names (`snap`, `gdpr_lawfulness`, `csa_scheduling`) onto hierarchical dotted
namespaces that mirror the directory tree (`us.snap`, `eu.gdpr.lawfulness`). This is the "flat namespace"
pain point `implementation_plans/import_system/IMPORT_PLAN.md` already promises to solve ("Python packages
give us hierarchical dotted paths for free"). Design doc (consumer side):
`/workspace/clausify-domains/docs/superpowers/specs/2026-07-15-module-namespace-migration-design.md`.

## Goal
A directory `foo/bar/` that contains `foo/bar/__init__.clausal` must import as the package module `foo.bar`,
executing the init file's clauses/exports into the package namespace — reusing Python's own `__init__`
package mechanism. Submodule files under it (`foo/bar/baz.clausal`) continue to resolve as `foo.bar.baz`.

Target usage (domain package with a thin re-exporting init + named submodules):
```
eu/gdpr/__init__.clausal          # -import_from(eu.gdpr.lawfulness, [decide_lawfulness, ...])  (re-export)
eu/gdpr/lawfulness.clausal        # -module(lawfulness, [decide_lawfulness, ...])
eu/gdpr/special_category_inference.clausal
```
so a consumer can write `-import_from(eu.gdpr, [decide_lawfulness])` (via the init's re-export) **or**
`-import_from(eu.gdpr.lawfulness, [decide_lawfulness])` (direct submodule).

## Where
- `clausal/import_hook.py` :: `_ExtensionFinder.find_spec` (currently ~line 534). Today it only matches a
  **flat file** `os.path.join(dir_entry, tail + ".clausal")`. Add a **directory branch**: if
  `pkg_dir = os.path.join(dir_entry, tail)` is a directory containing `__init__.clausal`, return a
  `ModuleSpec` whose loader points at `pkg_dir/__init__.clausal` **and** whose
  `submodule_search_locations = [pkg_dir]` (this is what marks it a *package* so `foo.bar.baz` then
  resolves via a subsequent `find_spec(fullname="foo.bar.baz", path=[pkg_dir])`).
- `PredicateLoader` (same file): when loading a package init, set the module's `__path__` (importlib does
  this from `submodule_search_locations`, but confirm the `.clausal` loader doesn't clobber it). Clause
  execution into the module namespace is otherwise identical to a flat module.
- **Do not regress PEP-420 namespace packages.** Today `foo/bar/` *without* an `__init__.clausal` already
  works as a namespace package and its submodule *files* resolve (`eu.gdpr.lawfulness` loads today). The new
  branch must only fire when `__init__.clausal` is present; absent it, fall through to existing behaviour.
- Keep the existing stdlib-shadowing guard (`tail in sys.stdlib_module_names`) and finder ordering
  (`_ExtensionFinder` runs before `PathFinder`) intact.

## Acceptance
- Dir `a/b/` with `a/b/__init__.clausal` defining/exporting `p/1` → `-import_from(a.b, [p])` loads and `p`
  runs. (Directory-as-module.)
- **Re-export through init:** `a/b/__init__.clausal` does `-import_from(a.b.c, [q])`; a consumer's
  `-import_from(a.b, [q])` then resolves `q` (the thin-package-init pattern the domains will use).
- Submodule files still resolve **with and without** an `__init__.clausal` present: `a/b/c.clausal` →
  `-import_from(a.b.c, [...])` works in both cases (no namespace-package regression).
- Existing flat-module resolution (`snap.clausal` → `snap`) unchanged; stdlib-shadow warning still fires.
- Tests in `tests/` + a fixture under `tests/fixtures/` (e.g. `pkg_init/…`) covering: dir-as-module,
  re-export, submodule-with-init, submodule-without-init, flat-module-unchanged.

## Notes
- `-module(name, [...])` declarations stay **bare** (`-module(lawfulness, [...])`) — the namespace comes from
  the directory/import path, NOT the declaration. (So this is unrelated to the earlier rejected dotted
  `-module(kit.X)` declarations — those are still out of scope.)
- Future (not this todo): the domains' *citation* atoms will migrate to their own namespaced files carrying
  external references + verbatim quoted statute text (explainability). Package-init resolution is the
  prerequisite that makes those sub-namespaces addressable.
