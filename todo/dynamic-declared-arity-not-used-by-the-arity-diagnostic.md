# Bug: a `-dynamic` predicate with no clauses yet still blames `trail`

**Reported:** 2026-07-29, found while reviewing
[`arity-mismatch-reports-a-missing-trail-argument.md`](done/arity-mismatch-reports-a-missing-trail-argument.md)

---

## Symptom

```clausal
-dynamic(dfact/3)

Test("dyn wrong arity") <- dfact(A, B),
```

reports the original bug, verbatim:

```
  dyn.clausal:3 :: dyn wrong arity — dfact__3() missing 1 required positional argument: 'trail'
    goal 1 of 1 raised:
      dfact(A, B)
      TypeError: dfact__3() missing 1 required positional argument: 'trail'
```

Add one clause — `dfact(1, 2, 3),` — and the same file reports it properly:

```
      PredicateArityMismatchError: dfact takes 3 arguments, but this call passes 2
```

So the fault is not the arity being unknowable. `dfact__3` is the *name of the
generated dispatch function*: the declared arity is on the class, in
`_fields`, and in `db._dynamic` as `("dfact", 3)`. Only the clause list is
empty, and the clause list is what the diagnostic reads.

## Why the sibling fix declines here

`PredicateMeta._get_dispatch(arity)` notices `2 != len(cls._fields)` and asks
`_refuse_call_at(2)`, which asks `_clause_arity()`, which returns `None` for a
predicate with no clauses — *nothing is known well enough to refuse*. That is
deliberate: the fix does not trust `_arity`, because a module that imports a
0-arity vocabulary atom and then defines a same-named predicate leaves `_arity`
at 0 on a class whose clauses are at 2, and the corpus relies on that shape
(`tests/fixtures/impord_atom_then_pred.clausal`, `au/firb/computation.clausal`,
`us/sara_irc_tax/computation.clausal`). Clause heads cannot be stale; `_fields`
can. The declined case is the price, and `-dynamic` before the first `assertz`
is the visible instance of it.

## Requested fix

Read the declared arity, from whichever of the two sources survives scrutiny:

- `db.is_dynamic(functor, arity)` / `db._dynamic` — a `(functor, arity)` pair
  written by `mark_dynamic` straight from the directive, which is a *declaration*
  and so cannot be a stale inference from clause shapes. Reaching it from
  `_refuse_call_at` needs a database handle the class does not currently hold.
- `len(cls._fields)` when `cls._clauses` is empty — no new plumbing, but this is
  exactly the value the fix decided not to trust.

## Why using it is not obviously safe

- **A clause-free class is the shape that is legitimately about to change.** The
  0-arity vocabulary atom is imported clause-free and re-minted at /2 by the
  first clause of the importing module; a forward declaration is clause-free
  until its clauses load. Refusing on `_fields` alone would have to be certain
  the call happens after that settles, and `_get_dispatch` has no way to know.
- **Clauses do not have to live on the class.** `_DbDispatchAdapter` and the
  database fallback in `solve()` dispatch predicates whose clauses are in
  `db._clauses` and never reach `pred_cls._clauses`, so "no clauses" does not
  mean "nothing to call". A refusal keyed on the empty list would refuse working
  goals in that family.
- **`-dynamic` at two arities.** `mark_dynamic` records pairs, so `dfact/2` and
  `dfact/3` can both be declared while one class named `dfact` exists — the
  declaration set can legitimately hold the arity being refused. Any check must
  refuse only when *no* declared pair matches the call.
- **The false-positive guard has to hold.** The five call sites where a resolved
  class's arity disagrees with a call site's were surveyed in the sibling fix and
  four were correct code (partial-kwargs term construction, DCG nonterminals at
  their pre-translation arity). Routing through `_get_dispatch` excluded them
  structurally; a `_fields`-based refusal must not let them back in.

A cheap first step that avoids all of the above: leave the refusal alone and fix
the *message* for the declined case, so a call that runs out of arguments inside
a generated dispatch function never surfaces `missing 1 required positional
argument: 'trail'` whatever the reason. That is a narrower change than teaching
`_refuse_call_at` a second source of truth, and it covers the other declined
cases (heads that disagree, unreadable head shapes) at the same time.
