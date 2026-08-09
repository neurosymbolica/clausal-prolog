# `terms_to_goalop` crashes on an attributed variable in goal position

**Error:** `terms_to_goalop: goal shape not yet supported (AttVar): AttVar(_0)`

A CLP(ℤ)-constrained variable (produced by `==`) used **as a goal** (bare, in goal position) makes the
clause compiler raise an internal `terms_to_goalop` error at load time instead of either evaluating it
or giving a clean "not a callable goal" diagnostic.

## Minimal repro (4 lines — fails at `<load>`)
```clausal
go(R) <- (
    X == 5,
    R == X - 2,
    R                 % <- R is a CLP attributed var, used here as a bare goal
)
Test("attvar in goal position") <- (go(R), R == 3)
```
```
$ python -m clausal.testing attvar_min.clausal
  ...::<load> — terms_to_goalop: goal shape not yet supported (AttVar): AttVar(_0)
```

## Where it came from (real case)
A generated rolling date-window rulebase ended a clause with a bare bound variable as its final goal:
```clausal
decide_window_eligibility(REF_DATE, STAYS) <- (
    ..., REM == LIMIT - USED,
    If(REM >= 0, RESULT is "allowed", RESULT is "not_allowed"),
    RESULT                      % <- bare var in goal position -> AttVar crash at load
)
```
The rest of the rulebase is correct (its `days_used`/`days_remaining` logic scores 26/26 against the
oracle); this one construct blocks the whole public-interface test file from loading.

## Why fix it
- It surfaces from machine-generated rulebases, where "a variable accidentally in goal position" is a
  common mistake. The current message is an internal-shape crash, not a user-actionable error.
- **Minimum fix:** turn it into a clear, located error — e.g. *"`R` is not a callable goal (got an
  attributed/bound non-callable in goal position) in clause `go/1`"* — so the author can find it.
- **Consider:** whether an attributed var in goal position should be supported at all, or always rejected
  cleanly at compile time.

## Repro artifacts (on the box)
`/root/clausal-train/data/attvar_repro/`: `attvar_min.clausal` (the 4-line repro) and
`attvar_artifact.tgz` (the full generated rolling date-window rulebase + tests that triggered it).

Found via a local-model authoring baseline run in an external authoring harness (see its own
`formalization-program-state` / `.superpowers/sdd/progress.md`).

## Resolution — RESOLVED 2026-06-29

Chosen design (confirmed with the user): **reject a bare variable in goal position at
compile time** with a clear, located error. An intended meta-call must be written
explicitly as `call/1` (`call(R)`). This is loud and fast for the generated-rulebase
mistake case — far better than the alternative of silently failing the clause (which a
`call/1` auto-wrap would do for a bound non-callable).

**Root cause.** All Clausal logic variables are `AttVar` instances (`Var = AttVar`, see
`clausal/logic/variables/__init__.py`). A clause body whose goal is just a variable reaches
`terms_to_goalop._convert_inner` as an `AttVar` and fell through to the generic `_not_yet`
`NotImplementedError`. Only goals (never operands) flow through `_convert`, so any variable
arriving there is genuinely in goal position.

**Fix.**
- `clausal/logic/compiler/terms_to_goalop.py`: new `BareGoalVariableError`; `_convert_inner`
  detects a bare logic variable (`is_var`) and raises it with an actionable message.
- `clausal/logic/compiler/predicate.py`: both `compile_predicate_trampoline` and
  `compile_predicate_shallow` catch the error and re-raise it stamped with the offending
  predicate's `functor/arity` so the load-time message locates the clause.

Now surfaces as:
`AttVar(_0) is not a callable goal: a bare variable appears in goal position in predicate
go/1. If a meta-call was intended, wrap it as call/1 (e.g. call(R)).`

Tests: `tests/test_bare_goal_variable.py` (unit error shape + actionable message + located
load-time error). Related runtime precedent: commit 579e94b6 raised `type_error(callable)`
for non-goal AST nodes passed to `call_goal`.
