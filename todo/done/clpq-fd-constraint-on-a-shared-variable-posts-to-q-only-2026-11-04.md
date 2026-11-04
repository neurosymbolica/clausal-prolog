# A CLP(FD) constraint on a variable with CLP(Q) state goes to CLP(Q) only (2026-11-04)

**Status: FIXED 2026-11-04 (b1c1b2ab).** A linear integer `#` comparison over
variables that all have FD state, one with CLP(Q) state, posts to both
stores (`clpfd._post_shared_fd_q`); X = 5, Y = 2 on both solvers. Pinned in
tests/test_clpq_fd_dual_post.py::test_a_shared_variable_takes_the_constraint_in_both_stores
(and test_the_oracle_agrees). Left open: FD constraints posted before
promotion, todo/clpq-fd-constraints-posted-before-promotion-are-not-in-the-relaxation-2026-11-04.md.

Found 2026-11-04 by the CLP(Q) coverage work, both solvers. Severity: a
wrong answer (a variable left unbound with an incomplete residual where it
has one value).

## What / Repro

```prolog
:- use_module(library(clpq)).
:- use_module(library(clpz)).
?- X #>= 0, X #=< 5, {X + Y = 7}, X #> 4.
```

Scryer (clpz and clpq loaded together): `X = 5, Y = 2`. Clausal,
`holzbaur`: X unbound, residual `{Y = 7 - X}, {X > 4}, {X =< 5}`;
`legacy`: X unbound, `{Y >= 2}, {Y < 3}`.

Cause: `{X + Y = 7}` gives X CLP(Q) state beside its FD state
(docs/clpq.md, "FD<->Q coexistence"). clpfd's dispatch sent every
comparison that touched a variable with CLP(Q) state to CLP(Q) alone, so
`X #> 4` never narrowed X's FD domain to 5..5 and clpfd never bound X.
