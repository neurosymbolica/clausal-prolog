# The `-g` answer printer shows CLP(Q) residuals only

**Status: FIXED 2026-10-26 (commit 169fc5e4).** `dif/2` and CLP(FD) residuals were printed since the `?-` top-level work (2026-10-24); a pending `freeze/2` or `when/2` now prints as its goal too (`freeze(X,true)`), plain form, operator ruling 2026-10-26. Pinned in tests/iso/test_freeze_when_residuals_scryer.py and tests/test_toplevel.py::test_residual_dif_and_clpz / ::test_residual_freeze_and_when. copy_term/3 is still open (todo/copy-term-3-attribute-goals-2026-09-08.md).

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
