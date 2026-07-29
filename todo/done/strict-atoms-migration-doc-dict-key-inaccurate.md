# Migration doc's dict-key carve-out is inaccurate for literal keys

**Status:** open (doc fix + reconcile with dict-key-atom-strict-asymmetry)
**Raised:** 2026-07-29, during the clausify `strict-atoms-readiness` migration
(clausify commits `f63802d..8a8035c`).

## The finding

`docs/strict-atoms-migration.md` (the "What did *not* change" list) currently
claims:

> **Dict-literal keys** — an undeclared bare atom used as a dict key *still*
> auto-mints (a deliberately scoped-out asymmetry; see
> `todo/dict-key-atom-strict-asymmetry.md`).

That is **not** what the engine does for the common case. A **source
dict-literal key** in a neither-directive file now RAISES under the strict
default:

```clausal
-module(m, [d/1])
d(D) <- (D is {sky: 1})     % NameError: strict_atoms: undeclared atom 'sky'
```

Empirically confirmed against this clone (`clausal-bug-fix`, HEAD
`d2d12fe0`): both a value-position undeclared atom AND a source dict-literal
key are rejected; only `-implicit_atoms` files (and the auto-implicit REPL /
doc blocks) still auto-mint.

## Why the doc is wrong but the asymmetry todo is still (partly) right

There are two dict-key paths, and only one is strict:

- **Compile-time, source literal keys** — `compiler_v2._process_bare_atom_refs`
  walks the AST (including dict-literal keys) under the strict-default
  (`effective_strict = not implicit_mode`) rule, so undeclared literal keys
  reject. This is the common case a user hits, and it is what makes the doc
  line wrong.
- **Runtime intern path** — `import_hook.py:_make_intern_atom` (line ~98) still
  gates on the *old* `strict = any(StrictAtomsDeclaration ...)` condition, so a
  dynamically-constructed key name can still auto-mint in a neither-directive
  file. This residual asymmetry is what `todo/dict-key-atom-strict-asymmetry.md`
  tracks — that todo remains validly open for this path.

## Action

1. **Fix the migration doc** (`docs/strict-atoms-migration.md`): the "dict-literal
   keys still auto-mint" bullet is misleading. State that **source dict-literal
   keys are strict** like any other bare atom, and that the *residual*
   permissiveness is limited to the runtime intern path (cross-ref the
   asymmetry todo), not source literals.
2. **Reconcile with** `todo/dict-key-atom-strict-asymmetry.md` — its "Decision
   needed / Converge" option is already in effect for the compile-time path;
   narrow that todo to the `_make_intern_atom` runtime path, or converge it too.

Related code: `clausal/logic/compiler_v2.py` `_process_bare_atom_refs`,
`clausal/import_hook.py` `_make_intern_atom` (line ~98), and the docstring at
`import_hook.py:~84-92` (which already hints at this split).

---
**Resolved 2026-07-29:** doc fixed (source dict-literal keys are strict — empirically confirmed) and `todo/dict-key-atom-strict-asymmetry.md` narrowed to the runtime `_make_intern_atom` path.
