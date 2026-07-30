# Design question: a term cannot cross between two live copies of the package

**Filed:** 2026-07-30, splitting the undecided half out of
[[functor-identity-leaks-across-modules-in-one-process]].

**Severity:** low as a bug, medium as a decision. Nothing in-repo hits it; it is
reachable only by importing the `clausal` package twice into one process, which
today means `sys.modules` surgery. It needs a *decision* rather than a patch,
because every available answer trades something real away.

## The situation

Term identity is nominal on the metaclass: `is_term_instance(obj)` is
`isinstance(type(obj), PredicateMeta)`. Two live copies of the package means two
unrelated `PredicateMeta` class objects, so a term minted by one copy is simply
not a term to the other — it walks and quacks like a functor instance and fails
every check.

As of `fix/functor-identity-cross-module` each copy is at least internally
consistent (the C accelerator's single registration slot is claimed once and
never stolen), and the failure now explains itself instead of claiming to want a
functor instance while holding one. What is left is the genuinely *mixed* flow,
which no per-copy policy can rescue:

    copy 1's captured _load_module  ->  mints the head class with copy 1's PredicateMeta
    the generated module body       ->  re-resolves `clausal.*` via sys.modules -> copy 2
    copy 2's Database.assertz       ->  head_key(head) -> not a term. Correctly.

Reproduction, ~15 lines, no external repo:
`tests/test_second_package_copy_term_identity.py::test_term_crossing_between_copies_is_refused_with_a_precise_message`.

## Options, with what each costs

1. **Leave it as an error with a precise diagnostic.** Where we are now. Costs
   nothing; means a two-copy process is unusable rather than slow. Defensible,
   because the honest statement is "one clausal package per process" and the
   message now says exactly that.

2. **Refuse the second copy loudly at import time.** Turns a confusing
   mid-execution `TypeError` into an immediate, attributable `ImportError` at the
   moment the mistake is made. Attractive, but it breaks callers that re-import
   deliberately — including the exact downstream test that surfaced this
   (`test_checker_does_not_import_clausal`, which asserts a *non*-import and then
   legitimately re-imports) — and its blast radius across the ~22 out-of-tree
   consumers under `packages/` cannot be established from in-repo tests alone.
   Needs an audit before it can be chosen, and probably an opt-out.

3. **Make term identity structural instead of nominal**: treat anything whose
   type carries a `_fields` tuple as a term. Bridges the crossing case and
   nothing else needs to change at the call sites. But it widens what counts as a
   term engine-wide — every unrelated class with a `_fields` attribute becomes a
   term — and the accelerated path is C, so it needs a rebuilt `.so` to avoid
   silently reverting to nominal on the fast path. This is the redesign; it
   should not be undertaken to serve a pathological process shape.

4. **Intern one class per `(module, name, arity)`**, as the parent todo
   originally suggested. Does *not* fix this: two copies would hold two interning
   tables and two sets of interned classes, relabelling the same incompatibility.
   Recorded so it is not proposed again.

## Recommendation

Stay on option 1 unless a real consumer needs two copies. If the pressure comes
from harnesses doing `sys.modules` surgery, the cheaper fix is upstream of the
engine: assert non-import in a subprocess. Option 2 is the only one worth
costing out, and only after auditing `packages/` for deliberate re-import.
