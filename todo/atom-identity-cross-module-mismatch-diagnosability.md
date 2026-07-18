# P2: silent unify failure between same-named module-local atoms — add a diagnosability aid

## Mechanism (intended design, confirmed — not a bug)
Name resolution is lexical/load-time against the DEFINING module (`clausal/logic/compiler_v2.py:498-566`
`_process_bare_atom_refs`; dispatch `globals_=module_dict` at `:180-191`; `docs/import.md:209-270`). A declared
atom gets a **module-local class** (`_process_declarations`, `compiler_v2.py:603-655`): two modules that each
DECLARE `approved` (instead of one importing it) hold distinct objects, and unification between them **fails
silently** — no error, no warning, the query just has no solution. Verified empirically (lib declares
`approved`, caller declares its own: `lib.approved is caller.approved → False`; `check(approved)` from the
caller → NO SOLUTION; with `-import_from` instead, shared identity, succeeds).

This bit the clausify-domains Wave-B decomposition repeatedly (misdiagnosed there as "bare atoms resolve against
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
