# Deep improper lists and cyclic terms overflow the engine's recursive walkers

**Status: FIXED 2026-10-24 (commits f8d2d427 and the deep-literal commit that follows it).**
The engine's `unify` unifies rational trees past a depth of 1000
(`unify_rational`, `variables/_variables.c`), `==`/2, `compare/3`, the sorts,
`copy_term/2`, `ground/1`, `term_variables/2`, `findall/3` and the writers
fall back to iterative, cycle-aware walks (`_helpers.term_compare`,
`clausal/logic/rational_walk.py`, the `...` of `terms._wq`), a deep ground
argument of an asserted clause compiles as a constant
(`compiler/deep_literals.py`), and every remaining RecursionError reaches a
program as `error(resource_error(stack), _)`.  Every `m2i`/`m3a`-`m3g` row
below answers as Scryer does.  Pinned in
`tests/iso/test_cyclic_terms_scryer.py` (each row under Clausal and Scryer),
`tests/iso/test_rational_tree_unify.py`, `tests/test_deep_literals.py` and
`tests/test_star_splice_readings.py::test_compare_on_two_distinct_cyclic_lists_answers_as_scryer`.

Filed 2026-10-22, split out of
`todo/done/star-splice-readings-and-cyclic-seglist-eq-2026-10-14.md` (its
M1-M3, "pre-existing recursion limits") when that todo's star-splice and
seam-`==` items were fixed. Each item below is a recursive walk, one frame
per cons cell or per lap of a cycle; fixing one does not fix the next.
Related: `todo/done/l3-cyclic-unify-fix-covers-only-eq-neq-is-2026-10-15.md`
(the engine's C `unify` has the same depth-capped recursion) and the "Still
open" ledgers in `todo/pl-translator-reads-an-improper-tail-as-an-element-2026-10-12.md`.

## Fixed on the way (2026-10-22)

- `compare/3`, `sort/2`, `msort/2`, `@</2` on an improper list of about 500
  cells: `_helpers.term_key` now loops the cons spine
  (`_cons_chain_key`). Pinned in
  `tests/test_star_splice_readings.py::test_compare_and_sort_on_a_500_cell_improper_list`.
- `assertz` of a PROPER list of 1500 (and 5000) cells, and the translator
  on a 5000-element `X = [...], Y = X`: both work on 1.1.0; pinned in
  `tests/test_star_splice_readings.py::test_assertz_of_a_1500_cell_list`.

## Still open

Repro (`-g <goal>` on a `.pl` file, native or translator front end):

```prolog
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
m2i :- mk(1500, foo, L), assertz(bigi(L)), bigi(X), X = [_,_|_].   % improper list
m3a :- X = [a|X], Y = [a|Y], X == Y.          % Scryer: yes
m3b :- X = [a|X], Y = [a|Y], X = Y.           % Scryer: yes
m3c :- X = [a|X], Y = [a|Y], compare(O, X, Y). % Scryer: O = (=)
m3d :- X = [a|X], copy_term(X, Y).            % Scryer: yes
m3e :- X = [a|X], findall(X, true, [_]).      % Scryer: yes
m3f :- X = [a|X], ground(X).                  % Scryer: yes
m3g :- X = [a|X], writeq(X).                  % Scryer prints the cyclic term
```

- **`assertz` of an IMPROPER list of about 1500 cells** (`m2i`) raises
  RecursionError. The cons cells `'.'(1, '.'(2, ... foo))` are 1500 nested
  tuples, and the clause compiler walks them recursively at several sites
  in turn: `globals_env._walk_body` (looping its cons spine moves the
  overflow to the next site), `_vars._collect_vars`, then the head-match
  and `terms_to_ast` emitters, which would also produce a 1500-deep nested
  AST that CPython's own compiler refuses. A fix would emit a cons chain
  as a runtime-built constant rather than nested AST. A proper list of the
  same length is fine (it is one Python list).
- **Two distinct cyclic lists** (`m3a`-`m3g`): ISO `==/2` and `=/2`
  (`structural_eq`, the C `unify`), `compare/3` (`term_key`, a clean
  RecursionError since 2026-10-22, never a hang), `copy_term/2`
  (`_copy_term: term nesting too deep`), `findall/3` and `ground/1`
  (`_is_ground: term nesting too deep`) and `writeq/1` all raise
  RecursionError where Scryer answers. Raising is acceptable, a wrong
  answer is not (`tests/test_partial_list_improper_tail.py::test_identity_never_answers_wrongly`);
  rational-tree support in those walkers is a feature, not a fix. The seam
  `==` (`SegList.__eq__`) already decides the bisimulation
  (`terms._rational_eq`, 2026-10-22), under the 2026-10-13 ruling's
  requirements: keys are the dereferenced objects of the terms, kept alive
  while keyed. The same construction would serve `structural_eq` and
  `compare/3`; `copy_term`, `findall` and `ground` need a cycle-aware C
  walk; `writeq` needs a spelling for cycles (Scryer prints `_` names
  through `local_vars`).
