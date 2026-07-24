# Dict-key atom resolution does not respect the strict default

**Status:** open (design question)
**Raised:** 2026-07-24, final whole-branch review of `strict-atoms-default`.

## The asymmetry

After strict-atoms-by-default landed, an undeclared bare atom in **value
position** raises a compile-time `NameError`:

```clausal
Color(sky),        % NameError: sky undeclared (strict default)
```

but the same undeclared atom used as a **dict-literal key** still silently
auto-mints, because `_make_intern_atom` in `clausal/import_hook.py`
(~line 91) gates minting on the *old* condition
`strict = any(StrictAtomsDeclaration ...)` rather than the new
`effective_strict = not any(ImplicitAtomsDeclaration ...)` used by
`compiler_v2._process_bare_atom_refs`:

```clausal
{sky: 1},          % mints `sky` — no error, under the same neither-directive file
```

So value-position and key-position bare atoms now resolve under **different**
defaults in the same file.

## Why it's currently out of scope

The design spec (`docs/superpowers/specs/2026-07-24-strict-atoms-default-design.md`,
"Out of scope") explicitly excluded changes to atom hashing / dict-key
behavior, inheriting the boundary from `GLOBAL_ATOMS_DEFAULT.md`. Under the
*old* loose default the two positions agreed (both minted), so the boundary
was invisible; the flip made it observable.

## Decision needed

1. **Converge** — make `_make_intern_atom` honor the same
   `effective_strict = not implicit_mode` rule so dict-key atoms raise under
   the strict default too. Most consistent; needs its own tests and a check
   for downstream reliance on key auto-mint.
2. **Deliberately keep the asymmetry** — dict keys are a distinct surface
   (interning for hashing) and may warrant staying permissive. If so, document
   it explicitly and fix the stale docstring at `import_hook.py:~79` (it says
   "Under `-strict_atoms`", which no longer names the governing condition).

Related code: `clausal/import_hook.py` `_make_intern_atom`,
`clausal/logic/compiler_v2.py` `_process_bare_atom_refs`.
