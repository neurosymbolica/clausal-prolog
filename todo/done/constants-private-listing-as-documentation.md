# Allow constants in `-private` as a documentation-only listing

**Filed:** 2026-08-25, from the constants-feature retrospective.

Atoms and predicates can be *documented* as internal via `-private` (advisory, never a
barrier — Clausal has no access control). Constants currently cannot be listed in either
`-module` or `-private` (both raise SyntaxError: "constants are public module globals — no
export listing needed"), so there is no advisory-visibility channel for them at all: a
maintainer cannot even signal "this constant is an implementation detail".

Proposal: accept constant-shaped names in `-private` as a documentation no-op (mirroring the
existing "visibility is advisory" stance), keep `-module` rejecting them (they are always
public; an export list entry would imply a distinction that does not exist). The
constants-reflection builtin (see `module_constants` work) could then expose the
private-listed flag so tooling can filter.

Cheap: relax one branch in `_handle_private_directive` (term_rewriting.py) + record the
names + one test + a docs sentence in directives.md.
