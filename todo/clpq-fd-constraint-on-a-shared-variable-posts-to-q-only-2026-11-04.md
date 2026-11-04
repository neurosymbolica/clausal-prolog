# A CLP(FD) constraint on a variable with CLP(Q) state goes to CLP(Q) only (2026-11-04)

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
