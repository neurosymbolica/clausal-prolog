# The merged wrong-value bridge does not fire on the incident it was built for

**Filed** 2026-08-02 (formalizer-training harness team), immediately after the
b5142dc3 merge went live. This is a follow-up to
`failed-goals-have-no-derivation-trace-2026-08-02.md`, whose headline incident —
`eu/schengen_90_180_max_stay`, "MAX = 0" — still reports with ZERO derivation output
under the merged diagnostics.

## Repro (exact, from the harness side)

    cd /workspace/clausify-executor-train
    CLAUSAL_TEST_DIAG_BUDGET=60 python3 -c "
    import sys; sys.path.insert(0,'.')
    from pathlib import Path
    from auto.runclausal import run_clausal
    ok, out = run_clausal(Path('/tmp/schengen_r1/scratch/eu/schengen_90_180_max_stay/'
                               'tests/test_public_interface.clausal'))
    print(out)"

(The scratch tree is archived at
`/workspace/clausify-executor-train/_reruns/resume_schengen_r1` if /tmp is gone.)

Observed, with a 60s budget and no budget-exceeded note: all four failing tests still
print only the old ladder —

    goal 2 of 2 failed:
      STATUS is eu.schengen_90_180_max_stay.eligible
    bindings at failure: STATUS = ineligible, ...
    no solution (this conjunct is not a predicate call, so there is no nearest solution to show)

No producer descent, no findall-collapse leaf, nothing new.

## The shape, precisely (candidate reasons the bridge's conditions miss it)

- The failing conjunct is `STATUS is <module-qualified atom>` — goal 2 of 2. Whether
  this parses as the Compare/non-Call node the bridge triggers on is worth checking
  first (the atom is dotted: `eu.schengen_90_180_max_stay.eligible`).
- The producer (goal 1, `..._assess(...)`) SUCCEEDED, binding STATUS = ineligible; the
  defect is two call levels down (`stay_eligibility` -> `max_additional_days`).
- The inner findall did NOT collapse to []: it collapsed to `[0]` (the LENGTH=0 probe
  succeeds trivially; every LENGTH>0 probe fails). If the collapse sentinel's gate is
  "body has no solution", a one-solution collapse escapes it — and the `[0]` shape was
  named in the original todo as the measured signature (`max_list([0]) = 0`).
- A companion test in the same file fails as a direct wrong value (`MAX == 90` /
  `MAX = 0`) with the producer `max_additional_days(...)` immediately before it — the
  simplest possible instance of the shape, also silent.

`posted_workers_long_term_trigger` (archived sibling, same harness path) shows the
identical silence on its `triggered`/`not_triggered` variant.

The forall element-naming and throw-through-findall halves of the merge are working as
advertised; this note is about the wrong-value bridge only.
