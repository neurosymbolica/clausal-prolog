# The tabling variant key maps every variable to one sentinel, so f(_, _) and f(X, X) are one answer

Filed 2026-10-20, found while fixing
todo/done/tabled-answer-rows-share-their-unbound-variables-2026-10-16.md.
Pre-existing; independent of that fix.  Severity: WRONG ANSWERS, not only
a lost solution.  Through negation it proves a falsehood: with the program
below and `first(X) :- w(f(X, X)).`, the goal
`first(_), \+ (w(f(A, B)), A = a, B = b)` succeeds although `w(f(a, b))`
is provable (`\+ (w(f(A, B)), A = a, B = b)` alone fails, correctly).  The
first call tables the subgoal `w(f(X, X))`, whose only answer is
`f(V, V)`; the second call `w(f(A, B))` has the same key, so it is taken
for a variant and replays that table (verified 2026-10-20).

## What / Repro

```prolog
:- table(w/1).
w(f(_, _)).
w(f(X, X)).

?- findall(T, w(T), L).
% Clausal: L = [f(_A, _B)]        expected: L = [f(_A, _B), f(_C, _C)]
```

The second clause's answer is dropped as a duplicate of the first.  The
same conflation affects the CALL key: `w(f(A, B))` and `w(f(A, A))` are
one subgoal, so the second call replays the first's table.

## Cause

`_normalize_for_key` (tabling.py, and its C twin `do_normalize` in
`_tabling_core.c`) replaces every unbound variable with the one `_VAR`
sentinel.  Variant checking (ISO/XSB) renames variables apart in order of
first occurrence, so `f(_, _)` keys as `f(V1, V2)` and `f(X, X)` as
`f(V1, V1)`: different variants, two answers, two subgoals.

## Candidates

- Number variables by first occurrence in the key walk (a per-call
  `id(var) -> n` map; the C twin keeps a small table), in both twins
  (P52 lock-step).  The subgoal key of a call with no repeated variable
  is unchanged.
- `make_subgoal_key(answer, None)` in `add_answer` would then keep both
  answers; `_scan_complete_answers` and `_key_subsumes` need a look for
  the numbered sentinels.
