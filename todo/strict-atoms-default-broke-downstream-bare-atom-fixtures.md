# Strict-atoms-by-default broke downstream bare-atom fixtures

**Found:** 2026-07-30, while accounting for the four failures reported in
[[functor-identity-leaks-across-modules-in-one-process]]. Three of them turned
out to be this, not that.

**Severity:** low for the engine (behaving as designed), but it is unmeasured
migration fallout in at least one out-of-tree consumer, and it *masked* an
unrelated engine bug for a day by firing first.

## What

Strict atom resolution became the default (merged to canonical main 2026-07-29).
A rulebase that references a bare atom without declaring it now raises

    NameError: strict_atoms: undeclared atoms 'art_1', 'art_2', 'met', 'req_a',
    'req_b' in gate_q_1

`/workspace/clausify-executor-train`'s `auto/tests/test_gate_query.py` has three
fixtures that do exactly that, e.g.

    _RB_REQ_FIXTURE = """-import_from(formalize_lib, [attribute, profile_get, unmet])
    requirement(req_a, PROFILE, met, art_1) <- profile_get(PROFILE, "flag", "true")
    ...

`req_a`, `met`, `art_1`, `req_b`, `art_2` are undeclared, so
`test_query_requirements_returns_frozenset`,
`test_query_requirements_unmet_profile` and
`test_query_requirements_key_name_collides_with_predicate` now fail — against
canonical `/workspace/clausal` as well as any branch, and in isolation. The fix
there is a one-line `-private([req_a, req_b, met, art_1, art_2])` per fixture.

## Why it is worth a todo here rather than only there

Two things:

1. **The default landed without a sweep of out-of-tree consumers.** These three
   are the ones that happened to be in front of me; nobody has checked the rest
   of `clausify-executor-train`, the `domains/` corpus, or `packages/`. If the
   count is large, that argues for a migration note or a deprecation window
   rather than N separate one-line fixes.

2. **It cost a day of misattribution.** The `NameError` fires during
   `compile_module`, before the clause heads exist, so in the reported run it was
   hidden behind an unrelated `TypeError` from `head_key` — and all four failures
   got written up as one mechanism. The recorded claim that
   "`pytest auto/tests/test_gate_query.py -q` -> 4 passed in isolation" was
   already stale when it was written.

## Action

* Sweep the known consumers for undeclared bare atoms and count them, before
  deciding between "fix each fixture" and "publish a migration note".
* Not an engine change: strict atoms are doing what they were built to do, and
  the diagnostic already lists every one of the five declaration routes.
