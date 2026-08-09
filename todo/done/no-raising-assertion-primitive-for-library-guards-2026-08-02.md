# No raising assertion primitive for library guards — wf-guards fail silently inside findall

**Filed:** 2026-08-02, from an external authoring harness team.

## The need

Library authors (the harness's `kit/` shared modules) want well-formedness guards that
RAISE with a message when given malformed input — non-ground terms, wrong shapes, wrong
type. Silent logical failure inside a `findall` is indistinguishable from a legitimate
empty result: the `findall` collapses to `[]`, downstream aggregations (e.g. `max_list`)
return a default, and every verdict downstream flips silently.

## Measured incident

A rolling date-window authoring run — four full repair budgets could not locate the defect from the
test report (see `failed-goals-have-no-derivation-trace-2026-08-02.md` in this
directory for full measurements). The defect: the model passed a date OBJECT where kit
predicate `window_days_used` expects a `[Y,M,D]` triple (`REF_YMD`). The kit predicate
failed logically. The `findall` collapsed to `[0]`. The test report showed only:

```
max_additional_days ... MAX == 90 / bindings at failure: MAX = 0
```

If `window_days_used` had raised on the malformed `REF_YMD` argument, the error would
have propagated through the `findall` as an exception and appeared in the report's
RAISED path — which is the loud, well-diagnosed channel. The failure would have been
located on attempt 1.

The same shape applies to any kit predicate that receives unbound variables or wrong
shapes: `intervals_wf`, `distinct_days_total`, and other layer-2 wrappers all fail
logically on malformed input and all collapse `findall` silently.

## The gap (conditional)

If the Clausal engine does not already provide a `raise_error/1`-style builtin (or
a documented py-interop assertion module that library code can call), there is no
loud channel available to Clausal-side library authors. The only loud channel today is
a Python-side exception from a py-interop module, which requires dropping out of
Clausal syntax.

A parallel investigation may find an existing mechanism. This todo is written
**conditionally**: if no such primitive exists, this is what the library side needs.

## What the library side needs from the primitive

1. **Message with term rendering.** The raise message must be able to include the
   offending term in a human-readable form — e.g. `raise_error("window_days_used:
   REF_YMD must be [Y,M,D], got: ~w", [REF_YMD])` — so the test report names the
   bad argument, not just the predicate.

2. **Propagates through findall to the RAISED path.** The raised error must propagate
   out of a `findall` body (rather than being swallowed as a logical failure) so it
   reaches the test runner's exception handler and appears in the same diagnostic
   channel as Python-side exceptions. If the engine's `findall` catches all exceptions
   and converts them to failure, this requirement asks for an exception class or tag
   that `findall` re-raises rather than catches.

3. **Callable from Clausal clause bodies without py-interop syntax.** The guard should
   be expressible as a normal Clausal goal so kit authors do not need to embed Python.

4. **Composable with the existing `diagnose_failure` report.** Ideally the raised error
   includes enough context (predicate name, argument position, bad value) that the
   existing test report's RAISED path renders it without engine changes.

## Candidate designs (if no primitive exists)

**Candidate 1 — `raise_error/1` or `raise_error/2` builtin.**
A Clausal builtin that throws an engine-level exception carrying a formatted message.
`findall` would re-raise it (or the exception class would be excluded from `findall`'s
catch). The builtin is the standard Prolog-family approach (`throw/1`, `type_error/2`);
the design question for Clausal is which exception taxonomy it joins and how `findall`
interacts with it.

**Candidate 2 — blessed py-interop assertion module.**
A documented, supported module (e.g. `clausal.guards`) that exposes assertion
predicates (`assert_ground/2`, `assert_shape/3`) callable as Clausal goals. These
raise Python exceptions that the engine already propagates through `findall` as RAISED.
No new engine primitive is needed; the cost is that kit authors import a py-interop
module.

**Candidate 3 — wf-guard macro or annotation.**
A compile-time or load-time mechanism that attaches argument shape declarations to a
predicate and generates the raise on mismatch automatically. This is the highest-level
interface and the largest scope; it may subsume candidates 1 and 2 but requires
a design for the declaration syntax.

Any of the three candidates converts a silent `findall` collapse into a located,
translatable error on the first attempt, for the class of kit-call arity/shape
mistakes that the training harness has measured as the dominant repair-blocking case.

## Outcome

**The primitive already existed — no new builtin was added.** `throw/1`, paired with
the ISO `*_error` term constructors in `clausal/logic/exceptions.py`, already satisfies
all four requirements the library side listed. Verified end-to-end:

1. **Message with term rendering** — the thrown term carries a human-readable message
   *and* the offending culprit term (`throw(wf_bad_shape("… must be [Y,M,D]", REF_YMD))`),
   so the report names the bad argument, not just the predicate.
2. **Propagates through findall to the RAISED path** — `_compile_find_all_core`
   (`clausal/logic/compiler/control_constructs.py`) drives its inner sub-generator with a
   bare `for` loop and no exception handler, so a `throw` inside the findall body escapes
   it rather than collapsing to `[]`. It reaches `run_test`'s handler
   (`clausal/testing.py:271`) and `diagnose_failure` walks to the raising conjunct,
   rendering it on the `raised:` branch (`verb = "raised"`, `clausal/testing.py:158`) —
   the same loud channel as a Python-side exception.
3. **Callable from Clausal clause bodies without py-interop** — `throw/1` is an ordinary
   Clausal goal (`_compile_throw`); the guard predicate is plain Clausal.
4. **Composable with the RAISED report** — the raised term surfaces with the findall
   goal named and the culprit visible, no engine change needed.

A pre-existing Python-level test already covered `throw`-in-`findall` propagation at the
IR surface (`tests/test_exceptions.py::TestThrowInFindAll`), but nothing exercised the
**.clausal-surface guard-predicate → findall → RAISED-diagnostic** path end-to-end. That
is what was added.

### One strict-atoms wrinkle worth knowing (documented, not a blocker)

Under the strict-atoms default, a bare `throw(type_error(...))` in a `.clausal` file
trips the undeclared-atom guard (`type_error` is read as an undeclared term-class name).
Two working spellings, both now documented and tested: declare your own error functor in
`-private([...])` and throw it (it throws as a term-class *instance* with named fields),
or `from clausal.logic.exceptions import type_error` at the top of the file and throw the
constructor's `error(type_error(...))` result. Every prior `.clausal` `throw` in the tree
threw a plain string; the structured constructors had only ever been called from Python.

### What was verified / added

- **Test:** `tests/test_exceptions.py::TestRaisingGuardThroughFindAll` (2 tests) —
  proves a guard's `throw` propagates out of a `findall` to the RAISED diagnostic path
  (asserting `result.error` is the `LogicException`, the culprit term is carried, and the
  diagnostic's `raised` branch names the findall), plus a control that well-formed input
  flows through with no raise. Fixture: `tests/fixtures/raising_guard_lib.clausal`
  (carries `# clausal: no-collect` so its intentionally-raising Test is not auto-collected
  as a spurious failure).
- **Docs:** new section "Raising well-formedness guards in library code" in
  `docs/exceptions.md`, with two compilable+tested example blocks (own-functor and
  imported-`type_error`) showing kit authors the pattern and the strict-atoms spelling.

### Suite

Full suite from this worktree: **10872 passed, 136 skipped, 44 xfailed, 1 failed**
(`test_no_raw_untested_blocks`, a known-standing baseline failure — my change adds 0 new
violations to it; `exceptions.md:56`'s pre-existing `safe_div` block was already a
violation before this change). The second known-standing failure,
`test_F026_multi_star_splits_bounded_for_moderate_input`, was confirmed separately as its
usual timing-threshold flake (3.18s < 3.0s). No new failures introduced.

No new engine primitive, no parallel raising mechanism — a second one next to
`throw`/`catch` would only add confusing surface area. The `catch`/trampoline interaction
bug in `todo/catch3-does-not-catch-an-exception-from-a-trampolined-subgoal.md` is unrelated
and does not affect findall propagation (which uses a plain `for` loop, not `catch`).
