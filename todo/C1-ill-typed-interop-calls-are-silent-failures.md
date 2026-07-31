# C(i) — an ill-typed py-interop call is indistinguishable from a legitimate "no"

**Filed:** 2026-07-30, from a review of study 13 in clausify-executor-train.
**Repo:** clausal. **Independent of todo B**, but feeds the same message pipeline —
land B first if doing both, so the new notes have somewhere to appear.
**Needs a study run:** NO.

## Symptom

`clausal/modules/py/datetime.py:222-236`, `_date_add_3`: when the `isinstance` check
fails, the generator does a bare `return`. In Prolog terms the goal simply has no
solution. There is no way for the caller — human or model — to distinguish

  - "this date genuinely has no successor under these constraints" from
  - "you passed an `int` where a `timedelta` is required".

This is a large share of what *creates* the unsatisfiable-goal situations that todo B is
about. Study 13's `study_schengen_max_stay_r1` stalled for 7 identical attempts with
`date_add/3` called with an integer as one of three stacked root causes; the model wrote
a 120-line debugging monologue into `computation.clausal` as comments, correctly guessing
*"Perhaps `window_days_used` expects a different format for HISTORY?"*, and had no way to
confirm it.

## The change

Two parts, both cheap:

1. **Record the type mismatch as a diagnostic note.** At minimum during the diagnostic
   re-run, when a py-interop predicate bails on an `isinstance` guard, record
   `date_add/3 was called with int where timedelta is required`. Audit the other
   `clausal/modules/py/` builtins for the same bare-`return`-on-type-mismatch shape; this
   is a pattern, not one function.

2. **Load-time lint for `[H|T]`.** A clause head containing `BitOr` over list literals is
   almost certainly Prolog cons syntax written by someone who does not know this DSL
   spells it `[H, *T]`. Emit *"did you mean `[H, *T]`?"*. Study 13's
   `study_working_time_average_r1` died on exactly this; the engine even leaked the tell
   (the near-miss rendering printed `wt_compliance(BitOr(None, [_, work], []), ...)`) and
   the model never decoded it.

## Deliberately NOT proposed

Raising `type_error` instead of failing silently. That would be more correct ISO-wise but
changes program semantics for every existing caller, and a goal that currently fails
quietly would start throwing. The diagnostic-note route gets the information out without
that blast radius. If someone wants the stricter behaviour it should be its own todo with
its own argument.

## Verify

`study_working_time_average_r1` and `study_schengen_max_stay_r1` scratch trees under
`/workspace/clausify-executor-train/_reruns/study13/`. Assert the lint fires on the first
and the type note appears on the second.
