# A tabled answer row with unbound variables is shared, not copied, on replay

Filed 2026-10-16, from the D68 review (F2), by the engine lane.
Pre-existing (main e7a59c8f behaves the same); independent of D68.

## What / Repro

```prolog
:- table(v/1).
v(_).
v(1).

?- v(X), var(X), X = b, findall(Y, v(Y), L).
% Clausal: L = [b, 1]      expected: L = [_, 1]
% (main e7a59c8f: L = [b] -- the streaming table also lost 1, fixed by D68)

?- findall(X-Y, (v(X), v(Y)), L).
% Clausal: L = [_A-_A, _B-1, 1-1, 1-1]
% expected  [_A-_B, _C-1, 1-_D, 1-1]: the first pair's two answers are one
% variable, and binding it to 1 through Y made the third pair 1-1
```

Scryer aliases too (/opt/scryer-prolog-clpq, 2026-10-16): the first query
gives `[b,1]`, the second `[b-b,b-1,1-b,1-1]` (the earlier binding of the
row's variable even outlives that query).

## Cause

`freeze_args` is a deref-walk: a frozen answer keeps the derivation's own
unbound `Var` objects.  `_unify_answer` (tabling.py, `_unify_answer_py` and
its C twin) unifies the caller's arguments with the stored row itself, so
every replay of a row shares those variables: a binding made through one
answer is seen by the next replay of the same row (until backtracking
undoes it).  Since D68 every answer of a leader is delivered from the table
too, not only cache hits.

## Candidates

- Rename the row's variables apart on every replay (copy_term of the row,
  attribute-free), as a stored clause is renamed apart.  Cost: a copy per
  replayed non-ground row; ground rows (the common case) can skip it with a
  groundness flag computed at `add_answer`.
- Store rows with variable sentinels (the subgoal key already maps unbound
  variables to `_VAR`) and build fresh variables on replay.

Related: todo/audit-2026-07-05/investigate-A12-tabling-answer-constraints.md
(the same rows lose their attributes).
