# JAX docs — replace 103 inline pseudo-code blocks with tested snippets

## What

`packages/clausal-jax/tests/test_doc_integrity.py` carries an
`_KNOWN_UNCOMPILABLE` allowlist of 103 entries — partial display
fragments and pseudo-code in the jax docs that don't compile
standalone. The list spans `jax.md`, `jax_equinox.md`, `jax_flax.md`,
`jax_nn.md`, `jax_optax.md`, `jax_random.md`, `jax_scipy.md`,
`jax_sharding.md`, `jax_transforms.md`, `jax_tree.md`.

This is **not a regression** introduced by the docs migration. These
blocks were already uncompilable before extraction — they made up
the bulk of core's pre-migration `test_no_raw_untested_blocks`
failure (108 entries; 103 became this allowlist after migration,
the remaining 5 were either fixed or moved with other packages).

The allowlist is in place so the package's tests pass; the cleanup
itself is the work below.

## What to do

For each `(file, lineno)` entry in the allowlist:

1. Read the block. Determine whether it is:
   - **Display-only** (a signature, a snippet of pseudo-code, an
     output sample). Move it to a section in
     `tests/fixtures/docs/<page>_sigs.txt` and reference it from
     the doc with `--8<-- "tests/fixtures/docs/<file>:<section>"`.
   - **Executable** (an example users should be able to run). Add
     a `Test(...) <- (...)` wrapper if missing, or fix any stale
     identifiers (`py.jax_*` → `jax_*`, etc.) so the block compiles.

2. Remove the entry from `_KNOWN_UNCOMPILABLE`.

3. Verify `pytest packages/clausal-jax/tests/test_doc_integrity.py`.

The allowlist comment says "do not grow" — anyone adding a new
inline block in jax docs should write it to be either a snippet
reference or a self-contained Test, not append to the allowlist.

## Why it's filed, not done

The package-docs migration plan is about migration mechanics:
move docs into packages, run integrity checks against them. Doing
the content cleanup inside the migration would have ballooned the
migration commit and blurred the diff. As a follow-up, this work
is independent of the migration and can be paced over multiple
small commits — each removes a few entries and improves the docs.

## Acceptance

- `_KNOWN_UNCOMPILABLE` in `packages/clausal-jax/tests/test_doc_integrity.py`
  is empty and the import removed.
- All 5 jax integrity checks pass without the allowlist.
