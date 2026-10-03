# clausal-jax: package-suite failures triaged (2026-10-04)

`python -m pytest packages` from the repo root (packages/conftest.py), box
run on 1c5ee5a0: **94 failed** in clausal-jax. After
feat/package-followups-2026-10-04: **0 failed** (the optax cases SKIP when
optax is not installed).

| Group | Class | Count | Representative node id | Status |
|---|---|---|---|---|
| optax absent: every `py.jax_optax` predicate FAILED ("no solutions") instead of raising | PACKAGE BUG (+ optional dependency absent on the box) | 54 | `packages/clausal-jax/tests/fixtures/jax_optax_tests.seam::sgd one step on a flat array` | fixed: raises `existence_error(module, optax)`, which the conftest turns into a skip naming optax |
| `-import_module(jax)` names py.jax (the bare `jax` -> `py.jax` alias), so `++(jax.numpy...)`, `jax.nn...`, `jax.ShapeDtypeStruct` raised AttributeError | ENGINE-SEMANTICS DRIFT | 24 | `packages/clausal-jax/tests/fixtures/jax_transforms_tests.seam::grad of sum(x^2) gives 2x` | fixed: py.jax's module `__getattr__` falls back to a public JAX SUBMODULE or CLASS it does not define (functions are not forwarded) |
| a Python str result is TEXT; fixtures under `-double_quotes(atom)` compared it with an atom (`device_platform(D, "cpu")`, `AXES == ["x"]`, `S == "['a'][0]"`); `device(A, D), device(A, D)` failed because `_property_2` check mode compared the bare str with the text | ENGINE-SEMANTICS DRIFT (+ helper bug) | 16 | `packages/clausal-jax/tests/fixtures/jax_sharding_tests.seam::device_platform is cpu on CI` | fixed: `_property_2` check mode accepts the text; fixtures check text with `atom_chars/2` |

Remaining failures: none.

Needs a ruling (not done):

- Should a symbolic NAME an adapter returns (a device platform such as
  `cpu`, a mesh/partition axis name) cross as an ATOM rather than text?
  Today `partition_spec(["x"], P), partition_spec(AXES, P)` gives back
  text where an atom went in.
- The `__getattr__` fallback forwards submodules and classes only, so
  `-import_from(jax, [grad])` still fails as an unknown name (review
  finding). The cost: a function-valued escape such as `++jax.vmap(...)`
  does not reach JAX through the alias; the flax/equinox fixtures use it
  and will fail when those libraries are installed (`jax.numpy.vectorize`
  or a ruling on how a seam file names the REAL `jax` would settle it).
- `py.jax_flax` / `py.jax_equinox` likely fail silently the same way
  optax did when their library is absent (not checked; both are skipped
  here because flax/equinox are not installed).
