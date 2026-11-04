# sat/1 refuses library(clpb)'s card/2, ^/2 and the +([...])/*([...]) forms

Found 2026-11-04, reviewing the copy_term/3 work (which taught `sat/1`,
`taut/2` and `sat_count/2` the connectives `+ * # ~ =:= =\= =< >= < >` as
terms, matching Scryer's `sat_rewrite`).

Scryer's library(clpb) also takes (measured on the oracle build):

- `card(Is, Exprs)`: the number of true expressions in `Exprs` is in `Is`
  (a list of integers and `L-H` ranges);
- `Var^Expr`: existential quantification of `Var` in `Expr`;
- `+(Exprs)` and `*(Exprs)`: the disjunction and conjunction of a list.

Clausal raises the Python `TypeError` "CLP(B): unsupported expression
type" for each (`clausal/logic/clpb.py`, `_expr_to_bdd`):

```prolog
?- sat(card([1], [X, Y])).       % Scryer: sat(X=\=Y) ; Clausal: TypeError
?- sat(X^(X*Y)).                  % Scryer: Y = 1, sat(X=:=X) ; Clausal: TypeError
?- sat(+([X, Y, Z])).             % Scryer: sat(X=\=X*Y#...) ; Clausal: TypeError
```

The residual goals (`clausal/logic/residuals.py`) never produce these
forms, so copy_term/3 is not affected.
