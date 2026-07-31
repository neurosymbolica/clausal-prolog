# B — the assertion diagnostic stops one level above the cause

**Filed:** 2026-07-30, from a review of study 13 in clausify-executor-train.
**Repo:** clausal. **Depends on:** clausify-executor-train todo A landing first,
otherwise the extra detail this produces is elided before the model sees it.
**Needs a study run:** NO — verifiable against `clausal.testing` directly.

## The ladder today

`clausal/clausal/testing.py:673-760`, `_report_nearest`, has three rungs:

1. **One-arg generalization** (706-736) — frees each argument in turn; on a hit, prints
   *"the predicate DID have a solution, which did not unify (argument N differs)"* plus
   the near-miss solution. **Carries a value. Useful.**
2. **All-holes probe, satisfiable** (751-755) — prints *"the predicate has solutions, but
   none within one argument of this goal — two or more arguments differ"* **and shows no
   solution at all**, despite `_has_solution` having just proved one exists and
   `_first_binding` being one call away (see 744).
3. **All-holes probe, unsatisfiable** (757-760) — *"the predicate has no solution for ANY
   arguments at this point (check the goals that produced its inputs, or its own
   clauses)"*. Zero localization into the predicate's own clause bodies.

## Why it matters

Measured over study 13's goal-level failures, recovery tracks whether the message carried
a **value**, not which phase or domain it was:

| report contains | attempts | phase recovered |
|---|---|---|
| bindings visible (actual value shown) | 3 | **3/3** |
| exception with error text | 6 | 4/6 |
| 1-arg-differs + bindings | 13 | 4/13 |
| anything with "no solution for ANY arguments" | 29 | **0/29** |

*(Counts are the reviewer's slice; an independent recount over the same archive gave
58 goal-level attempts with 32 hitting the rung-3 branch. The proportions agree; the
0/29 recovery figure is the load-bearing claim and has not been independently recounted.)*

Rung 3 is a better-worded *"test X failed"*. No run that hit it ever escaped.

## The change

**Rung 3 — descend one level.** When the all-holes probe is unsatisfiable, for each clause
of the failing predicate run its body with the goal's generalized head bindings, using the
same goal-walker that already produces `goal N of M failed` for test bodies, and report the
first failing conjunct per clause with its bindings.

Expected output on the three reproduced cases:

  - schengen: `window_days_used(HISTORY, <date object>, 180, _) has no solution` — the
    wrong-type argument becomes visible.
  - vat: `RAW_PCT > 100 failed, RAW_PCT = 50` — names the contradictory guard directly.

**Rung 2 — print what you already computed.** The satisfiability proof at 744 has a
solution in hand. Render the first 1–3.

Bound descent at depth 1–2. The existing `$CLAUSAL_TEST_DIAG_BUDGET` deadline machinery
already threads through here (study 13's `crr_output_floor_r1` reports exceeding it), so
reuse it rather than adding a second budget.

## Verify

Reproduce from the archived scratch trees under
`/workspace/clausify-executor-train/_reruns/study13/`:

  - `study_schengen_max_stay_r1` — wrong arg type into `kit/rolling_window.clausal:149`
  - `study_vat_pro_rata_deduction_r2` — contradictory guards in one conjunction
  - `study_working_time_average_r1` — `[H|T]` cons syntax parsed as `BitOr`

Run `python -m clausal.testing` on each and assert the printed conjunct names the known
cause. No model, no GPU.

## Note

Everything printed derives from the producer's own rulebase and its own tests. Nothing
here touches sealed-oracle data, so there is no leak surface.
