# CLP(FD) constraints posted before promotion are not in the CLP(Q) relaxation (2026-11-04)

**Status: OPEN, needs an operator ruling.**

Found 2026-11-04 by the CLP(Q) coverage work, both solvers (`legacy`,
`holzbaur`). Severity: a silent failure where an answer exists.

## What / Repro

```prolog
:- use_module(library(clpq)).
:- use_module(library(clpz)).
d(D) :- X in 1..5, Y in 1..5, X #= Y + 3, {D = X - Y}, maximize(D).
```

`d(D)` fails; the answer is `D = 3`. When `X #= Y + 3` is posted, neither
variable has CLP(Q) state, so it goes to clpfd alone. `{D = X - Y}` then
promotes X and Y with their domains' hulls as clpfd has narrowed them
(DEVIATIONS.md D20, D29), 4..5 and 1..2, without the link between them.
The relaxation's optimum, `D = 4` (X = 5, Y = 1), is bound, and clpfd
refuses it.

The other order works since 2026-11-04 (DEVIATIONS.md D20, the dual post):
`X in 1..5, Y in 1..5, {D = X - Y}, X #= Y + 3` posts `X #= Y + 3` to both
stores and gives `D = 3` (tests/test_clpq_fd_dual_post.py, `max_after`).

Scryer, with clpz and clpq loaded together, fails both orders: its clpq
never sees clpz's bounds, so `D` is unbounded there.

## Options

A. **Replay at promotion.** When an FD variable first gets CLP(Q) state,
   post to CLP(Q) every linear integer FD constraint on it (EqConstraint,
   Lt/Le/Ne, ScalarProductConstraint over plain variables) and promote the
   other FD variables those constraints reach, transitively. Exact for
   linear networks; the cost is a walk of the reached FD component at each
   promotion, and it pulls whole FD models into the simplex (a large
   `all_different` puzzle that touches CLP(Q) once would put every linear
   constraint into the tableau). Non-linear and global constraints
   (TimesConstraint, all_different, reified ones) cannot be replayed; they
   still need B.
B. **Refuse.** maximize/minimize/bb_inf raise a new
   `representation_error(fd_constraint_not_in_relaxation)` when the
   optimum's binding is refused by clpfd and an FD variable in the
   objective's component carries an FD constraint that CLP(Q) does not
   hold. Never a silent failure (the 2026-11-03 ruling's aim), no change
   to answers that are given; a new error term.
C. **Keep and document** (current): the failure stands, recorded in
   docs/clpq.md and D29.

Recommendation: B now (matches the 2026-11-03 ruling that an optimum is
never a silent failure, small, both solvers), A later if programs mixing
the two need it, with B kept for the constraints A cannot replay.
