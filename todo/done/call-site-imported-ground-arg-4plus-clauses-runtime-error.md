# clausal engine bug: `call_site` optimisation breaks GROUND-argument calls to IMPORTED predicates with >= 4 clauses

> **FIXED 2026-07-11.** Root cause: `call_site` bound the RAW SIGNAL-mode
> bucket function (`pred._index_plans[pos][key]`, compiled with
> `emit_done=False`) into the caller's globals and drove it directly via
> `StepGenerator`. Raw buckets deliberately omit the terminal
> `yield (fail, DONE)` and loop-on-TRO-tail-call — the dispatch closure
> normally supplies both — so the generator returned with no final yield.
> Only imported callees trigger it because predicates are locked at
> end-of-module-load (`import_hook.py` step 7): same-module callees are
> still unlocked when their callers compile, so no bucket-ref hint is
> written; >= 4 clauses is `_INDEX_THRESHOLD`. Fix:
> `_make_call_site_bucket_trampoline` (compiler/arg_index.py) wraps every
> bucket exposed via `_index_plans` / `_index_plans_joint` to complete the
> trampoline contract (terminal DONE + TRO re-dispatch through the full
> dispatch fn). Regression tests:
> `tests/test_callsite_imported_ground_call.py` (+ fixtures
> `callsite_bucket_lib/use.clausal`) and
> `TestDirectBucketCallSiteExecution` in
> `tests/test_callsite_specialization.py`. The standalone repro referenced
> below lives in `the standalone repro directory (`repro/`, alongside this todo)` (all six rows PASS
> post-fix); the downstream domain's `CLAUSAL_DISABLE_OPT=call_site` workaround has been
> removed.

**Severity**: high — every input-mode `Test` clause of the shape
`Test(...) <- (fixture(P), pred(P, "expected"))` against an imported rulebase
predicate with >= 4 clauses raises instead of solving. Found while integrating
a downstream investment-screening rulebase domain (30 of its 46 input-mode tests were failing
with this error at baseline; nothing wrong with the domain).

**Where**: `/workspace/clausal` (engine), the **`call_site`** compiler optimisation
(`clausal/logic/compiler/…`; the enabled-optimisation set lives in
`clausal/logic/compiler/compile_ctx.py::_default_enabled_optimisations`,
`_ALL_OPTIMISATIONS = {"tro", "destructive_reuse", "call_site", "continuation_tco"}`).

**Repro**: `./repro/repro.sh` (self-contained, no domain dependency). Engine:
`/workspace/clausal` source tree, python 3.13.3 (same under the
`/workspace/clausal/venv` interpreter).

## Symptom

```
RuntimeError: StepGenerator inner generator returned unexpectedly (no final yield)
```

raised from `clausal/logic/solve.py::_drive_trampoline` →
`_drive_until_yield(sg)` (C `runtime/_trampoline`; the pure-Python `StepGen_send`
protocol check is the same). Under `python -m clausal.testing` the affected test
reports the error; when driven through embedded `solve()` on the same goal shape
it raises out of the generator.

## Minimal trigger — ALL FOUR ingredients required

1. a predicate with **>= 4 clauses** (3 clauses: works) whose argument position
   carries **head constants** (`category(P, "a") <- …` etc.);
2. the predicate is **imported into another module** (`-import_from`) — the same
   predicate defined in the calling module works;
3. the call site is **inside a compiled clause** (e.g. a `Test/1` body) — calling
   the imported predicate directly from Python via `solve()` works;
4. the constant-bearing argument is **GROUND at the call site**
   (`category(1, "a")`) — calling with an unbound variable and comparing
   afterwards (`category(1, D), D is "a"`) works.

## Decision matrix (from `repro/repro.sh`, all verified 2026-07-11)

| # | clauses | constants | defined | call style | result |
|---|---|---|---|---|---|
| 1 | 4 | 4 distinct | imported | ground `category(1, "a")` | **RuntimeError** |
| 2 | 4 | 4 distinct | imported | unbound `category(1, D), D is "a"` | pass |
| 3 | 3 | 3 distinct | imported | ground | pass |
| 4 | 4 | **2 distinct** | imported | ground | **RuntimeError** |
| 5 | 4 | 4 distinct | **same module** | ground | pass |
| 6 | 4 | 4 distinct | imported | ground, `CLAUSAL_DISABLE_OPT=call_site` | pass |
| — | 5 | 5 distinct | imported | ground (incl. LAST-clause match) | **RuntimeError** |

Row 4 shows the trigger is the **clause COUNT (>= 4)**, not the number of
distinct constants — presumably the threshold at which `call_site` switches to
an indexed/bucketed dispatch strategy for the imported callee. Row 6 isolates
the culprit: disabling **`call_site` alone** fixes it; disabling `tro`,
`destructive_reuse` or `continuation_tco` individually does NOT
(`CLAUSAL_DISABLE_OPT=<name>` sweep).

## Likely history

Probably predates but was SURFACED by the A04 fix (commit `8027e88d`,
`todo/audit-2026-07-05/done/fix-A04-drive-until-yield-runtime-error.md`): before
that fix, C `_drive_until_yield` swallowed every `RuntimeError` and reported
"search exhausted" — so this same defect would previously have manifested as a
silent **0-solutions wrong answer** on ground-argument call sites (arguably
worse). The StepGen protocol error itself ("inner generator returned
unexpectedly", `StepGen_send` `runtime/_trampoline.c:213-223`) is the pre-existing
masked failure mode named in that audit note.

## Where it bit in production

The downstream investment-screening rulebase domain: all input-mode self-tests calling
`notifiable(P, "notifiable")`, `investor_category(P, "not_foreign")`,
`interest_test(P, 10, _)` etc. (imported predicates with 4+ clauses and
constant heads) errored; output-mode variants of the same queries passed.
The domain's test runner and negative-control suite currently export
`CLAUSAL_DISABLE_OPT=call_site` as a documented workaround (see the domain's own
differential-test notes) — **please drop that workaround once this is
fixed** (grep for `CLAUSAL_DISABLE_OPT=call_site` under the domain's checkout).

## Acceptance for the fix

1. `./repro/repro.sh` → all six rows PASS with no `CLAUSAL_DISABLE_OPT`.
2. Re-running the downstream investment-screening domain's test suite still ALL GREEN
   after deleting the two `export CLAUSAL_DISABLE_OPT=call_site` lines
   (123 tests + 4 negative controls).
3. A regression test in the engine suite covering: imported predicate, >= 4
   clauses, ground head-constant argument at a compiled call site — first,
   middle and LAST clause selected.
