# Clausal cannot express partial application

**Status: FIXED 2026-09-25 (commit 0868c0e4).** A compound in callable position is a closure, as in Scryer: `call(add_z(10), 1, Y)` and `maplist(add_z(10), [1, 2], YS)` append the remaining arguments (YS = [11, 12]) instead of failing silently. Pinned in tests/test_call_runs_body_terms.py::test_a_runtime_cell_goal_folds_like_call_n.

**Filed:** 2026-08-15, re-scoped from the silent-failure framing at the
operator's direction: the deficiency is the MISSING CAPABILITY, not (only) how
its absence fails. **Status: OPEN — language design.**

## The gap

The lambda is Clausal's only closure former. A predicate reference with some
arguments already bound — ISO Prolog's bread-and-butter `maplist(add_z(Z), XS,
YS)`, where `call/N` appends the mapped arguments — has no Clausal spelling:

```clausal
add_z(Z, X, Y) <- (Y == X + Z)

t1(Y)  <- call_goal(add_z, 10, 1, Y)        # bare atom + appended args: works
t2(Y)  <- call_goal(add_z(10), 1, Y)        # no solution -- not a closure
t3(YS) <- maplist(add_z(10), [1, 2], YS)    # no solution -- not a closure
```

(Verified 2026-08-15 on main @ 17813a96.) The only way to close over `Z` is the
full forwarding lambda:

```clausal
maplist(((X, Y) <- add_z(Z, X, Y)), XS, YS)     # today's only spelling
maplist(add_z(Z), XS, YS)                        # the missing spelling
```

## Why it matters

- **It is the standard idiom of the neighboring language.** Every
  Prolog-trained author (human or model — see `docs/for_prolog_programmers.md`'s
  audience) will write `maplist(foo(A), ...)` on the first day. Today that
  fails silently (see "failure mode" below).
- **It taxes exactly the code real rulebases are full of.** Every closure over
  a bound prefix costs a lambda that restates the callee's argument list. In a
  production domain corpus a conservative single-line regex finds **8 lambdas
  whose params are exactly the callee's argument suffix** (pure partial
  applications, e.g. `((P, R) <- g(P, R))` closing over nothing vs.
  `((X, Y) <- f(A, X, Y))` closing over `A`) — plus the many multi-line and
  interleaved-constant shapes the regex cannot see.
- **It gates the eta-reduction rewrite rule.** `clausal-rewrite`'s
  `unnecessary_lambda` class (2026-08-15) reduces full forwarding lambdas to
  bare references, and correctly REFUSES prefix-closing lambdas — they are
  load-bearing precisely because this feature does not exist. If partial
  application lands, the rule's legality extends mechanically: params = exact
  arg suffix, closed-over prefix contains no params → replace with the
  partially-applied term.

## Design considerations (not prescriptions)

1. **Disambiguation is positional, same as today.** A compound in CALLABLE
   position (`maplist`'s first arg, `call_goal`'s goal, and other
   higher-order slots) is unambiguous intent, exactly as bare atoms already
   are; a compound in data position stays data. No new syntax needed —
   `add_z(10)` already parses.
2. **Append semantics** should mirror `call_goal`'s existing bare-atom rule:
   `call_goal(f(A1..Ak), X1..Xn)` ≡ `f(A1..Ak, X1..Xn)`.
3. **The reflection vocabulary is ready**: `Goal(name, args, kwargs)` in
   callable position IS the partial-application term; no vocabulary change.
4. **Interaction with dispatch/arity**: the callee's arity check moves to
   call time (k + n must match a defined arity) — the diagnostics for
   `maplist/4 not found` style mistakes must not get worse.

## The failure mode, until (or unless) the feature lands

Today the non-callable compound fails SILENTLY — "the predicate has no
solution for ANY arguments" — while a stray comparison in the same position
raises `type_error("callable", ...)` (`clausal/logic/builtins/_registry.py`).
That is the confident-silence class: under a `not` or on an `indeterminate`
route it becomes a wrong verdict.
If the design answer to partial application is NO, the minimum fix is the loud
rejection with a hint:

> `add_z(10)` is not callable — Clausal has no partial application; write the
> closure as a lambda: `((X, Y) <- add_z(10, X, Y))`.

If the answer is YES, the silent case disappears into the feature.
