# A quoted arithmetic cell in source is a NameError in a strict module

**Status: RULED Q16 2026-09-28 ("yes, they are builtins really") and DONE on
feat/arith-scryer-rulings-2026-09-28: the evaluable table's functors are in
scope in every module with no declaration
(`terms_to_ast.evaluable_functor_signature`, the fallback for a name nothing
binds; a module's own declaration answers first). `rem` is NOT in the closed
table, so it is not among them. `decimal/2` (an exact-number cell, not an
evaluable functor) still needs a declaration.

Was: OPEN. Found 2026-09-28. Pre-existing on main 7a615550.

The rulings of 2026-09-28 make the QUOTED spelling of an operator the way to
get Scryer's meaning in today's syntax: `'//'(-7, 2)` truncates, `'**'(2, 3)`
is 8.0, `'^'(2, 3)` is 8. But in a module with strict functors (the default)
writing one is an ordinary functor construction of an undeclared functor:

    g(X) <- 'is'(X, '//'(-7, 2))
    NameError: Predicate '///2' is not in scope as a term class.

The same holds for `'+'(1, 2)`, `div(-7, 2)`, `mod(7, 2)`, `rdiv(1, 3)`. It
works under `-implicit_functors`, and a cell built at runtime
(`unpack(T, ['//', -7, 2])`) needs no declaration.

Question: should the functors of the closed evaluable table
(`clausal.logic.exact_arith.EVALUABLE`: `+ - * / // div mod ** ^`, and the
exact-number `rdiv`/`decimal`) be in scope as term constructors in every
module, the way `'is'` is in scope as a builtin? Nothing else can mean them
(the table is closed), so there is no collision to guard against, and the
ruling's quoted spelling would then be writable without a directive.

docs/operators.md ("Writing a quoted arithmetic cell") documents the
`-implicit_functors` requirement meanwhile.
