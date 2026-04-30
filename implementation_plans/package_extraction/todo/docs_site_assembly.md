# Decide and implement how the docs site assembles after migration

## Where this came from

`implementation_plans/package_extraction/docs_migration.md` §6
listed three options for assembling end-user documentation now
that per-package docs live at `packages/clausal-<pkg>/docs/`:

- **A. Per-package independent sites.** Each package grows its
  own `mkdocs.yml`. Users navigate from core's `packages.md` to
  each package's standalone site. Simplest; matches per-distribution
  publication. Worst for cross-doc search.
- **B. Monorepo plugin.** Use `mkdocs-monorepo-plugin` (or a build
  script) to assemble core + all `packages/*/docs/` into one site
  at build time.
- **C. Symlink package docs into core's `docs/` at build time.**
  Build script runs `ln -s ../packages/<pkg>/docs/<pkg>.md
  docs/<pkg>.md` before mkdocs.

The plan recommended **A for v1**, revisit B once packages are
on PyPI. That decision wasn't actioned during the migration —
this todo carries it forward.

## Concrete state today

`mkdocs build` (non-strict) produces 54 broken-link warnings
because core docs (`index.md`, `architecture.md`, `constraints.md`,
`directives.md`, `files.md`, `for_prolog_programmers.md`,
`importing_prolog.md`, `iso_prolog_compatibility_report.md`,
`prolog_translation.md`, `tabling.md`, `units.md`, etc.) link to
moved package docs (`scryer.md`, `trealla.md`, `yaml.md`,
`scipy_*.md`, `sympy.md`, `spacy.md`, `sklearn.md`).

`mkdocs build --strict` aborts on these warnings.

`docs/packages.md` lists the packages and uses relative paths like
`../packages/clausal-yaml/docs/yaml.md`. Those resolve correctly
in the source tree (`packages/clausal-yaml/docs/yaml.md` exists)
but mkdocs doesn't include them in the built site by default —
they fall outside `docs_dir`.

## What to do

### Short-term (option A, recommended for v1)

Make core's docs site build clean without --strict warnings,
acknowledging that package docs live separately.

1. Replace direct cross-references to extracted-package docs
   with links to `packages.md`. For example, in
   `for_prolog_programmers.md`: `[Scryer](scryer.md)` →
   `[Scryer](packages.md)`. Consistent for all 54 broken links.
2. Replace package-relative `../packages/<pkg>/docs/<pkg>.md`
   links in `packages.md` with either GitLab URLs (once each
   package has its own repo) or with `https://gitlab.com/MikeAmy/clausal/-/blob/main/packages/clausal-<pkg>/docs/<pkg>.md`
   (renders the markdown on GitLab). The mkdocs site shows
   "see the package's repo for full docs" — honest and correct
   given option A.
3. Re-run `mkdocs build --strict`. Should be clean.
4. Each package gets its own `mkdocs.yml` and its own served
   site (or a README that's well-structured) — separately, on
   each package's own schedule.

Estimated effort: 1–2 hours of mechanical edits + maybe a small
script to rewrite the link patterns.

### Long-term (option B, when packages are on PyPI)

Add `mkdocs-monorepo-plugin` to core's `mkdocs.yml` so that core's
`packages.md` becomes the index of a unified site that includes
each package's docs as a subsection. Each package keeps owning
its docs source, but users get a single navigable site.

Estimated effort: a day to learn the plugin, configure paths,
verify cross-package search and the navigation tree, and update
each package's mkdocs config to play along.

## Why it's filed, not done

The migration plan explicitly punted this decision: "not blocking
— every option above works given the target state. Pick when
there's a concrete request." Today's docs migration completed
with `mkdocs build` failing in --strict mode, which means the
question can no longer be deferred for serving the user-facing
docs. But it's also a real product/UX decision that the human
should make, not the migration agent.

## Acceptance

- Decision made (recorded by amending this file or
  `docs_migration.md` §6) and chosen option implemented.
- `mkdocs build --strict` exits 0.
- `bash docs/serve-docs.sh` produces a site users can navigate
  from core to per-package documentation, by whatever mechanism
  the chosen option provides.
