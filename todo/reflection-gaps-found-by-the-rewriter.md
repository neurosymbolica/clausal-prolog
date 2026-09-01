# Three reflection/dialect gaps the rewriter ran into

Found while building `clausal/rewrite/` (2026-08-15).  None of them is a
rewriter bug — the rewriter works around all three — but each is a sharp edge
that the next thing built on reflection will hit, and two of them are arguably
defects in the vocabulary rather than facts about it.

Each has a test pinning the CURRENT behavior, so changing any of them will fail
loudly rather than silently:
`tests/rewrite/test_reflection_contract.py`, `tests/rewrite/test_driver.py`.

## 1. An occurs check cannot see into a term a rule just built

```
Rebuild(Goal(NAME, ARGS, KW), Goal(NAME, ARGS, KW)),

SeesDirect(H, N)  <- reified_subterm(H, Variable(N))              # succeeds
SeesRebuilt(H, N) <- (Rebuild(H, H2), reified_subterm(H2, Variable(N)))  # fails
```

Same term, same variable inside it.  The rebuilt structure holds logic
variables, and `reified_subterm`'s walk does not follow them.

**Consequence for anyone writing rules:** "build the answer, then check the
answer is sound" is not an available shape.  Every legality condition has to be
established about the INPUT.  The head-fold learned this the expensive way — its
post-condition passed vacuously and it emitted a clause with an unbound head
variable.

**Fix, if it is one:** `_reified_subterm_2` in `clausal/modules/reflection.py`
walks with `deref` at the top only; a `_deref_walk` on entry (or a deref in the
recursion) would make it see bound structure.  Worth checking what else in
`clausal/modules/reflection.py` walks the same way — `goal_functor`,
`clause_body`, and the enumeration builtins have the same shape.

## 2. `[*XS]` is not a list test — a string unifies with it

```
Listish([*XS]) <- ++print("matched", XS)
```

`Listish("met")` succeeds, binding `XS` to the whole string.  A recursive
list-walking predicate written the obvious way therefore walks into every string
in its input; ours died on the 4 GiB cap.  The workaround is an explicit
`++isinstance(X, list)` gate before destructuring.

This is presumably deliberate — bytes-as-lists is a documented feature — but the
interaction with `[Head, *Tail]` recursion is a trap, and nothing warns.  Worth
either a note in `docs/bytes_as_lists.md` or a lint.

## 3. Reification drops a head's keyword-argument names

```
p(A=X, B=2) <- (X is 5)     reifies as     Goal("p", [X, 2], [])
```

The names are simply gone, so anything that re-renders a reified head emits it
positionally and changes what callers may write.  `Goal.kwargs` exists and is
documented as `[name, value]` pairs, so this looks like a hole in
`_ClauseReifier` rather than a design choice — head keyword arguments are common
in this corpus (`Factorial(N=0, RESULT=1),`).

The rewriter refuses to touch a clause whose head has keyword arguments, which
costs it those folds.

---

## STATUS 2026-09-02 — gaps 1 and 2 closed; gap 3 parked as a design question

1. **FIXED.** `_subterms` (`clausal/modules/reflection.py`) now derefs on
   entry, so `reified_subterm/2` follows bound logic variables — matching the
   deref discipline `replace_subterm`'s `_rewrites` already had (that walker
   was audited and was NOT blind). "Build the answer, then check it" is an
   available shape now; a pre-condition remains the better rule design and
   head_fold keeps its `Substitutable/1` gate. The pinning test flipped to
   the new contract:
   `test_occurs_check_sees_into_a_freshly_built_term`.
2. **DOCUMENTED.** The `[*XS]`-matches-a-string recursion trap and its
   `++isinstance(X, list)` gate are now in `docs/strings_as_lists.md`
   (Pattern Matching) with a pointer from `docs/bytes_as_lists.md`. No lint —
   the note names the in-tree example (head_fold's Foldable gate).
3. **PARKED — not a plain hole.** Dropping head keyword names is the recorded
   A11-F010 decision: keyword heads canonicalize to the runtime's
   first-definition field order so reified positional args match what the
   runtime enumerates (`kp(y=20, x=10)` → args `[10, 20]`), and the F010 pin
   (`test_F010_keyword_head_reify_matches_runtime_order`) explicitly allows
   either shape. Preserving kwargs pairs instead would improve render
   fidelity and let the rewrite driver lift its `_head_has_keywords` skip,
   but every cross-representation matcher that compares reified heads
   against runtime-shaped patterns would need the same canonicalization
   moved into matching. That is a fidelity-vs-canonicalization design call
   reversing F010, not a patch — decide it deliberately.
