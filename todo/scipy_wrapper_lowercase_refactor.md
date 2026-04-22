# scipy wrappers — lowercase rename to match external lib names

The Clausal convention settled (some time ago, via a big refactor
across the wrappers) on **lowercase predicate names matching the
external library's own names** — same principle as JAX wrappers
(`sigmoid`, `softmax`, `logsumexp`, `tree_flatten`) and PyTorch
wrappers (`relu`, `linear`, `cross_entropy`).

Some of the older scipy wrappers still use **TitleCase** names and
were missed by that refactor. Audit + rename:

| File | Current | Target | Examples |
|---|---|---|---|
| `clausal/modules/py/scipy_special.py` | `Gamma`, `GammaLog`, `Erf`, `Logit`, `BesselJ`, `LogSumExp`, `Entr`, `KlDivergence`, ... | `gamma`, `gammaln`, `erf`, `logit`, `besselj` (or `jn`), `logsumexp`, `entr`, `kl_div`, ... | Match `scipy.special`'s own names |
| `clausal/modules/py/scipy_stats.py` | `StatsMean`, `StatsNormalPdf`, `StatsDist`, `StatsFreezeDist`, `StatsFrozenPdf`, ... | Either drop the `Stats` prefix (module-scoped already) or keep it lowercase (`stats_mean`, `stats_normal_pdf`, `stats_dist`, ...). Leaning toward **no prefix** since the module name already namespaces. | `scipy.stats.norm.pdf(x, ...)` → `norm_pdf` or `pdf("norm", ...)` |

Also audit other scipy wrapper files that may have been missed:
`scipy_cluster`, `scipy_linalg`, `scipy_integrate`, `scipy_optimize`,
`scipy_signal`, `scipy_sparse`, `scipy_spatial`, `scipy_differentiate`,
`scipy_interpolate`, `scipy_ndimage`, `scipy_fft`, `scipy_constants`.
Grep each for capital-leading predicate names and rename.

## What breaks

- **User .clausal files.** Any import block referencing `Gamma`,
  `Erf`, `StatsNormalPdf`, etc. needs updating. Plan a deprecation
  shim that re-exports the TitleCase names pointing at the lowercase
  ones for one release cycle, then remove.
- **Internal fixture tests.** `tests/fixtures/scipy_*.clausal` and
  any other fixtures using these names — grep and rename.
- **Docs.** `docs/scipy*.md` — same grep-and-rename.

## Why not do this alongside Phase 11 (JAX scipy)

Phase 11 (`py.jax_scipy`) is proceeding with the **lowercase
external-library-matching** convention, per the Clausal-wide naming
rule. Keeping the scopes separate: Phase 11 ships correct names for
its own new predicates; the old scipy wrappers get the rename in a
separate, focused refactor pass with the deprecation shim.

## Order of operations

1. Audit each scipy wrapper file; list TitleCase predicates.
2. Add lowercase aliases alongside the TitleCase exports. Keep
   both working.
3. Update `docs/scipy*.md` + fixtures to use the lowercase names.
4. Mark TitleCase exports with a deprecation comment / warning.
5. Release cycle: announce the rename.
6. Next cycle: drop the TitleCase aliases.

## Status

Open. No deadline; the TitleCase names still work, they're just
inconsistent with the rest of the project. Pick up when there's
time or when it blocks something.
