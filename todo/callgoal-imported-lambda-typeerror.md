# INVESTIGATION: call_goal of a lambda that reaches an imported predicate → Python TypeError

**Opened 2026-06-25** from real-world exercise (clausify formalization kit). Filed
as an investigation, not a minimized bug — the trigger is context-dependent and I
could not reduce it below the shape in the repro. **Does not block the kit** (the
`assess/6` engine uses the same `call_goal/5` and passes), so low urgency; but it is
a real Python-level crash surfaced to user code, which should never happen.

## Symptom

```
node_class.<locals>.__call__() takes from 1 to 3 positional arguments but 7 were given
```
Raised at solve time (a raw Python `TypeError`, not a Clausal failure/exception) when
`call_goal` invokes a multi-arg lambda whose body reaches an **imported** predicate.

## Repro

`todo/callgoal_imported_lambda_repro.clausal` — run from `/workspace/clausify/kit`
(so `formalize_lib` resolves). The CONTROL passes; the BUG test raises the TypeError:

```clausal
-import_from(formalize_lib, [check_gte, attr, unmet])
requirement("age_gte_18", PROFILE, STATUS, "cite_age") <- (
    check_gte(PROFILE, "age", 18, "age_gte_18", STATUS))   # check_gte is IMPORTED
Test("BUG") <- (
    call_goal(((ID, P, St, C) <- requirement(ID, P, St, C)),
              "age_gte_18", [attr("age", 10)], S, _),
    S is unmet("age_gte_18"))
```

## What triggers it vs not (isolation so far)

| Case | Result |
|---|---|
| `call_goal` of 2-arg lambda, **local** body | OK |
| `call_goal` of 4-arg lambda, **local** body (`q/4` that just binds) | OK |
| `call_goal` of 2-arg lambda → local pred that calls imported `check_gte` | OK |
| **`call_goal` of 4-arg lambda → `requirement/4` → imported `check_gte` (list profile arg)** | **TypeError** |
| The SAME `call_goal/5` driven through kit `assess/6` (call site *inside* `formalize_lib`, lambda passed as a var across the module boundary) | **OK** (19/19) |

So it is NOT just "imported predicate in body" and NOT just arity. The distinguishing
factors between the failing top-level case and the working `assess/6` case are
candidates for the root cause:
- **Call site module**: failing call_goal is in the *caller's* module with an
  **inline lambda literal**; the working one is inside `formalize_lib` with the lambda
  **passed as a bound variable** (`REQ_PRED`) across the import boundary.
- **Arg threading**: the failing case threads a **list** (`[attr("age",10)]`) and an
  unbound output through the lambda into an imported predicate.

## Suggested investigation angles

1. Diff the call_goal dispatch path for (a) inline-lambda-literal at the call site vs
   (b) lambda bound to a var then passed — the `node_class.__call__` arity mismatch
   ("7 given, takes 1–3") suggests the lambda node is being applied with the wrong
   number of positional args in one path.
2. Check whether name-resolution of the imported predicate inside an inline lambda
   (lexical/Pythonic resolution, per docs/import.md) builds a different node shape
   than when the lambda is resolved in the library module.
3. Bisect against the recent head-literal / solve-cache commits (≤ 725a6ca5) — the
   `assess/6` direct `call_goal` test **passed earlier in the same session** before
   the 2026-06-25 batch landed, so a recent change may have shifted this path.
   (Caveat: that earlier pass may have been a mid-edit transient; verify.)

## Done when

- The BUG test in `todo/callgoal_imported_lambda_repro.clausal` either passes or
  raises a proper Clausal error (never a raw Python TypeError).
- A regression test covers `call_goal` of an inline multi-arg lambda whose body
  calls an imported predicate.
