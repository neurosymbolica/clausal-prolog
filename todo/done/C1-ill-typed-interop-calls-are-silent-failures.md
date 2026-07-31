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

## Landed (2026-07-31)

Both parts, as specified.

1. **Type-mismatch notes.** `clausal/modules/py/__init__.py` grew a note
   collector (module-global sink, active only while
   `collect_type_mismatch_notes()` is entered) plus three guard helpers:
   `expect_type` (isinstance guard — unbound Var stays a silent mode signal,
   bound wrong type records "`pred` was called with `int` where `timedelta`
   is required (argument N)"), `note_mismatch` (shapes isinstance can't
   phrase: subclass exclusions, list-element types, mixed date/datetime
   comparability), and `note_rejected_call` (try/except twins around pure
   constructors — records the exception text, so `date(2024, 13, 1)` says
   "month must be in 1..12"). `clausal.testing.diagnose_failure` activates
   the collector around the whole re-run (descent included) and appends the
   deduplicated notes to `diag.notes`. Every bound-arg type guard across
   `clausal/modules/py/` was converted (datetime, csv, json, url, uuid,
   files, os, process, tcp, hash, hmac, pbkdf2, random, http, re);
   sqlite/imperial/units/logging audited — nothing matching the shape.
   I/O-error except-clauses (OSError etc.) deliberately stay silent: those
   are runtime failures, not ill-typed calls.

2. **Cons-syntax lint.** `_warn_cons_bar_head` in
   `clausal/templating/term_rewriting.py`, called from all three head paths
   (facts, `<-` rules, DCG rules). Fires on a head `BitOr` that is a direct
   element of a list display (`[H | T]`) or has a list-literal operand
   (`[W, S] | REST`, the study-13 shape); a `BitOr` over bare names stays
   silent (plausible clpb-style structural pattern). Message names the line,
   quotes the source, and says "did you mean `[H, *T]`?"
   (`ClausalLintWarning`, same channel as the `is not` lint).

Verified against both study-13 trees: the lint fires on
working_time_average's two cons heads (lines 58/65, source quoted); on
schengen, `max_additional_days` now diagnoses as descent-leaf
`computation.clausal:85/129` (COUNT = 0) **plus** the note "date_add/3 was
called with int where timedelta is required (argument 2)" — the fact the
study model spent 7 attempts guessing at. (The schengen scratch tree no
longer loads as-is — it froze mid-repair with a missing `within_limit`
export — so the check ran via a probe test importing its `computation`
module directly, with `/workspace/clausify` + `/workspace/clausify/kit` on
`PYTHONPATH`.)

Tests: `tests/test_py_interop_type_notes.py` (helpers, dedupe, e2e note
through the harness, descent survival, unbound-var silence),
`tests/test_lint_cons_bar_head.py` (both shapes, facts and rules, line
attribution, negative cases incl. `[H, *T]` and body `|`).
