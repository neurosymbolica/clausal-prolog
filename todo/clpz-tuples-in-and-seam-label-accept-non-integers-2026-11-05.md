# tuples_in/2 and the seam's label/1 accept a non-integer where clpz raises type_error(integer, _)

Found 2026-11-05 while pinning cyclic CLP(Z) posts
(`tests/iso/test_clpz_cyclic_scryer.py`, commit 10737fe8). Neither is about
cycles: an acyclic compound or an atom is accepted too, and a cyclic term
just takes the same path. Neither hangs. Severity: a silent success where
Scryer's clpz raises an error, so a wrong program reads as correct.

## What / Repro

Each goal is run as `ev(Goal, R)`, where
`ev(G, R) :- catch((G, R = yes), error(E, C), R = E-C).`, with
`library(clpz)` loaded.

| goal | Clausal | Scryer (clpz) |
|---|---|---|
| `.pl` `X = X+1, tuples_in([[X]], [[1]])` | `yes` | `type_error(integer,... +1)-can_be/2` |
| `.pl` `X = 1+2, tuples_in([[X]], [[3]])` | `yes` | `type_error(integer,1+2)-can_be/2` |
| `.pl` `tuples_in([[a]], [[1]])` | `yes` | `type_error(integer,a)-can_be/2` |
| seam `X is 1 + 2, label([X])` | `yes` | -- |
| seam `X is X + 1, label([X])` | `yes` | -- |
| seam `X is 'a', label([X])` | `yes` | -- |

For comparison, these already answer as Scryer does:

| goal | Clausal | Scryer |
|---|---|---|
| `.pl` `X = 1+2, label([X])` | `type_error(integer,1+2)-labeling/2` | `type_error(integer,1+2)-must_be/2` |
| `.pl` `X = X+1, labeling([], [X])` | `type_error(integer,... +1)-labeling/2` | `type_error(integer,... +1)-must_be/2` |
| seam `X is 1 + 2, labeling([], [X])` | `type_error(integer,1+2)-labeling/2` | -- |

## Expected

- `tuples_in/2`: `type_error(integer, E)` for the first element `E` of a
  tuple that is neither a variable nor an integer, as Scryer's `can_be`.
  The context is `tuples_in/2`, the indicator Clausal already uses for this
  builtin's other errors.
- The seam's `label/1`: `type_error(integer, E)` for a list element that is
  neither a variable nor an integer, as `labeling/2` raises on both surfaces
  today. Context `label/1`, or `labeling/2` if label/1 is defined as
  `labeling([], Vs)` the way it is in `.pl`.

## Where the check belongs

- `tuples_in/2`: in `_tuples_in` in `clausal/logic/builtins/clpz_names.py`.
  The relation rows already go through `_integer`; the tuple elements
  (`tups`) go through `_items` only. Check each element with
  `clpz_surface._fd_variable(e, "tuples_in/2")` (Scryer's `fd_variable/1`,
  `can_be(integer, X)`) before posting.
- The seam's `label/1`: in `_label__1` in
  `clausal/logic/builtins/constraints.py`, or in `clpfd.label`, which keeps
  only the unbound variables (`_label_fd`) and skips everything else without
  a word. Run the same per-element check `clpz_surface.labeling` runs
  (`_finite_or_raise` after `_proper_list`) for each element that is not an
  integer. Watch the units side channel: `_label_targets` swaps a united
  variable for its shadow, so the check goes before that swap, on the user's
  elements.

A cyclic element needs nothing extra: `_fd_variable` looks at the top of the
term only, and `term_writeq` prints the culprit (`... +1`).

## Pin

Add rows to `tests/iso/test_clpz_cyclic_scryer.py` (cyclic) and to the
acyclic clpz error tests (`tests/iso/test_clpz_reported_rows_scryer.py`),
on `.pl`, `.clausal` and the seam.
