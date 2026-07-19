# Global Atoms as Default — Spec

## Status

Proposal. Builds on the atoms-as-`PredicateMeta` work documented in
[`ATOMS_REFACTOR.md`](./ATOMS_REFACTOR.md) (which established that atoms are
zero-field `PredicateMeta` classes living in their module's namespace). This
spec changes the **default identity scope** for atoms from module-local to
global.

**Upstream state at time of writing**: The shadowing-warning machinery
(`ClausalAtomShadowingWarning`, `ClausalUnusedOverwritesWarning`, and the
`-overwrites` directive) exists in the `thai_imm_rules` consumer repo
(commits `e586d2e`, `c8a3581`, `f40cda2` on its `main`) but has **not** been
forward-ported to upstream `clausal`. The implementation plan below assumes
the upstream state and implements the shadowing warning with the narrowed
trigger from the start, rather than forward-porting then narrowing.

## Background

After the atoms-refactor, every bare atom referenced in a `.clausal` file
must be declared in `-module([...])` or `-private([...])`, and each
declaration mints a fresh `PredicateMeta` class in the declaring module's
`__dict__` (see `_process_declarations` in
`clausal/logic/compiler_v2.py:367-390`). Two modules each declaring `red`
produce two distinct classes that print identically but fail to unify by
Python identity. Sharing identity across modules requires
`-import_from(M, [red])`.

This design is internally consistent — atoms are arity-0 `PredicateMeta`,
unification is identity-based, predicates with arity match Prolog's
per-module scoping — but it diverges from Prolog's global-atom convention
precisely on the case where Prolog's choice carries the most weight:
tag-like atoms (`ok`, `error`, `pending`, `found`, status enums, profile
keys). The current rules require ceremony (every module that uses a shared
tag must `-import_from` a canonical owner) and produce a silent-failure
footgun when two modules independently declare the same name without an
import relationship.

## The new model

Atoms have two orthogonal properties: **identity scope** (global vs. module-local)
and **visibility** (importable vs. private).

| Declaration site | Identity | Importable |
|---|---|---|
| listed in `-module([atom])` | module-local | yes |
| listed in `-private([atom])` | module-local | no |
| unmentioned (bare reference only) | **global** (auto-minted) | n/a — already shared |

The two axes line up: *local-vs-global* corresponds to *mentioned-vs-unmentioned*,
and *public-vs-private* corresponds to *which list*. An atom may not appear in
both `-module` and `-private` (mutually exclusive points on the same axis); the
compiler rejects this with a hard error.

Predicates with arity ≥ 1 remain Prolog-aligned and are not affected by the
global default — see [Predicates](#predicates-with-arity) below.

## Resolution rules

### 1. Bare atom reference

A bare atom name `red` in module source is resolved at compile time by:

1. If `red` is listed in this module's `-private([...])` → use the module-local
   private `PredicateMeta`.
2. Else if `red` is listed in this module's `-module([...])` → use the
   module-local public `PredicateMeta`.
3. Else if `red` is brought into scope by `-import_from(M, [red])` → use the
   imported class (M's local `red`, if M owns one; otherwise see rule 4 in
   §[Changes to existing directives](#changes-to-existing-directives)).
4. Else → look up `red` in the process-wide global atom dict (the existing
   `predicate_builtins` from `clausal/import_hook.py:171`).
   `predicate_builtins.setdefault("red", make_predicate("red", []))` mints
   on first reference and reuses thereafter.

Steps 1–3 are mutually exclusive by the no-overlap rules; step 4 is the
fallthrough. **First use wins** for minting, but identity is load-order
independent because `setdefault` returns the existing entry on later mints.

### 2. Import wins over global

If module C does `-import_from(b, [red])` *and* uses bare `red` in clauses,
bare `red` resolves to B's local class (rule 3 above takes precedence over
rule 4). C cannot reach the global `red` via bare reference; it must use
`global_atom/2` (see [Escape hatches](#escape-hatches)) or refer to the global
class through a different module that exposes it.

This matches Python's name-lookup convention (an explicit import shadows
builtins) and gives `ClausalAtomShadowingWarning` a precise, narrow job:

> Warn when `-import_from(M, [red])` exists *and* the module also declares
> `red` in `-module` or `-private`. The two declarations describe distinct
> classes; this is almost certainly unintentional.

The `-overwrites([red])` directive (introduced in this spec, not yet upstream)
suppresses the warning when the shadowing is deliberate.

### 3. Private shadows global within its own module

If module A declares `-private([red])`, bare `red` in A's source is A's private
class — *not* the global class. Other modules' bare `red` continues to resolve
to the global class via rule 4. Privacy means "shadow the world inside my
walls."

Symmetric rule for `-module`: a `red` listed in `-module([red])` shadows the
global `red` within the declaring module's source. Other modules that
`-import_from(a, [red])` then resolve to that module-local class (rule 3
above). Other modules that don't import still see the global `red`.

### 4. `-import_from` of an atom

Importing an atom from a module that owns a local version (because the source
module listed it in `-module([...])`) binds the imported class into the local
namespace and shadows the global default for that name in the importing
module. Importing an atom that the source module does *not* list in
`-module([...])` is a no-op — the atom is already global, so there is nothing
distinct to import. The compiler treats such an import as a documentation hint
rather than an error, so mixed atom/predicate imports from the same module
work without partial rejection.

### 5. `-overwrites`

New directive introduced by this spec (not present upstream): silences
`ClausalAtomShadowingWarning` for the listed names. Trigger is the
import-plus-local-declaration case (rule 2 above) — `-overwrites` is the
escape hatch for when a module deliberately maintains both an imported name
and a distinct local declaration of the same name.

## Predicates with arity

Predicates with arity ≥ 1 do not participate in the global default. The rules
for them:

| Declaration site | Identity | Importable |
|---|---|---|
| listed in `-module([P(X)])` | module-local | yes |
| listed in `-private([P(X)])` | module-local | no |
| **unmentioned** | **module-local, implicitly private** | no |

This preserves Prolog's "exports must be declared" norm and the cross-module
tabling/dispatch guarantees that depend on per-module predicate identity.
The asymmetry between atoms (global default) and predicates (local default)
is principled: Prolog itself treats atoms as global and predicates as
module-scoped, so the divergence in default reflects a real semantic
distinction, not an inconsistency.

A `-common([P(X)])`-style directive for sharing predicate identity across
modules is **out of scope** for this proposal and should remain unimplemented.
Cross-module predicate sharing is what `-import_from` is for.

## Escape hatches

### `global_atom/2`

Builtin predicate exposing direct lookup into `predicate_builtins`:

```clausal
global_atom("red", ATOM)   % unifies ATOM with the global red class
```

Modes:

- `global_atom(+Name, -Atom)` — given a string name, unifies `Atom` with
  the corresponding global `PredicateMeta` class, minting it on demand via
  `setdefault`.
- `global_atom(+Name, +Atom)` — succeeds iff `Atom` is the global class for
  `Name`. Useful as a guard.
- `global_atom(-Name, +Atom)` — given a `PredicateMeta` class, unifies
  `Name` with its `__name__`. Succeeds iff the class is in
  `predicate_builtins` (i.e., is genuinely a global atom, not a
  module-local one with the same spelling).
- `global_atom(-Name, -Atom)` — enumerates the global atom dict.
  Implementation detail; ordering not guaranteed.

`global_atom/2` is the only sanctioned way to obtain the global class for a
name when a module-local declaration or an import shadows the global default.

### Qualified references

`other_module.red` continues to refer to the atom class living in
`other_module`'s namespace, exactly as it does today. This is the way to reach
a module's local atom without importing it. No spec change.

### Diagnosing cross-module identity mismatch (`CLAUSAL_WARN_ATOM_IDENTITY`)

The module-local identity model means two modules that each *declare* the same
atom hold **distinct** classes, so a value carrying one will not unify with a
value carrying the other — the query silently has *no solution*. This is the
intended scoping (see rule 3 above), but the failure looks identical to a
legitimately-unsatisfiable query.

Set the opt-in env var `CLAUSAL_WARN_ATOM_IDENTITY=1` to make unification emit a
one-shot `ClausalAtomIdentityMismatchWarning` (a `ClausalAtomShadowingWarning`
subclass, so it lives in the same warning family) naming *both* owning modules
whenever two same-named atoms of different identity are compared. Example:

```clausal
# lib.clausal
-module(lib, [approved, Check(X)])
Check(approved),
```
```clausal
# caller.clausal — re-declares `approved`, so Check(approved) has no solution
-import_from(lib, [Check])
-private([approved])
Ask() <- Check(approved)
```

**Remedy:** import the atom instead of re-declaring it —
`-import_from(lib, [Check, approved])` — so both modules share one class.

The flag is off by default and the check is **only** installed on atom classes
minted while it is set, so the unify hot path is untouched when the flag is off.
This is a *diagnosability aid only*: it does not change whether unification
succeeds (module-local identity is deliberate; see the Non-goal below).

## Changes to existing directives

- **`-module(name, [...])`**: unchanged syntax. Items in the export list now
  carry "module-local, public" semantics rather than the current "module-local,
  public, and the only way to use this name in this module" semantics.
- **`-private([...])`**: unchanged syntax. Items carry "module-local,
  private." Listing an atom here only matters when the module wants identity
  distinct from the global default; otherwise the listing is unnecessary.
- **`-import_from(M, [...])`**: unchanged for predicates. For atoms, becomes
  semantically meaningful only when M owns a local version (atom listed in
  M's `-module([...])`). Importing a name that is global in M is a no-op
  documentation hint.

## New directive: `-strict_atoms`

File-level opt-in directive that disables the global auto-mint default for
the file containing it. With `-strict_atoms` present, every bare atom
reference in the file must be reachable through one of:

- a `-module([...])` listing,
- a `-private([...])` listing,
- a `-import_from(M, [...])` listing,
- a qualified reference (`other_module.red`),
- a `global_atom/2` call.

A bare reference to an atom not satisfying any of the above is a compile-time
error rather than a silent global auto-mint. The diagnostic names the
offending atom and the file, and suggests the four legitimate ways to
declare or reach it.

`-strict_atoms` takes no arguments:

```clausal
-strict_atoms
-module(immigration_rules, [Eligible(X), Denied(X, Reason)])
-private([visa_type, application_status])
-import_from(atoms, [ok, error, pending])
```

Intent: trade Prolog-style ergonomics for typo safety in files where atom
spelling correctness is load-bearing — regulatory rules, clinical decision
support, legal compliance, financial compliance. A typo in such files can
produce a quietly wrong answer (a fallback clause fires because the canonical
lookup didn't find the expected atom); `-strict_atoms` upgrades these errors
from silent to compile-time.

**Scope**: per-file only. `-strict_atoms` does not propagate to imported
modules; each file decides for itself. A strict file can import freely from
non-strict files and vice versa — the resolution rules in §1 still apply,
the directive only changes whether step 4 (global fallthrough) is permitted.

**Interaction with `global_atom/2`**: even in strict files, `global_atom/2`
still resolves against the global atom dict. The directive restricts *bare*
references, not the reflection escape hatch. A strict file that genuinely
needs to reach a global atom by name does so via
`global_atom("red", ATOM), ...`.

**Recommended use**: turn on for any file whose clauses encode authoritative
rules (regulatory, legal, clinical). Leave off for general code, library
code, and prototypes. Two real-world consumers that should adopt this:
`thai_imm_rules` and any future legal/clinical rule package.

## Implementation touch points

Concrete file references for the implementor. Line numbers reflect upstream
`clausal` `main` at the time of writing (after commit `5937d44`).

### Atom resolution / minting

- **`clausal/import_hook.py:171-198`** — `predicate_builtins` dict is
  defined and populated. This is the shared mutable dict that auto-minted
  global atoms live in. New global atoms enter via
  `predicate_builtins.setdefault(name, make_predicate(name, []))`.
- **`clausal/import_hook.py:333`** and **`:419`** — `module_dict.update(
  predicate_builtins)` is called at the start of each module's exec.
  Class objects are copied by reference, so any global atom minted in
  `predicate_builtins` before a module's exec ends up in that module's
  `__dict__` and resolves naturally via Python name lookup.

### Per-module atom/predicate declaration

- **`clausal/logic/compiler_v2.py:367-390`** — `_process_declarations`
  walks `-module` and `-private` `module_items` and calls
  `make_predicate(name, [])` for each atom, `make_predicate(name, fields)`
  for each predicate, assigning the result into `module_dict`. This is
  where the local-declaration branch of rule 1 already lives.
- **`make_predicate`** is imported from
  `clausal.logic.predicate` (see `clausal/__init__.py:24`). Factory for
  `PredicateMeta` classes.

### Auto-mint hook (the main behavior change)

After `_process_declarations` runs, the compiler must:

1. Collect the set of bare atom names referenced in the file's clauses
   but **not** accounted for by `-module`, `-private`, or any
   `-import_from`. Pythonic AST term rewriting (around
   `clausal/templating/term_rewriting.py`) already walks atomic positions
   in clause bodies — that's the natural place to collect references.
2. For each undeclared bare atom name, call
   `predicate_builtins.setdefault(name, make_predicate(name, []))` and
   assign the result into `module_dict[name] = cls`. Order:
   `setdefault` must happen at compile time so the class is present in
   `module_dict` before clauses execute.

This single hook implements rule 1.4 (the global fallthrough). It should
run **after** `_process_declarations` so explicit declarations win.

### Directive parsing and dispatch

- **`clausal/templating/term_rewriting.py:2407-2449`** — `_handle_directive`
  dispatches `-name(...)` directives. New directives must be added here:
  - Add a branch for `-strict_atoms` that calls a new
    `_handle_strict_atoms_directive`.
  - Add a branch for `-overwrites` that calls a new
    `_handle_overwrites_directive` (modeled on the thai_imm_rules
    implementation but with the narrowed trigger). The existing
    "known directives" error message at line 2444-2449 must be updated
    to list the new directives.
- **`clausal/templating/term_rewriting.py:2450-2543`** —
  `_handle_module_directive` (line 2450) and `_handle_private_directive`
  (line 2499) populate `transformer._module_items` with
  `ModuleDeclItem` / `PrivateDeclItem`. The validation step (atom must
  not appear in both lists; mutual-exclusion error) goes in
  `_process_declarations` or in a new pre-pass in
  `clausal/logic/compiler_v2.py`.

### Module-level AST nodes

- **`clausal/pythonic_ast/nodes.py`** holds `ModuleDeclItem`,
  `PrivateDeclItem`, and `DirectiveItem`. New nodes needed:
  - `StrictAtomsDeclItem` — marker, no payload. Presence in
    `module_items` activates strict-mode resolution.
  - `OverwritesDeclItem(items: list[str])` — list of atom names whose
    shadowing should not warn.

### Shadowing warning

- **No existing classes in upstream.** Add to
  `clausal/logic/compiler_v2.py` near the top (mirroring the
  thai_imm_rules placement at line 38-58):
  - `class ClausalAtomShadowingWarning(UserWarning): ...`
  - `class ClausalUnusedOverwritesWarning(UserWarning): ...`
- The check itself runs as part of declaration processing in
  `_process_declarations`: walk imports, walk `-module` + `-private`
  declarations, compute the intersection, subtract `OverwritesDeclItem`
  entries, emit `ClausalAtomShadowingWarning` for the remainder.
- Compute the set of `-overwrites` names that do not appear in any
  `-import_from` ∩ local-declaration intersection; emit
  `ClausalUnusedOverwritesWarning` for each.

### `global_atom/2` builtin

- Pattern: builtins are registered in `predicate_builtins`
  (`clausal/import_hook.py:171-198`). Look at how `unify`, `deref`,
  `walk` are exposed — same pattern.
- Implementation: a Python function that takes `(name, atom)` deref'd
  args and dispatches on instantiation, calling
  `predicate_builtins.setdefault` for the `+name, -atom` mode.
- Mode handling follows the pattern of existing reflection builtins;
  look at how `functor/3` or `atom_to_term/2` (if present) handle their
  modes for a template.

### Documentation

- **`docs/directives.md`** — add `-strict_atoms` section. Add
  `-overwrites` section (this is the first time it lands in upstream).
  Update `-module`, `-private`, `-import_from` sections with the new
  resolution semantics and a "per-module identity" callout that points
  at this spec. The thai_imm_rules version of `docs/directives.md` has
  prose that can be adapted (it covers `-overwrites` but assumes
  per-module default; update the framing).
- **`docs/syntax.md`** — replace the "Per-module identity" callout from
  the atoms section with a "Global by default" callout. Cross-reference
  this spec and `docs/directives.md#-strict_atoms`.
- **`docs/builtins.md`** — add `global_atom/2` entry.

## Suggested implementation phases

Each phase is independently testable and produces a working build. Phases
1–3 are additive (no behavior change for existing code that uses explicit
declarations). Phase 4 is the breaking flip. Phases 5–6 are docs and
migration cleanup.

### Phase 1: `global_atom/2` builtin

Smallest, additive, no behavior change. Implements the reflection escape
hatch ahead of the auto-mint hook so tests for Phase 2 can use it to
assert identity sharing.

- Add `global_atom/2` Python implementation.
- Register in `predicate_builtins`.
- Tests: each mode (+,-), (+,+), (-,+), (-,-). Round-trip
  `global_atom("foo", X), global_atom(N, X)` should give `N = "foo"`.
- Commit: `feat(builtins): global_atom/2 for global-atom reflection`

### Phase 2: bare-atom auto-mint hook

The behavior change. After this phase, undeclared bare atom references in
non-strict files auto-mint into `predicate_builtins`.

- Add the collect-undeclared-bare-atoms pass in the term-rewriting
  walker.
- Add the mint-into-module-dict step in `_process_declarations` (or a
  successor pass) that calls
  `predicate_builtins.setdefault(name, make_predicate(name, []))` and
  assigns into `module_dict`.
- Tests:
  - Two modules, neither declares `red`, both reference `red` in
    clauses. Assert `mod_a.red is mod_b.red`.
  - Module A declares `-private([red])`, module B does not. Assert
    `mod_a.red is not mod_b.red` and `mod_b.red` is in
    `predicate_builtins`.
  - Module A declares `-module(a, [red])`, module B does
    `-import_from(a, [red])` and bare-references `red`. Assert
    `mod_b.red is mod_a.red` (import wins over global).
  - Module A declares `-module(a, [red])`, module B bare-references
    `red` without importing. Assert `mod_a.red is not mod_b.red` and
    `mod_b.red` is in `predicate_builtins`.
- Commit: `feat(compiler): bare atoms default to global identity`

### Phase 3: `-strict_atoms` directive

Additive opt-out from Phase 2's auto-mint.

- Add `StrictAtomsDeclItem` AST node in
  `clausal/pythonic_ast/nodes.py`.
- Add `_handle_strict_atoms_directive` to
  `clausal/templating/term_rewriting.py` and wire into
  `_handle_directive`.
- In the auto-mint pass (Phase 2), check for
  `StrictAtomsDeclItem` in `module_items`; if present, raise a
  `NameError` with a helpful diagnostic instead of minting.
- Tests:
  - File with `-strict_atoms` and bare reference to undeclared atom
    fails to compile with a diagnostic naming the atom.
  - File with `-strict_atoms` and bare reference to atom declared in
    `-private` compiles successfully.
  - File with `-strict_atoms` and `global_atom("red", X)` compiles
    successfully even though `red` is not declared.
- Update `_handle_directive` known-directives error message.
- Commit: `feat(directive): -strict_atoms for typo-safe rule files`

### Phase 4: shadowing warning + `-overwrites`

Forward-port the warning from `thai_imm_rules` with the narrowed trigger.

- Add `ClausalAtomShadowingWarning` and `ClausalUnusedOverwritesWarning`
  to `clausal/logic/compiler_v2.py`.
- Add `OverwritesDeclItem` AST node.
- Add `_handle_overwrites_directive`.
- In `_process_declarations` (or successor), compute the
  import-∩-local-declaration intersection minus `-overwrites`
  entries; warn for each.
- Compute unused `-overwrites` entries; warn for each.
- Tests:
  - `-import_from(M, [red])` + `-private([red])` → warning fires.
  - Same + `-overwrites([red])` → no warning.
  - `-overwrites([foo])` with no shadow → unused-warning fires.
- Commit: `feat(compiler): ClausalAtomShadowingWarning with narrowed
  trigger`

### Phase 5: documentation

- Rewrite `docs/directives.md` per the touch-points section above.
- Update `docs/syntax.md` "Per-module identity" callout.
- Add `docs/builtins.md` entry for `global_atom/2`.
- Cross-link to this spec from each relevant doc.
- Commit: `docs(atoms): document global-default + -strict_atoms`

### Phase 6: migration of existing fixtures

- Grep for `-private([…])` and `-module(…, [bare_atoms])` listings
  across `tests/fixtures/**/*.clausal` and `clausal/**/*.clausal`.
- For each, decide: keep (module-local identity is intentional) or
  remove (the listing was ceremonial; global default is fine).
- Run full test suite and adjust any tests that asserted per-module
  identity on atoms that are better as global.
- Commit: `refactor(fixtures): drop redundant atom declarations`

After Phase 6, downstream consumers (notably `thai_imm_rules`) can
update to consume the new upstream behavior. The thai_imm_rules
commits `e586d2e`, `c8a3581`, `f40cda2` should be reverted in favor of
the upstream implementation.

## What this spec does NOT change

- The reification of atoms as `PredicateMeta` classes.
- Unification semantics (still Python identity on classes).
- Hashing / `__eq__` / dict-key behavior of atoms.
- Predicate (arity ≥ 1) scoping or import rules.
- The interaction with Scryer/Trealla bridges (atoms crossing the boundary
  still need a marshalling convention — see [Open questions](#open-questions)).
- The directive syntax for `-module`, `-private`, or `-import_from`.

## Migration

### What breaks

Code that relies on the *current* per-module default for atoms breaks
silently if two modules independently declared the same atom expecting them
to be distinct. Under the new model, both names point to the global class
unless the modules explicitly opt in to module-local identity via `-private`
or `-module`.

A grep over existing `.clausal` files for atoms appearing in `-module([...])`
or `-private([...])` lists identifies every site that needs review. For most
of them (tag atoms used as data), removing the listing is the correct
migration — the global default already gives the desired sharing behavior.
For the minority where module-local identity is intentional (atoms carrying
module-specific semantics that must not unify across modules), the listing
stays. Phase 6 of the implementation plan covers this sweep.

### What doesn't break

- Atom *spellings* in clauses. No source rewriting needed for the common
  case.
- Predicate declarations and import directives — unchanged.
- The `PredicateMeta` runtime contract — unchanged.
- Round-tripping atoms through Python code that uses `is`/`==` on
  `PredicateMeta` classes — unchanged, since identity is still
  class-identity.

### Downstream impact

`thai_imm_rules` currently carries its own implementation of the shadowing
warning + `-overwrites` (commits `e586d2e`, `c8a3581`, `f40cda2`). Once
this spec lands upstream, those commits should be reverted and the upstream
implementation adopted. The behavior change (per-module → global default)
will reduce ceremony in thai_imm_rules and is a candidate use case for the
new `-strict_atoms` directive.

## Open questions

1. **Additional typo mitigation beyond `-strict_atoms`.** Files that don't
   opt into `-strict_atoms` still face the silent-typo cost. Project-wide
   mitigations worth considering as follow-ups:
   - Compile-time lint pass that flags global atoms referenced exactly once
     across the loaded program (high-signal heuristic for typos in
     non-strict files).
   - IDE/LSP integration that surfaces global atoms and their referencing
     sites, so authors notice when a "new" atom appears that should have
     matched an existing one.

   These are complements to `-strict_atoms`, not replacements for it: the
   directive gives a hard local guarantee for rule-bearing files, while
   lint/LSP give statistical coverage elsewhere.

2. **Marshalling across backend bridges.** Scryer and Trealla have global
   atom tables. A round-trip Clausal-A → Scryer → Clausal-B previously had
   to choose a module to intern returning atoms into. Under the new default,
   the natural choice is the global atom dict — but this means a
   Scryer-originated atom never carries module attribution back to Clausal.
   Out of scope here; document the marshalling rule alongside whichever
   bridge spec covers term serialization.

3. **Persistence and external storage.** Terms serialized to disk or wire
   formats need a canonical naming convention for atoms. With most atoms
   global, the natural form is the bare name (`red`). Module-local atoms
   need qualification (`module.red`). Out of scope here; the
   serialization layer should define its own canonicalization.

4. **REPL / notebook behavior.** Bare `?- color(red).` from an interactive
   session resolves `red` against the REPL's module context. Under the new
   default, `red` is the global atom — which is the intuitive behavior for
   ad-hoc queries. Worth confirming in the REPL implementation that no
   module-local resolution accidentally shadows the global default in the
   REPL's pseudo-module.

5. **`global_atom/2` naming.** `global_atom/2` is more declarative
   (Prolog-style noun-form predicate); `get_global_atom/2` is more
   imperative. Spec uses `global_atom/2` for consistency with Prolog naming
   conventions.

6. **Auto-mint pass placement.** The bare-atom collection step needs to run
   after directive processing (so we know what's declared) but before clause
   compilation (so module_dict is populated). Confirm this fits cleanly into
   the existing pipeline order in `clausal/logic/compiler_v2.py`. If the
   term-rewriting walker is the right collection site, the mint step can
   piggy-back on `_process_declarations`. If a separate AST pass is
   cleaner, add it as a sibling.

## Summary

- Atoms default to global (auto-minted into `predicate_builtins`).
- `-module([atom])` opts into module-local public identity.
- `-private([atom])` opts into module-local private identity.
- Bare reference resolution: private → public → imported → global.
- Predicates with arity stay module-local-by-default; this spec does not
  change them.
- `global_atom/2` is the reflection escape hatch.
- `ClausalAtomShadowingWarning` (new upstream, narrowed trigger from the
  thai_imm_rules version) catches `-import_from` + local-declaration
  conflicts; `-overwrites` suppresses.
- `-strict_atoms` is a per-file opt-in that disables global auto-mint,
  turning bare-reference-to-undeclared-atom into a compile-time error.
  Intended for regulatory/clinical/legal/compliance files where atom-typo
  correctness is load-bearing.
- Typo silence in non-strict files is the accepted cost, with a lint pass
  and LSP integration as follow-up mitigations.
- Implementation proceeds in six phases (Phase 1: `global_atom/2`,
  Phase 2: auto-mint hook, Phase 3: `-strict_atoms`, Phase 4: shadowing
  warning + `-overwrites`, Phase 5: docs, Phase 6: fixture migration).
- Downstream `thai_imm_rules` reverts its parallel implementation after
  Phase 4 lands.
