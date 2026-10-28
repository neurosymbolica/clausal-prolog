# clpz `#=` with a product of two unknowns does not narrow when a factor binds later

**Status: FIXED 2026-10-28 (commit 763a2538).** A non-linear sub-expression (`*` of two unknowns, `//`, `div`, `mod`, `rem`, `^`, `min`, `max`) of any `#=`/`#\=`/`#<`/... post is lifted into a fresh variable with its own propagator (`clausal/logic/clpfd_nonlinear.py`), so `R*T #= 14, T = 7` gives R = 2 in either order. Pinned in tests/test_clpz_nonlinear_propagation.py (rows `R*T #= 14, T = 7` and `T = 7, R*T #= 14`) and tests/iso/test_clpz_propagation_matrix_scryer.py::test_row[k2004-edge].

Found 2026-10-01 while fixing the inequality gap (fix/clpz-linear-bounds-bind-2026-10-01).

```prolog
:- use_module(library(clpz)).
eq1(R, D) :- R*T #= 14, T = 7, fd_dom(R, D).
```

- Scryer: `R = 2, D = 2..2`.
- Clausal: R unbound, `inf..sup`.

`fd_eq` (C `py_fd_eq`, `_clpfd_propagate.c`) linearises only a LINEAR tree;
`R*T` falls through to an EqConstraint over the tree, which narrows only a
bare-variable side.  The inequality fix lifts such a product into a
`TimesConstraint` (`clpfd.py`, `_post_linear_ineq`); `#=` could do the same
(and `#\=`).  Not done there because it changes the `#=` post path, which
is hotter and outside that fix's scope.
