# The `.pl` translator mis-emits some meta-call goal arguments the native front end runs

Filed: 2026-10-22, while auditing every goal position of the meta-predicates
the translator knows (`tests/test_pl_translator_data_terms_followups.py::
test_goal_positions_of_meta_predicates_stay_goals`). Each row below failed the
same way at 1.1.0 (`bb9bb20d`); none is caused by the data-position cell work.
Run with `CLAUSAL_PL_FRONTEND=translator`, compared with the native front end.

## What / Repro

1. `aggregate_all/3` over `member/2`:
   `t :- aggregate_all(count, (member(A, [1,2,3]), A > 1), N), writeq(N).`
   The translator emits `aggregate_all(count, (in_(A, [1, 2, 3]), A > 1), N)`,
   and the file does not load: "functor in_/3 was constructed with 2
   positional argument(s) but its class was registered with 3 field(s)".
   Native: `2`. (`findall/3` with the same goal works on both.)
   The same `in_` shape stops `tests/iso_diff/lists.pl`, where `member(X, L)`
   is written as DATA (`t(l13, X, member(X, [a, b, c]))`).
2. `phrase/2` of a control construct:
   `t :- phrase((g, [c]), [a,b,c]).` (with `g --> [a], [b].`) raises
   `existence_error(procedure, g/3)`, and
   `t :- phrase(([x] ; [y], []), [y]).` raises
   `type_error(callable, <class '...Or'>)`. Native: both succeed. The
   translator emits the DCG body in the seam's goal spelling
   (`('g', [c])`, `[x] or ([y], [])`), which phrase/2 does not read as a
   grammar body.

Also seen, on BOTH front ends (not translator gaps):

- `t :- catch(fail, _, true) ; w(x).` does not load ("empty body on Try"):
  `todo/catch-fail-goal-compiles-to-an-empty-try-2026-10-16.md`.
- `ignore/1` is `existence_error(procedure, ignore/1)`: special_forms.py
  lists it as "the library spelling a `.pl` file calls (no engine
  definition)".
