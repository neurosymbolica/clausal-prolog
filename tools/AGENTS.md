# tools/ — developer scripts (repo root, not the package)

Ad-hoc developer tools that live outside the `clausal` package. Most are
one-off censuses written for a specific migration; a few are live. Do not
confuse with [`../clausal/tools/`](../clausal/tools/AGENTS.md), the package's
reader/front-end/translator code.

Up: [../AGENTS.md](../AGENTS.md)

## Live (used by CI or tests)

| Path | What |
|---|---|
| `wheel_smoke.py` | Smoke-tests an INSTALLED clausal (C extensions, `clausal` CLI, a `library(...)` facade, a `.pl` program). Run by cibuildwheel in `../.github/workflows/release.yml`; run it from outside the source tree |
| `show_generated.py` | Prints seam source beside the generated trampoline Python. Pinned by `../tests/test_show_generated_smoke.py` |
| `build_logo.py` | Generates the logo SVGs, PNGs and favicons in `../docs/assets/logo/` (PNGs need Chromium and ImageMagick) |
| `new-worktree` | Bash: create a git worktree that shares Claude memory with the source repo |

## Migration censuses and helpers (historical)

| Path | Written for |
|---|---|
| `atom_class_census/census.py` | Remaining uses of the deprecated `atom` str-subclass (2026-09-27) |
| `atom_export_predicate_census/census.py` | Modules hit by the atom-export / `name/0` warning (ruling 2026-09-26) |
| `import_local_clash_census/census.py` | Modules hit by the import/local clash refusal (2026-09-26) |
| `division_census/` | Whether exported programs divide unevenly under clpz `#=` ([README](division_census/README.md)) |
| `double_quotes_pin.py` | Pin/migrate `-double_quotes` in sources for the 2026-09-26 `atom` -> `chars` default flip |
| `atoms_flip/STR_SITES.tsv` | Working table of `str` type tests for the atoms-as-str flip (2026-09-18) |
| `w3_package_gate.sh` | Runs out-of-tree `_get_dispatch` implementors' package suites in their own venv (W3, 2026-09-22) |

## Gotchas

- Census tools describe `.clausal` / `.seam` as written at the time; several
  predate the 2026-10-02 extension flip, when `.clausal` meant seam source.
- Re-running a census is fine; editing it to "fix" an old migration is usually
  not wanted — check the todo or plan it served first.

Related one-off scripts live in `../scripts/` (`gen_currencies.py` generates the
ISO-4217 vocabulary in `clausal/modules/countries` and is AST-checked by
`tests/test_currency_minor_units.py`; `audit_2026_07_05/check_prompt_paths.py`
validated the 2026-07-05 audit prompts).
