# Runtime dict-key atom intern does not respect the strict default

**Status:** open (narrowed 2026-07-29 — the compile-time path already converged)
**Raised:** 2026-07-24, final whole-branch review of `strict-atoms-default`.
**Narrowed:** 2026-07-29 after empirical check on `clausal-bug-fix` HEAD `d2d12fe0`.

## Corrected scope

There are two dict-key atom paths; only ONE remains permissive:

- **Compile-time source literal keys — STRICT (no gap).** A bare atom used as a
  source dict-literal key (`d(D) <- (D == {sky: 1})`) is collected by
  `compiler_v2._process_bare_atom_refs` and rejected under the strict default
  (`effective_strict = not implicit_mode`) exactly like a value-position atom.
  Empirically confirmed: `{sky: 1}` in a neither-directive file raises
  `strict_atoms: undeclared atom 'sky'`. This path already matches the default;
  nothing to do.
- **Runtime intern path — STILL PERMISSIVE (the real gap).**
  `clausal/import_hook.py:_make_intern_atom` (~line 98) gates minting on the
  *old* `strict = any(StrictAtomsDeclaration ...)` condition, so a
  **dynamically-constructed** dict-key name can still auto-mint in a
  neither-directive file. This is the residual asymmetry.

(An earlier version of this todo overstated the gap as covering all dict keys,
and `docs/strict-atoms-migration.md` briefly repeated that error; both are now
corrected — see the closed
`todo/done/strict-atoms-migration-doc-dict-key-inaccurate.md`.)

## Decision needed (runtime path only)

1. **Converge** — make `_make_intern_atom` honor
   `effective_strict = not implicit_mode` so runtime-constructed keys reject
   under the strict default too. Needs its own tests and a check for downstream
   reliance on runtime key auto-mint.
2. **Deliberately keep it** — runtime interning for hashing may warrant staying
   permissive. If so, document it and fix the `_make_intern_atom` docstring
   (~line 84), which still says "Under `-strict_atoms`" rather than naming the
   current governing condition.

Related code: `clausal/import_hook.py` `_make_intern_atom`,
`clausal/logic/compiler_v2.py` `_process_bare_atom_refs`.
