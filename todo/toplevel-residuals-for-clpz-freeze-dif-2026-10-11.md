# The `-g` answer printer shows CLP(Q) residuals only

Since 2026-10-11 `clausal -g` prints the CLP(Q) constraints left on an
answer's variables (`{X + Y = 3}`, `{X > 1}`), through
`clausal.logic.clpq.residual_q`.  Every other kind of pending constraint is
still dropped:

    X #> 3                    ->  true.     (Scryer: clpz:(X in 4..sup).)
    freeze(X, true)           ->  true.     (Scryer: freeze:freeze(X,true).)
    dif(X, a)                 ->  true.     (Scryer: dif:dif(X,a).)

There is no `copy_term/3` (attribute goals) to ask each solver for its
residual goals.  Building that is the general fix; the CLI printer then
calls it instead of `residual_q`.
