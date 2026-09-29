# retract/1 treats every body Unify as part of the head (parked)

Found 2026-09-25 (feat/clause-2-2026-09-25).  `Clause.hoisted` now records
which leading body goals came from the head, and `retract/1` could use it.
It is NOT a small, self-contained change, so it is parked here.

`database_ops._retract_factory._first_match_index` checks EVERY `Unify` in the
body, and the success path binds through every one:

```python
            for goal in clause.body:
                if isinstance(goal, _Unify):
                    ...structural_unify(lv, rv, chk_trail)...
...
        for goal in removed.body:
            if isinstance(goal, _Unify):
                structural_unify(deref(goal.left), deref(goal.right), trail)
```

So for `h(X) <- (X is 3)` (hoisted = 0), `retract(h(5))` treats the
program's own `X is 3` as a head test and refuses the clause.

The exact version reads only `clause.body[:clause.hoisted]`.  But that
changes which RULES retract/1 removes: `retract(h(5))` would then remove that
rule.  ISO `retract(H)` is `retract((H :- true))`, so it should match only
clauses whose body is `true`.  Doing this right means deciding retract/1's
rule semantics -- whether it retracts rules, and whether it supports
`retract((H :- B))` -- which is the next step of the clause/2 plan
(assertz/retract of rules).  Do it there, with `clause_ops.head_matches` and
`clause_terms` as the matcher, so retract and clause/2 cannot disagree.
