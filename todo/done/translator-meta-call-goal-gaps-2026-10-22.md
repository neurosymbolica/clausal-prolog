# The `.pl` translator mis-emits some meta-call goal arguments the native front end runs

**Status: FIXED 2026-10-22 (commit 028b0ffa).** member/2 keeps its ISO name (no more `in_` node), data terms take no builtin rename, phrase/2,3's first argument is the ISO grammar body term, variable goals are `call(G)`, and the catch-fail row is fixed in the compiler; ignore/1 stays undefined (see below). Pinned in tests/test_pl_translator_data_terms_followups.py::test_member_and_phrase_bodies_in_meta_and_data_positions (both front ends; the first program's lines are Scryer's).

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
  `todo/done/catch-fail-goal-compiles-to-an-empty-try-2026-10-16.md`.
- `ignore/1` is `existence_error(procedure, ignore/1)`: special_forms.py
  lists it as "the library spelling a `.pl` file calls (no engine
  definition)".

## Resolution (2026-10-22)

1. `aggregate_all/3` over `member/2`, and `member/2` as data: fixed
   (`_REVERSE_OVERRIDES` no longer renames member; `_predicate_name(...,
   rename=False)` for data). The same data rename hit every reverse-map
   name (`memberchk`, `time`, `zip`, `fd_domain`, ...) and clpz `in/2`
   (keyword rename to `in_`); all fixed. `tests/iso_diff/lists.pl`,
   `allsol.pl`, `except.pl`, `tests/iso_l3/rulebase_s1.pl` and
   `s5/s5_clpz_exit.pl` now load on the translator.
2. `phrase/2` of a control construct: fixed (`_emit_dcg_body_term`; the
   seam builds `'{}'(T)` as the curly cell). Grammar-rule bodies had
   siblings, fixed too: an atom nonterminal was read as terminals, a `;`
   branch went through the goal emitter. `->` in a grammar body stays
   refused by the translator (cut-free; F024).
3. catch-fail: fixed in the compiler
   (todo/done/catch-fail-goal-compiles-to-an-empty-try-2026-10-16.md).
4. ignore/1: NOT added. ISO has no ignore/1; it is `(G -> true ; true)`,
   committed choice, and Clausal is cut-free on its own surfaces (an engine
   builtin would be reachable from `.clausal`); ruling D13 forbids new
   transition constructs (once/1, `\+`, forall/2 are counted and may not
   grow). docs/iso_prolog_compatibility_report.md lists it under "Missing
   builtins" (common non-ISO extras). A `.pl` file may define it itself:
   the native front end runs `->` in `.pl` modules.

Remaining, not this todo's (pre-existing, seen while testing):

- The translator declares a data atom equal to a module it also qualifies
  goals with (`X = lists, lists:member(a, L)`) as `-private([lists])`,
  which shadows the module: "terms_to_goalop: goal shape not yet supported
  (Call): LoadAttr(object='lists', ...)" at load.
- The translator's writeq does not know library(clpz)'s operators:
  `writeq(X #= 1)` prints `#=(_,1)` (native: `_ #= 1`).
- The translator stores body goals written as data in its lowered form
  (`fail` as `false`, `X is E` as `eval_(E, X)`): pinned class (a)/(c)
  rows of `tests/fixtures/pl_parity_known.json`.
