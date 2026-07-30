# `-private` atoms are importable, which the atoms spec says they are not

**Found:** 2026-07-30, while fixing downstream fixtures for
[[done/strict-atoms-default-broke-downstream-bare-atom-fixtures]].
**Severity:** low and not urgent — the permissive behaviour is the *useful* one
and nothing observed is broken by it. This is a spec/implementation divergence
that should be resolved in one direction or the other on purpose, rather than
left as an accident that downstream code is now relying on.

## What the spec says

`implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md` makes visibility
one of the two axes of the atom model, and is explicit about it:

| Declaration site | Identity | Importable |
|---|---|---|
| listed in `-module([atom])` | module-local | yes |
| listed in `-private([atom])` | module-local | **no** |

and describes `-private` as "shadow the world inside my walls".

## What actually happens

An atom declared `-private` in one module can be imported by name from another,
and the import binds the declaring module's class — so the two modules share one
identity, which is the whole point of importing it:

    # owner.clausal
    -private([tag_a, helper(X)])
    helper(tag_a),

    # consumer.clausal
    -import_from(owner, [helper, tag_a])
    use(X) <- helper(X)

`consumer` loads clean and `use/1` solves. Under the spec's table the
`-import_from` of `tag_a` should have been rejected, or at least should not have
yielded `owner`'s class.

## Why it matters, mildly

Downstream fixtures now depend on it. Under strict atoms, a fixture whose atoms
must unify across two files has to import them rather than re-declare them (two
`-private` declarations mint two classes and the query silently fails). If the
owning file is an anonymous fixture module with no `-module(...)` export list —
common for generated or tmp_path fixtures, which have no stable module name to
export under — then importing from its `-private` list is the *only* route that
preserves identity. `clausify-executor-train`'s `test_gate_test_profiles`
fixtures were fixed this way, deliberately.

So tightening the implementation to match the spec would break that pattern and
would need an alternative for anonymous modules first.

## Options

1. **Change the spec, keep the behaviour.** `-private` means "not part of my
   documented surface", not "unreachable" — closer to Python's leading
   underscore than to C++ `private`, and consistent with how the rest of Clausal
   treats module boundaries. Cheapest, and matches what code already does.
2. **Enforce the spec.** Reject `-import_from(M, [a])` when `a` is in M's
   `-private`. Needs a story for anonymous modules first, or fixtures lose their
   only identity-preserving option.
3. **Warn only.** A `ClausalPrivateAtomImportWarning` naming both modules, with
   `-module` suggested as the fix. Keeps working code working and surfaces the
   ambiguity.

Option 1 is the likely answer, but it is a documentation decision with a real
consequence — it fixes the meaning of `-private` — and should be made rather
than defaulted into.

## Not to be confused with

The identity trap itself (declaring the same atom `-private` in two files that
must agree, producing a silently unsatisfiable query) is *correct* behaviour and
is now documented under Path B in `docs/strict-atoms-migration.md`. This todo is
only about whether the import should have been allowed.
