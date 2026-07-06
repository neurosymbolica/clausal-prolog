# fix(A03-F002): destructive reuse corrupts containers behind nondet prefixes

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/03-compiler-goals/findings.md` A03-F002
**Tests:** `tests/audit_2026_07_05/test_03_compiler_goals.py::TestF002DestructiveReuseNondetPrefix` (3 xfail — flip to pass)

## Bug

DR safety criterion 5 ("all preceding goals deterministic — no choice
points can backtrack through the mutation",
`implementation_plans/compiler/todo/destructive_reuse_optimization_issue.md`
§6) is enforced via `tro._is_deterministic_op_ir`
(`destructive_reuse.py:129`), which wrongly classifies `MemberIn` and
`Branch` as deterministic (A03-F001). The untrailed in-place mutation then
survives backtracking:

    drm(OUT) <- (SRC is [1,2], X in [10,20], append(SRC, [X], OUT))
    → [1,2,10] then [1,2,20,20]        # second solution built from corrupted list

`dict_put/4` and `set_union/3` are analysis-eligible in the same shape
(runtime corruption not separately reproduced; `append` is).

## Fix direction

Fixing the classifier (`fix-A03-tro-nondet-prefix.md`) fixes this too — the
DR tests are the acceptance gate that the fix covers both consumers. If the
classifier is instead split per-consumer, DR needs the STRICTER variant
(any multi-solution prefix is fatal here: wrong values, not just lost ones).

## Acceptance

- `drm`/`drb` yield `[[1,2,10]], [[1,2,20]]`; `dict_put` analysis probe
  returns not-eligible.
- Controls stay green: `drmc` (live source), `drok` (det prefix DR still
  applies — keep the optimisation!), Alternate-prefix ineligibility.
