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
