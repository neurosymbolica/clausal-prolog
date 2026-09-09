# `eval_/2` with a variable operand divides as a FLOAT; the other two binders are exact

Observed 2026-09-09 while reviewing fix/normalise-integral-rationals-2026-09-09;
PRE-EXISTING on a3e3ec6b (same output on the untouched baseline tree). Not changed by
that branch on purpose: whether `eval_/2` should be exact-rational for variable
operands is a design decision for the operator, not a bug fix.

    -double_quotes(chars)
    g_eval(T, Q) <- eval_(T / 4, Q)
    g_eq(T, Q)   <- (Q == T / 4)
    g_is(T, Q)   <- 'is'(Q, T / 4)

Probe, T bound to 700000 at call time (branch tree; baseline gives the same for
`g_eval` and `Fraction(175000, 1)` for the other two):

    g_eval 175000.0 float
    g_eq   175000   int
    g_is   175000   int
    eval_(4 / 2, X) -> 2 int   (a LITERAL int/int Div is exact: `$exact_div`)

Three paths, two answers:

1. `eval_(T / 4, Q)` — `ArithEval`; `arith_to_ast_expr` only recognises a literal
   int/int Div (both operands ints at compile time). With a variable operand it emits
   Python's own `/` (`ast.Div` via `_ARITH_BINOP_MAP`), which is IEEE true division:
   `700000 / 4 == 175000.0`.
2. `Q == T / 4` — `fd_eq` -> `_resolve` -> `_eval_ground`, which does `Fraction(l, r)`
   for int/int at RUNTIME, so it is exact whatever was known at compile time.
3. `'is'(Q, T / 4)` — `_iso_eval` -> `_eval_ground`, same as 2.

So `docs/clpq.md`'s "integer division always produces an exact rational" is true of
`==`/`'is'` and of `eval_` over literals, and false of `eval_` over a variable. The
docs on that branch were kept from claiming exactness for the variable-operand
`eval_` case.

Options for the operator: (a) emit `$exact_div(l, r)` for EVERY Div in
`arith_to_ast_expr`, not only the literal one — one runtime type check per division,
and `eval_` becomes exact like the other two; (b) document `eval_/2` as "Python
evaluation semantics" (which `terms_to_goalop.py` already says in a comment) and leave
it; (c) route `eval_/2` through `_eval_ground`. Decide, then add a parity test that
runs the three-clause program above and asserts the three answers agree in type.
