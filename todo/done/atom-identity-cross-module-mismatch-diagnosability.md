# P2: silent unify failure between same-named module-local atoms — add a diagnosability aid

STATUS: DONE (2026-07-19). Diagnosability aid only — atom identity/interning
unchanged (Non-goal respected). Opt-in via env var `CLAUSAL_WARN_ATOM_IDENTITY=1`.
When set, `PredicateMeta.__new__` installs a diagnostic `__unify__` on zero-field
(atom) classes only; when unset, no hook is installed and the unify hot path is
byte-for-byte unchanged (zero-cost when off). New warning
`ClausalAtomIdentityMismatchWarning` subclasses the existing
`ClausalAtomShadowingWarning` family (`compiler_v2.py`); it fires one-shot per
(name, ownerA, ownerB) naming both owning modules, and unify still returns False.
`_process_declarations` now stamps declared atoms' `__module__` with the owning
clausal module for accurate attribution. Coverage: the compare-site hook fires
whenever the C `do_unify` reaches an atom on either side (the atom's `__unify__`
is consulted symmetrically) — i.e. all constant-atom-vs-atom compares. Docs +
remedy (`-import_from`) added to `docs/import.md` and
`GLOBAL_ATOMS_DEFAULT.md`. Tests in `tests/test_atom_identity_warning.py`
(unit compare-site + subprocess two-module package repro; warns once under flag,
silent without).

## Mechanism (intended design, confirmed — not a bug)
Name resolution is lexical/load-time against the DEFINING module (`clausal/logic/compiler_v2.py:498-566`
`_process_bare_atom_refs`; dispatch `globals_=module_dict` at `:180-191`; `docs/import.md:209-270`). A declared
atom gets a **module-local class** (`_process_declarations`, `compiler_v2.py:603-655`): two modules that each
DECLARE `approved` (instead of one importing it) hold distinct objects, and unification between them **fails
silently** — no error, no warning, the query just has no solution. Verified empirically (lib declares
`approved`, caller declares its own: `lib.approved is caller.approved → False`; `check(approved)` from the
caller → NO SOLUTION; with `-import_from` instead, shared identity, succeeds).

This bit a downstream rulebase corpus's decomposition work repeatedly (misdiagnosed there as "bare atoms resolve against
the calling module at solve time" — wrong mechanism, and now corrected in their briefs). Their mitigation is a
convention ("all shared atoms live in schema.clausal and are imported") plus a corpus lint. The engine-side gap
is **diagnosability**: the failure mode is indistinguishable from a legitimately-unsatisfiable query.

## Proposal
- Debug/diagnostic mode (env var or `-warn_atom_shadowing`-style flag): when unification compares two atoms (or
  0-arity functor classes) with the SAME name but DIFFERENT identity, emit a one-shot warning naming both owning
  modules. A `ClausalAtomShadowingWarning` already exists for the import+local-declare conflict — extend that
  family to the cross-module compare case (compare-site hook can be behind the flag to avoid hot-path cost).
- Docs: add an explicit "same-name declared atoms do not unify across modules" example + remedy
  (`-import_from`) to `docs/import.md` near L209-270 and to GLOBAL_ATOMS_DEFAULT.md.

## Non-goal
Do NOT globally intern declared atoms — module-local identity is a deliberate opt-in; changing it breaks the
declared-atom scoping model.

## Acceptance
Repro test: two-module package with duplicate declared atom → warning fires once under the flag, silent without
it; docs example added.
