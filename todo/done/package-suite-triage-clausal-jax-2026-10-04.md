# clausal-jax: package-suite failures triaged (2026-10-04)

**Status: FIXED 2026-10-04 (commits ddea7b16, dfca3ca5, 94815dbd, 90e3d6d2).** clausal-jax runs with 0 failures (1139 passed; only the flax and equinox suites skip when those libraries are absent). Both rulings landed: symbolic names cross as atoms, and the real jax is reached with a hosted `import jax as pyjax`.

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

- RULED 2026-10-04 (atom out, text in), DONE on
  feat/package-triage-rulings-2026-10-04: a symbolic NAME an adapter
  returns (a device platform such as `cpu`, a mesh/partition axis name)
  crosses as an ATOM; the sharding fixture compares atoms again. Leftovers
  of the census: todo/adapter-text-boundary-census-leftovers-2026-10-04.md.
- RULED 2026-10-04, DONE on feat/package-triage-rulings-2026-10-04: no
  wider forwarding. A seam file reaches the REAL `jax` with a hosted Python
  `import jax as pyjax` (an existing spelling; `++pyjax.vmap(...)` works);
  the flax/equinox fixtures and docs use it. Documented in
  docs/python_integration.md ("Reaching a Python library directly").
- `py.jax_flax` / `py.jax_equinox` DID fail silently when their library is
  absent; fixed as optax was (existence_error(module, flax|equinox), checked
  outside the `_pure` wrapper).
