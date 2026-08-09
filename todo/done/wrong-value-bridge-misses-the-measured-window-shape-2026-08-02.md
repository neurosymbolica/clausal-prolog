# The merged wrong-value bridge does not fire on the incident it was built for

**Filed** 2026-08-02 (external authoring harness team), immediately after the
b5142dc3 merge went live. This is a follow-up to
`failed-goals-have-no-derivation-trace-2026-08-02.md`, whose headline incident —
`date_window/rolling_window_rule`, "MAX = 0" — still reports with ZERO derivation output
under the merged diagnostics.

## Repro (exact, from the harness side)

    cd <external harness checkout>
    CLAUSAL_TEST_DIAG_BUDGET=60 python3 -c "
    import sys; sys.path.insert(0,'.')
    from pathlib import Path
    from auto.runclausal import run_clausal
    ok, out = run_clausal(Path('/tmp/window_r1/scratch/date_window/rolling_window_rule/'
                               'tests/test_public_interface.clausal'))
    print(out)"

(The scratch tree is archived under the harness checkout's archived-run directory
if /tmp is gone.)

Observed, with a 60s budget and no budget-exceeded note: all four failing tests still
print only the old ladder —

    goal 2 of 2 failed:
      STATUS is date_window.rolling_window_rule.eligible
    bindings at failure: STATUS = ineligible, ...
    no solution (this conjunct is not a predicate call, so there is no nearest solution to show)

No producer descent, no findall-collapse leaf, nothing new.

## The shape, precisely (candidate reasons the bridge's conditions miss it)

- The failing conjunct is `STATUS is <module-qualified atom>` — goal 2 of 2. Whether
  this parses as the Compare/non-Call node the bridge triggers on is worth checking
  first (the atom is dotted: `date_window.rolling_window_rule.eligible`).
- The producer (goal 1, `..._assess(...)`) SUCCEEDED, binding STATUS = ineligible; the
  defect is two call levels down (`window_eligibility` -> `max_extra_days`).
- The inner findall did NOT collapse to []: it collapsed to `[0]` (the LENGTH=0 probe
  succeeds trivially; every LENGTH>0 probe fails). If the collapse sentinel's gate is
  "body has no solution", a one-solution collapse escapes it — and the `[0]` shape was
  named in the original todo as the measured signature (`max_list([0]) = 0`).
- A companion test in the same file fails as a direct wrong value (`MAX == 90` /
  `MAX = 0`) with the producer `max_extra_days(...)` immediately before it — the
  simplest possible instance of the shape, also silent.

`trigger_threshold_rule` (archived sibling, same harness path) shows the
identical silence on its `triggered`/`not_triggered` variant.

The forall element-naming and throw-through-findall halves of the merge are working as
advertised; this note is about the wrong-value bridge only.

## Outcome (2026-08-02)

Diagnosed against the archived scratch tree (in-process instrumented re-runs of
`diagnose_failure`, then the real harness repro).  THREE causes bit — one of
them not on the candidate list:

1. **Query compile crash on rich-bound Vars (not enumerated above; the reason
   candidates 1/2 looked plausible).**  `term_to_ast_expr` derefs bound Vars at
   compile time (`terms_to_ast.py`) and had no lowering for a value like
   `datetime.date` — it raised `NotImplementedError`.  Every descent probe that
   re-solves goals under live bindings (the scan's findall re-run, the collapse
   finding's body walk, deeper `_descend`s) compiles through
   `_compile_as_query`; once the prefix bound `ENTRY_DATE` to a `date`, every
   probe died at compile and the catch-alls silently discarded the finding.
   Fixed in the compiler: `_collect_vars(goal, include_bound=True)` registers
   live BOUND Vars for the query path, and `term_to_ast_expr` falls back to
   referencing a registered bound Var by name (runtime deref yields the value)
   instead of raising.  Strictly additive: the fallback fires only where the
   old code raised.

2. **Candidate 3 — the `[0]` one-trivial-solution collapse escaped the gate.**
   `_findall_collapse_finding` required the body to have NO solution; the
   measured bag `[0]` has exactly one (the LENGTH=0 probe).  Now a non-empty
   all-zeros bag re-walks the body with a `template is not 0` disequality
   injected after the conjunct that introduces the template variable
   (`_trivial_collapse_probe`), and names the first NON-trivial failure.  The
   deepest truthful leaf on the repro is `between(0, LENGTH - 1, DAY_OFFSET)`
   — this engine does not evaluate arithmetic args to `between/3`, so the
   inner findall body fails there for every LENGTH > 0.  (The post-mortem's
   guess of `window_days_used` was one conjunct too deep: the body never got
   that far.)

3. **Candidate 4 — depth bound, silently.**  The scan's recursion through
   SATISFIABLE wrappers was capped at `DIAG_MAX_DESCENT_DEPTH=2`; the assess
   chain needs 4 (assess → decide → window_eligibility → max_extra_days).
   The scan now has its own `DIAG_MAX_COLLAPSE_DEPTH=5` bound and, when that
   bound stops it, SAYS so (`_note_depth_stop`) instead of going silent — the
   failing-call descent keeps its pinned 2-level cap.

Candidates 1 and 2 did NOT bite: the dotted-atom comparison parses into a
non-Call node the bridge already triggers on, and the Var-identity producer
lookup found the succeeded goal-1 producer in every measured test (pinned in
`test_dotted_atom_comparison_reaches_producer` anyway).

Also fixed en route: `_reified_findall_body_goal` picked the FIRST findall in
the file as the reified twin, rendering the outer findall's source text
against the inner findall's line number; it now searches the owning clause
(by position) first.  And a failing leaf that consumes a collapsed bag
(`length(VALID_DAYS, LENGTH)` with `VALID_DAYS = []`) now names the feeding
findall's swallowed failure beneath it (`_collapsed_findall_feeding`, gated
by bag→leaf Var identity so a legitimately-empty unrelated findall is never
blamed).

Report on the repro now (all four failing tests, both archived trees):

    the value it compares was produced by date_window.rolling_window_rule.max_extra_days(...),
      which succeeded with a wrong value; that producer's failing route:
    a findall whose body succeeds only for the trivial value 0 — it silently
      collapsed to [0]; the first non-trivial candidate fails at:
      computation.clausal:90  window_is_valid_for_length(HISTORY, ENTRY_DATE, LENGTH, LIMIT, WINDOW_SIZE)
        ... LENGTH = 1 ...
        computation.clausal:115  length(VALID_DAYS, LENGTH)
            VALID_DAYS = []
            a findall whose body failed for every candidate — it silently collapsed to an empty result:
              computation.clausal:105  between(0, LENGTH - 1, DAY_OFFSET)
                LENGTH = 1

All existing report lines are byte-identical; the new lines are additive
descent/note lines.  New pins in `tests/test_testing_descent.py`: the dotted
atom shape, the `[0]` collapse (with the nested empty-bag chain), the
deep-wrapper chain past the old depth bound, and the depth-exhaustion note.
