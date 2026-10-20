# fix(A11-F023): ','/2 argument flattened on emission — arity silently changes

`tools/prolog_to_clausal.py:598-602` renders the `","` _INFIX_MAP entry bare
in argument position: `foo(a, (b, c)).` → `Foo(a, b , c),` — a foo/2 fact
becomes Foo/3, and the output is valid Python so nothing ever errors. Any
term embedding `,/2` is corrupted the same way.

**Fix**: parenthesize/tuple-ize `,/2` in argument position (or emit a
dedicated pair/and term); at minimum reject with PrologTranslationError.

**Test**: test_F023_tuple_arg_arity_preserved (xfail).
