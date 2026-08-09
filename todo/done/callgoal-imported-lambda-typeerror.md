# RESOLVED: call_goal of a "lambda" with a non-logic-var head name → Python TypeError

**STATUS: RESOLVED 2026-06-26.** Root cause found; it was **not** about imported
predicates at all (that was a red herring from the original repro). Fixed by
turning the raw Python `TypeError` into a proper ISO `type_error(callable, _)`.

## Resolution (2026-06-26)

**Root cause — a mis-named lambda head variable, nothing to do with imports.**
The repro's lambda head was `(ID, P, St, C)`. Logic-variable names must be
ALL-CAPS or `_leading` (`clausal/templating/term_rewriting.py:_is_logic_var_name`),
and `"St".isupper()` is **False** (lowercase `t`). So `_extract_arrow_lambda_params`
rejected the head and the `<-` arrow was parsed as a **`Predicate` rule literal**
(the assertz shape) instead of a `Lambda` — exactly per the by-design
`test_functor_head_stays_predicate`.

That raw `Predicate` AST node was then passed to `call_goal`. Every Pythonic AST
node is `callable` (each gets a field-replacement `__call__` from `@node_class`),
so `call_goal`'s `callable(goal_val)` guard accepted it, and
`_ensure_trampoline_dispatch` wrapped the node via `_simple_to_trampoline`. The
node's keyword-only `__call__` was then invoked with positional dispatch args →
`node_class.<locals>.__call__() takes from 1 to 3 positional arguments but N were
given`.

This also explains why the earlier minimization attempts failed: they used
all-uppercase head names (`I, P, S, C`) which ARE logic vars, so those arrows
became proper Lambdas and worked. The trigger was purely the `St` naming — fully
reproducible **kit-free** with `((K, V, St) <- loc(K, V))`.

**Fix.** `clausal/logic/builtins/_registry.py::_ensure_trampoline_dispatch` now
rejects Pythonic AST `Node` goal values with
`LogicException(type_error("callable", goal, <hint>))` — a catchable Clausal error
whose context string points at the logic-variable-naming rule. This is the single
chokepoint for call_goal/call/maplist/foldl/include/… so every higher-order
builtin is covered.

**Regression test.**
`tests/test_lambdas.py::TestLambdaImport::test_call_goal_of_predicate_literal_raises_logic_error`
— asserts the mixed-case-head `call_goal` raises `error(type_error(callable, _))`
rather than a raw `TypeError`. Full suite: 8130 passed, same 6 pre-existing
unrelated failures as baseline.

---

## Original investigation notes (kept for history)

**STATUS: OPEN — active investigation target for this bug-fix clone.**

**Opened 2026-06-25** from real-world exercise (an external authoring harness's formalization kit). Filed
as an investigation, not a minimized bug — the trigger is context-dependent and I
could not reduce it below the shape in the repro. **Does not block the kit** (its
own 6-arity dispatcher predicate uses the same `call_goal/5` and passes), so low urgency; but it is
a real Python-level crash surfaced to user code, which should never happen.

## Symptom

```
node_class.<locals>.__call__() takes from 1 to 3 positional arguments but 7 were given
```
Raised at solve time (a raw Python `TypeError`, not a Clausal failure/exception) when
`call_goal` invokes a multi-arg lambda whose body reaches an **imported** predicate.

## Repro

`todo/callgoal_imported_lambda_repro.clausal` — run from a downstream helper
library's kit checkout (so the library's own module resolves). The CONTROL passes; the BUG test raises the TypeError:

```clausal
-import_from(vocab_lib, [check_ge, attr, unmet])
requirement("age_gte_18", PROFILE, STATUS, "cite_age") <- (
    check_ge(PROFILE, "age", 18, "age_gte_18", STATUS))   # check_ge is IMPORTED
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
| `call_goal` of 2-arg lambda → local pred that calls imported `check_ge` | OK |
| **`call_goal` of 4-arg lambda → `requirement/4` → imported `check_ge` (list profile arg)** | **TypeError** |
| The SAME `call_goal/5` driven through the kit's own dispatcher predicate (call site *inside* the downstream helper library, lambda passed as a var across the module boundary) | **OK** (19/19) |

So it is NOT just "imported predicate in body" and NOT just arity. The distinguishing
factors between the failing top-level case and the working dispatcher-predicate case are
candidates for the root cause:
- **Call site module**: failing call_goal is in the *caller's* module with an
  **inline lambda literal**; the working one is inside the downstream helper library with the lambda
  **passed as a bound variable** (`REQ_PRED`) across the import boundary.
- **Arg threading**: the failing case threads a **list** (`[attr("age",10)]`) and an
  unbound output through the lambda into an imported predicate.

## Minimization attempts (negative results — narrowing, 2026-06-25)

Two self-contained, **kit-free** repros with the SAME structural shape **do NOT
reproduce** (both pass against stable clausal at HEAD `725a6ca5`):
1. A minimal exported `mcheck/5` doing list-profile lookup, reached via a 4-arg
   lambda `((I,P,S,C) <- req(I,P,S,C))` where `req` calls the imported `mcheck`.
2. Same, but `mcheck` given three clauses incl. a `not mhas(...)` branch that
   constructs a list status `miss([KEY])` (mirroring `check_ge`'s unknown clause).

So the trigger is **NOT** merely "a 4-arg lambda whose body reaches a cross-module
imported predicate." It depends on something specific to the real downstream helper
library (size / compilation path, or a particular predicate/clause in the
`requirement -> check_ge -> profile_get` chain the minimal stand-in doesn't capture).
The reliable repro is the kit-based `callgoal_imported_lambda_repro.clausal` (run
from the downstream helper library's kit checkout so its module resolves). **Next
minimization step:** copy the helper library's module locally and delete
clauses/exports until the crash vanishes — the last deletion points at the cause.

## Suggested investigation angles

1. Diff the call_goal dispatch path for (a) inline-lambda-literal at the call site vs
   (b) lambda bound to a var then passed — the `node_class.__call__` arity mismatch
   ("7 given, takes 1–3") suggests the lambda node is being applied with the wrong
   number of positional args in one path.
2. Check whether name-resolution of the imported predicate inside an inline lambda
   (lexical/Pythonic resolution, per docs/import.md) builds a different node shape
   than when the lambda is resolved in the library module.
3. Bisect against the recent head-literal / solve-cache commits (≤ 725a6ca5) — the
   dispatcher predicate's direct `call_goal` test **passed earlier in the same session** before
   the 2026-06-25 batch landed, so a recent change may have shifted this path.
   (Caveat: that earlier pass may have been a mid-edit transient; verify.)

## Done when

- The BUG test in `todo/callgoal_imported_lambda_repro.clausal` either passes or
  raises a proper Clausal error (never a raw Python TypeError).
- A regression test covers `call_goal` of an inline multi-arg lambda whose body
  calls an imported predicate.
