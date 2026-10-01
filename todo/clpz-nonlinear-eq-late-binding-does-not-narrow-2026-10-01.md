# clpz `#=` with a product of two unknowns does not narrow when a factor binds later

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
