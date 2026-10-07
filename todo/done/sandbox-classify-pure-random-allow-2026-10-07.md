# Sandbox: classify `library(pure_random)` as ALLOW

**Status: OPEN (for the sandbox work; nothing to do until the sandbox lands).**

Filed 2026-10-07, with the pure random library.

`clausal/modules/pure_random.py` (`library(pure_random)`, seam
`-import_from(pure_random, ...)`) is pure and deterministic: every answer is
a function of the arguments. It reads no clock, no OS entropy, no file, no
environment and no global state, and writes nothing. Its only Python
dependencies are `hashlib.sha256` and `random.Random(int).random()` on a
fresh, local generator. The state term `rng(Seed, N)` is validated
(`type_error(rng_state, S)`) before any of it reaches Python, and the seed
is read only as an integer or as text.

So the sandbox should classify all six predicates as ALLOW: `rng_seed/2`,
`random/3`, `random_between/5`, `random_member/4`, `random_permutation/4`,
`random_sample/5`.

The deprecated `py.random` (`library(py_random)`) is the opposite case: it
keeps a process-global generator, and `set_seed/1` changes it for every
other caller. It should NOT be allowed by default.

## DONE 2026-10-07

Classified ALLOW in `clausal.sandbox.ADAPTERS` and the `docs/sandbox.md`
table when the library was restacked onto the landed sandbox. Checked
against the code: the only randomness is `random.Random(<SHA-256 digest>)`,
a fresh local generator per draw; the stdlib modules are bound under
underscore names, which no export rule offers. `py.random` stays deny.
