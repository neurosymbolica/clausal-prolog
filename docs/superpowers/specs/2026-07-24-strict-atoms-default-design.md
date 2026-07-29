# Strict Atoms by Default — Design

**Date:** 2026-07-24
**Status:** Approved design, pending implementation plan.
**Builds on:** [`GLOBAL_ATOMS_DEFAULT.md`](../../../implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md)
(established atoms-as-`PredicateMeta`, the global auto-mint default, and the
`-strict_atoms` opt-in it is now reversing).

## Motivation

Clausal atoms currently default to **global auto-mint**: a bare atom reference
that is not declared, imported, or qualified silently mints a fresh global
`PredicateMeta` class. A typo (`peding` for `pending`) therefore produces a
silently-unsatisfiable clause and a no-solution answer indistinguishable from a
legitimately-false query. `-strict_atoms` upgrades that silent footgun to a
compile-time `NameError`, but only for files that opt in.

Clausal's headline goals — correctness, safety, and familiarity to Python
programmers — all point the other way from the current default:

- **Python familiarity.** A bare lowercase identifier in Python is a name
  lookup that raises `NameError` when undefined; Python never auto-creates a
  name by reference. Strict atoms match that instinct; the loose default
  surprises it.
- **Correctness / safety.** Silent-wrong-answer is the worst failure class for
  a rule language. Making the safe behavior the default and the auto-mint an
  opt-in is the standard safe-default principle.
- **Data already lives in strings.** Free-form data is idiomatically carried as
  strings (`color("blue")`), so bare atoms play the role of *named constants /
  identifiers*. Requiring those to be declared is exactly Python's stance on
  names, and cheap because the high-frequency data case does not use bare atoms.

The counterweight is Prolog ergonomics (ceremony-free tag atoms), which
`GLOBAL_ATOMS_DEFAULT.md` deliberately optimized for. This design reverses that
default while preserving a permanent, ceremony-free escape hatch for the cases
that genuinely want loose behavior (REPL, prototypes, legacy).

## Chosen approach

**Pure binary flip, staged.** Two runtime states only — strict (hard
`NameError`) and implicit (auto-mint) — with no intermediate `warn` state. Safety
during the transition comes from *migration ordering*, not a runtime middle
state: an escape-hatch directive is added everywhere first, so flipping the
default breaks nothing, and strictness is then peeled on file-by-file.

**Scope: the Clausal repository only.** The codemod and the default flip touch
`clausal/**` and `tests/fixtures/**`. Downstream consumers (`thai_imm_rules`,
`clausify-domains`, the `ai_act`/MAR rules) migrate on their own schedule — the
directive is per-file and does not propagate, so a downstream program adds
`-implicit_atoms` to any loose file before upgrading. `clausify-domains` is
believed to be largely strict-clean already.

## End-state runtime model

Two orthogonal, argument-less directive markers. Both accept the bare `-name`
form and the parenthesised `-name()` form, mirroring today's `-strict_atoms`.

| File contains          | Undeclared bare atom behavior            |
|------------------------|------------------------------------------|
| `-implicit_atoms`      | auto-mint into the global dict (today's default) |
| `-strict_atoms`        | hard `NameError` (unchanged)             |
| neither                | **`NameError`** — the new default        |
| both                   | **compile error** (mutually exclusive)   |

- Resolution rules 1.1–1.4 of `GLOBAL_ATOMS_DEFAULT.md` (private → public →
  imported → global) are untouched. These directives select *only* whether step
  1.4 (the global fallthrough) mints or raises.
- The internal decision inverts from today's `strict_mode = any(StrictAtomsItem
  in module_items)` to `implicit_mode = any(ImplicitAtomsItem in module_items)`,
  with `strict = not implicit` as the default.
- `global_atom/2` still resolves against the global dict in every mode; the
  directives restrict *bare* references only, not the reflection escape hatch.
- The both-directives case is a hard compile error, matching the existing
  `-module`/`-private` mutual-exclusion precedent.

`-strict_atoms` survives as a no-op that merely restates the default. It emits a
one-per-process deprecation notice (see [Deprecation](#deprecation-notice)).
`-implicit_atoms` is **not** deprecated — it is the permanent, sanctioned escape
hatch.

## Migration phases

Each phase is a separate commit; the test suite is green at every phase
boundary.

### Phase 1 — Add `-implicit_atoms` (additive, no behavior change)

- Add `ImplicitAtomsDeclaration` AST node (`clausal/pythonic_ast/nodes.py`).
- Add `_handle_implicit_atoms_directive` and wire it into `_handle_directive`
  (`clausal/templating/term_rewriting.py`); add it to the known-directives error
  message.
- Add the both-directives mutual-exclusion error.
- Codemod inserts `-implicit_atoms` into every `clausal/**/*.clausal` and
  `tests/fixtures/**/*.clausal` that does **not** already carry `-strict_atoms`.

Because the default is still loose at this phase, `-implicit_atoms` is a no-op —
which is exactly what makes it safe to add everywhere.

### Phase 2 — Green the suite (checkpoint)

Fixtures and tests that asserted the loose default now assert it via an explicit
directive. Nothing should change behaviorally; this phase is a verification
checkpoint, not new production code. Fix any test that implicitly depended on the
old default without an explicit directive.

### Phase 3 — Flip the default (the breaking change)

- Invert the mint/raise decision in `_auto_mint_bare_atoms`
  (`clausal/logic/compiler_v2.py`): neither directive ⇒ strict.
- Pin the REPL to implicit (see [REPL](#repl)).
- Land the `-strict_atoms` deprecation notice, since the directive becomes
  redundant at this point.

The suite stays green because Phase 1 armored every in-repo file with
`-implicit_atoms`.

### Phase 4 — Pilot strictness

Remove `-implicit_atoms` from a small, high-value set of files so they become
strict, and fix the fallout (genuine typos surface as errors here — the payoff).
The pilot set is chosen at implementation time; candidates are rule-bearing
stdlib files and a couple of representative fixtures. Purpose: validate the
migration ergonomics on a small sample before the full sweep.

### Phase 5 — Sweep and deprecate

- Remove `-implicit_atoms` from every file where strict is fine, leaving it only
  where loose behavior is genuinely wanted.
- `-strict_atoms` is now formally deprecated (kept, one-shot warning).
- `-implicit_atoms` remains the permanent, non-deprecated escape hatch.

## REPL

The REPL stays implicit regardless of the file default. The interactive
pseudo-module injects an `ImplicitAtomsDeclaration` into its `module_items` (or
sets the mode directly) before compiling each snippet, so ad-hoc queries such as
`?- color(red).` keep auto-minting. This is wired at the REPL boundary
(`clausal/repl.py`, `clausal/_install_ipython.py`), **not** in the compiler: the
compiler stays uniformly strict-by-default, and the REPL is the single caller
that opts out. This mirrors Python's own split between a friendly interactive
prompt and `-W error` for programs.

## Deprecation notice

`-strict_atoms` becomes redundant once strict is the default, so it is
deprecated but retained (some authors value the explicit intent marker, and
existing files should keep working).

- New warning class `ClausalStrictAtomsDeprecationWarning(DeprecationWarning)`.
- Emitted **at most once per process**, guarded by a module-level
  `_strict_atoms_deprecation_emitted` boolean in `compiler_v2` — explicitly
  *not* relying on the `warnings` once-per-location dedup filter, so it is
  exactly-once regardless of the consumer's warning-filter configuration.
- Message states that the directive is redundant with the strict default and
  safe to delete.
- Introduced in Phase 3. Intent is informational (let authors know), not to nag
  per file.

## Testing

- **New-behavior unit tests** (Phases 1 & 3):
  - `-implicit_atoms` mints an undeclared bare atom.
  - A neither-directive file raises `NameError` after the flip.
  - A both-directives file raises the mutual-exclusion error.
  - `-strict_atoms` still raises on undeclared atoms and fires the deprecation
    warning **exactly once** across two loads in a single process.
- **REPL test:** an interactive snippet referencing an undeclared bare atom
  succeeds (mints) even with the strict file default in force.
- **Codemod idempotency:** running the codemod twice adds the directive once and
  never touches a file that already carries `-strict_atoms`.
- **Existing suite** is the primary regression net at Phases 2 and 3.

## Touch points

- `clausal/pythonic_ast/nodes.py` — add `ImplicitAtomsDeclaration`.
- `clausal/templating/term_rewriting.py` — `_handle_implicit_atoms_directive`,
  dispatch wiring, updated known-directives message.
- `clausal/logic/compiler_v2.py` — invert the mint/raise decision in
  `_auto_mint_bare_atoms`; add the mutual-exclusion check; add the
  deprecation-warning guard and warning class.
- `clausal/repl.py`, `clausal/_install_ipython.py` — pin implicit mode for
  interactive sessions.
- Codemod script (throwaway, kept under `tools/` or `implementation_plans/`) for
  Phases 1 and 5.
- Docs: `docs/directives.md` (add `-implicit_atoms`; mark `-strict_atoms`
  deprecated; restate the default), `docs/syntax.md` (atoms callout),
  `docs/builtins.md` (cross-reference).

## Out of scope

- Any `warn` (mint-and-warn) runtime state — explicitly rejected in favor of the
  staged binary flip.
- Downstream-repo migration — each consumer migrates on its own schedule.
- A project-level or env-var default switch — not needed under the per-file
  escape-hatch model; can be revisited if downstream ergonomics demand it.
- Changes to atom reification, unification, hashing/dict-key behavior, or
  predicate (arity ≥ 1) scoping.

## Open decisions deferred to implementation

- The exact membership of the Phase 4 pilot set.
- Final home for the codemod script (`tools/` vs. `implementation_plans/`).
