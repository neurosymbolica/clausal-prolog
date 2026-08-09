# BUG: a closure/lambda loses its callable arity when bound to a variable or nested in a compound term

> **RESOLVED 2026-06-26.** Root cause: a lambda only became a callable closure when it
> appeared *directly* as a call argument (`_hoist_lambda_args` hoisted it to a compiled
> `FunctionDef` in its defining context). In any other value position — the RHS of `is`
> (`Unify`), or nested inside a compound like `bundle((A,B)<-…)` — it was never hoisted, so it
> reached runtime as a raw `Lambda` AST node. `call_goal` then could not invoke it (after the
> adjacent `579e94b6` fix it surfaces a clean `type_error(callable, _)` instead of the raw
> `node_class.__call__ … N positional` TypeError, but the closure still didn't work).
>
> **Fix:** lambda hoisting is now recursive and covers all value positions:
> - `clausal/logic/compiler/control_constructs.py::_hoist_lambdas_in_term` — recursively
>   replaces every `Lambda` anywhere in a term (compound args, nested calls, lists) with a
>   `LoadName` ref to a compiled closure; `_hoist_lambda_args` uses it (fixes case C).
> - `clausal/logic/compiler/_lower_goalop_shared.py` `Unify` case — hoists lambdas on either
>   side of `is` and prepends the closure defs (fixes case B).
>
> A closure can now be threaded through a variable or bundled in a term and still invoked.
> Regression tests: `tests/test_lambdas.py::TestLambdaImport::test_lambda_threaded_through_local_var`
> and `::test_lambda_nested_in_compound_term`; the repro (moved to `todo/done/`) passes 3/3.
> Full suite: 8142 passed.

**Reported 2026-06-26** (found building a generic Clausal **planner** skeleton for a downstream
consumer: the engine
needs to receive the domain's hooks — goal oracle, action generator, requirement-satisfier — as closures.
A `Hooks(oracle, actions, satisfiers)` bundle term, and even threading a single closure through a local
variable, both fail; closures had to be passed as **separate direct literal arguments** to work.)

> Observed on `/workspace/clausal` (main). Please confirm on this clone's build — the recent
> `579e94b6 fix(higher-order): raise type_error(callable) for non-goal AST nodes in call_goal` is adjacent
> and may interact.

## Symptom

A lambda `((A, B) <- double(A, B))` is callable via `call_goal` when passed **directly** as a predicate
argument, but **not** once it has been unified into a variable (`G is ((A,B) <- ...)`) or nested inside a
compound term and extracted. In the broken cases `call_goal` mis-invokes it:

```
node_class.<locals>.__call__() takes from 1 to 3 positional arguments but 5 were given
```

i.e. the round-tripped closure is no longer recognized as a goal carrying its parameter arity, so `call_goal`
passes it the wrong number of arguments.

## Minimal repro

`todo/closure-arity-repro.clausal` (run with this clone's interpreter, or for the observed baseline:
`cd /workspace/clausal && source venv/bin/activate && cd <dir> && python -m clausal.testing closure-arity-repro.clausal`):

```clausal
double(A, B) <- (B == A * 2)

# A: closure passed DIRECTLY as an argument, then called -> PASSES
callit(GOAL, X, Y) <- (call_goal(GOAL, X, Y))
Test("A: direct closure arg") <- (callit(((A, B) <- double(A, B)), 3, R), R == 6)

# B: closure unified into a local variable, then called -> FAILS
Test("B: closure via local var") <- (G is ((A, B) <- double(A, B)), call_goal(G, 3, R), R == 6)

# C: closure nested in a compound term, extracted, then called -> FAILS
-private([bundle(G)])
unbundle(BUNDLE, X, Y) <- (BUNDLE is bundle(G), call_goal(G, X, Y))
Test("C: closure nested in compound") <- (unbundle(bundle(((A, B) <- double(A, B))), 3, R), R == 6)
```

Observed on main: **A passes; B and C fail** with the arity error above.

## Likely cause

The lambda is a special AST node whose parameter arity is known to the compiler when it appears **directly**
in argument position. After it round-trips through unification (`is`) or compound construction/extraction it
becomes an opaque term; `call_goal` no longer reads its arity and applies all its arguments, overflowing the
node's `__call__` (1–3 params). Probably in the higher-order `call_goal` path / how lambda AST nodes are
re-wrapped after unification.

## Expected

A closure bound to a variable, or stored in and extracted from a compound term, should remain callable with
its declared arity — standard higher-order Prolog: a goal/closure held in a variable is callable, and
`call(G, Extra…)` adds arguments. This is what lets a library pass a *record* of goals around.

## Impact

A generic higher-order library cannot bundle goals into a term or thread a goal through a variable — closures
must be passed as direct, literal arguments only. Concretely it forced the downstream consumer's
planner engine to take
its three domain hooks as three separate direct closure args instead of one `Hooks(...)` bundle, and a domain
must hide that behind a wrapper predicate.

## Workaround (in use)

Pass closures only as **direct literal arguments**; never unify a closure into a variable to pass it on, and
never nest one inside a compound term.
