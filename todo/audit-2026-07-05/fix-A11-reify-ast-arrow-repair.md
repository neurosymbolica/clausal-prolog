# fix(A11-F012): reify_ast's " < -" repair corrupts X < -1 comparisons

`reflection.py:509` blanket-replaces `" < -"` with `" <- "` in
`ast.unparse` output, because unparse renders the clause arrow that way — but
a genuine `X < -1` comparison renders identically. Result (executed):
`reify_ast(ast.parse('Foo(X) <- (X < -1)'))` → body `Lambda(params=[X],
body=1)`; a bare `Baz < -1` becomes a CLAUSE. reify_source is correct (Lt).

**Fix**: repair only the top-level arrow (the Compare at the statement root),
or accept an optional `source=` text and use it verbatim when provided.

**Test**: test_F012_reify_ast_preserves_lt_negative (xfail).
