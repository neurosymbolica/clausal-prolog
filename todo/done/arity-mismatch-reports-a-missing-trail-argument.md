# Bug: calling a visible predicate at the wrong arity blames a missing `trail`

**Reported:** 2026-07-29, found while fixing
[`predicate-not-found-should-list-candidates.md`](predicate-not-found-should-list-candidates.md)

---

## Symptom

```clausal
-private([art_1_2, meta])

citation(art_1_2, "EUMR Article 1(2)", meta),
cite(art_1_2),

Test("citation record resolves") <- (
    cite(REF),
    citation(REF, METADATA)      # citation/2 — but citation/3 is what exists
),
```

reports:

```
  t3.clausal:8 :: citation record resolves — citation__3() missing 1 required positional argument: 'trail'
    goal 2 of 2 raised:
      citation(REF, METADATA)
      TypeError: citation__3() missing 1 required positional argument: 'trail'
```

Three things are wrong with that line, in increasing order of severity:

1. it leaks the mangled internal name `citation__3`;
2. it blames `trail`, an argument the author never wrote and cannot supply;
3. it never says the word *arity*, which is the entire content of the fault.

The author wrote a call with two arguments where the predicate takes three.
That sentence does not appear anywhere in the message.

## Why the sibling fix does not cover it

`Predicate name/N not found` now lists candidates, and its first branch is
"same name, another arity" — but that branch is only reachable when the name is
**absent** from the caller's namespace (a database-backed module, or a
`Compound`-headed predicate).  When the name IS bound — the common case: defined
in this file, or imported from another — the compiler injects the predicate
class directly and the wrong-arity call reaches the generated dispatch
function, which fails as a plain Python `TypeError` before any Clausal
diagnostic can see it.

So the *more* common in-module arity mismatch has the *worse* message.

## Requested fix

Detect it where the arity is already known and the check is free: in
`_inject_resolved_targets` / `_inject_call_targets`
(`clausal/logic/compiler/globals_env.py`), the resolved object's `_arity` is
compared against the call site's `target_arity` at compile time.  When they
disagree the call can never succeed, so injecting a shim whose `_get_dispatch`
raises `predicate_not_found(...)` would route it into the existing message —
no runtime cost, since resolution already happens once at compile time.

Two things to establish before doing that, neither of which was in scope for
the lookup fix:

- **kwargs.** `target_arity` counts `len(args) + len(kwargs)`; confirm a
  keyword call site still compares equal to the class's declared arity.
- **multi-arity names.** A name can be a `BuiltinPredicate` merged across
  arities, and `.pl`-translated code may reach the same name at several
  arities.  A false positive here would break working programs, so the shim
  must only replace the injection when the mismatch is unambiguous.

Until then the arity fault is legible only when the name is out of scope.

---

## FIXED — 2026-07-29

Both prerequisites were resolvable, and the answers moved the fix to a
different seam than the one requested here.

**kwargs: not a concern at all.** A keyword *goal* call does not exist —
`Pair(KEY="a", VALUE=V)` in a body raises `terms_to_goalop: goal shape not yet
supported (Call)` at load. `Call` nodes with kwargs only ever occur as *terms*,
and terms never resolve a dispatch function. So the `len(args) + len(kwargs)`
arithmetic in `_collect_call_targets` never reaches the check.

**multi-arity names: real, and it sank the requested approach.** Instrumenting
`_inject_resolved_targets` over the whole suite (10 466 tests) turned up exactly
five names where a resolved `PredicateMeta`'s arity disagrees with a call site's,
and four of them are *correct code*:

| name | call site | class | what it is |
|---|---|---|---|
| `vec` | /1 | /2 | `vec(x=1)` — partial-kwargs term construction |
| `count_leaves`, `digit`, `push_all` | /1 | /3 | DCG nonterminal handed to `phrase/3` |
| `…impord_atomvocab.impord_qd` | /2 | /0 | 0-arity vocabulary atom re-minted as a /2 predicate |

The first four say a `Call` in a clause body is not necessarily a *goal*, so
replacing the injected global with a shim — as this todo proposed — would have
broken term construction for the same name in the same clause. The fifth says
`_arity` can be **stale**: the atom-vs-predicate collision leaves `_arity` at 0
on a shared class whose clauses are already at 2, so `_arity` alone is not a
sound test even in goal position.

**What was done instead.** The seam is
`PredicateMeta._get_dispatch(arity=None)` — the one place a name becomes a
dispatch function, so covering it covers every position at once. The goal-call
emitters (`goal_shallow`, `goal_trampoline`) pass the call site's arity;
`call/N` passes `extra_n`; everything else omits it and is unaffected. Term
construction never goes through `_get_dispatch`, so all four false positives are
excluded structurally rather than by a guard. Staleness is handled by
`_clause_arity()`, which reads the clause heads: `_arity` is the cheap first
test, clause heads are the confirmation, and only the confirmed disagreement
raises.

Choosing that seam also fixed a case the requested approach could not reach:
`clausal/testing.py`'s goal-level diagnostic walk re-runs conjuncts through
`solve()`, which compiles with its own body compiler and never sees the
compile-time `locked_dispatch_keys`. Under the shim approach the report headline
would have named the arity while the goal block underneath still printed
`TypeError: citation__3() missing 1 required positional argument: 'trail'`.

**Message.** Not routed into `predicate_not_found` after all. `Predicate
citation/2 not found` is true but is the wrong sentence when `citation` is right
there in the file — it repeats the sin the sibling fix removed. New
`describe_arity_mismatch` states the fault outright:

```
citation takes 3 arguments, but this call passes 2
  citation/3 is defined at t.clausal:3.
  -> pass 3 arguments to citation, or define citation/2 as a predicate of its own.
```

`PredicateArityMismatchError` subclasses `TypeError` — which is what the failure
already was, so anything catching it keeps working.

**Cost.** Locked predicates (the default) reach dispatch through the cached
`$disp_` name and never call `_get_dispatch` at all: 244.8 → 241.2 ms on a
240 ms recursion benchmark, i.e. nothing. Unlocked (`-dynamic`) predicates pay
one integer comparison per goal invocation: `_get_dispatch()` 100.2 ns vs
`_get_dispatch(2)` 118.6 ns over 400 k calls. A `-dynamic`-only workload
measured 45–52 ms before and 48–51 ms after — inside this box's noise band.
`_maybe_cache_dispatch` no longer caches under a mismatched key, which also
fixes a latent bug: `$disp_citation_2` was being bound to `citation/3`'s
dispatch function.

Files: `clausal/logic/predicate.py` (`_get_dispatch(arity)`, `_clause_arity`,
`_refuse_call_at`), `clausal/predicate_diagnostics.py`,
`clausal/logic/compiler/{goal_shallow,goal_trampoline,globals_env}.py`,
`clausal/logic/solve.py`, `clausal/logic/builtins/{_registry,higher_order}.py`,
`clausal/modules/py/__init__.py`, `docs/predicates.md`,
`tests/test_predicate_arity_mismatch_diagnostic.py` (21 tests) +
`tests/fixtures/arimp_{lib,use}.clausal`.

**Left open**, as separate todos rather than widened scope:

- [`higher-order-meta-call-wrong-arity.md`](../higher-order-meta-call-wrong-arity.md)
  — `maplist`/`foldl`/`include`/… still give the old message. The funnel takes
  the arity now; the 17 sites each need their own value read off their own
  contract, and guessing would refuse working code.
- [`same-name-two-arities-silently-merge.md`](../same-name-two-arities-silently-merge.md)
  — found while probing: `foo(a, b),` and `foo(a),` in one file do not stay
  unrelated. The shorter head is padded to `foo(a, _)` and absorbed into `foo/2`;
  `foo/1` never exists. This makes the *new* diagnostic accurate and confusing
  at once — it names `foo/2` as the only definition while the author is looking
  at a `foo(a),` clause.
