# A term_expansion/4 body cannot call a helper predicate of its own module

Found 2026-09-25 writing the retired-q() warning's helper-reachability test.

```clausal
term_expansion(I, O, S, S) <- step(I, O)
step(I, O) <- rewrite(I, O)
rewrite(fact(X), [fact(X), logged_fact(X)]),
fact(1),
```

fails to load: `NotImplementedError: Predicate step/2 has no compiled
dispatch function. The compiler must be run first.` The expansion rules are
compiled into the synthetic `_term_expansion_` module
(`clausal/logic/term_expansion.py` `_compile_expansion_rules`), and only the
`term_expansion/4` clauses are asserted and compiled there; the file's other
predicates are not compiled yet when expansion runs (expansion happens
before the module's own compile, by design, since it rewrites that input).

ISO/Scryer `term_expansion/2` routinely delegates to helpers defined in the
same file ABOVE the point of use (they are already consulted). Options:
compile the helpers reachable from the term_expansion bodies into the
synthetic module too (they are not themselves expanded, like the TE clauses),
or document the limit and point at a helper MODULE imported with
`-import_from`.

The retired-q() warning already follows this reachability
(`EmbedTransformer._settle_retired_quasi_quote`), so it is ready for either.

## Closed 2026-09-30

Fixed on fix/todo-batch-3-2026-09-30 with the first option: the helpers
reachable from the term_expansion/4 bodies (transitively, by name over every
functor a body writes -- the same reachability the retired-q() warning uses)
are defined and compiled into the synthetic `_term_expansion_` module as
written; they are not themselves expanded, and they still reach the module as
ordinary items. The pre-mint of data constructors skips a helper's
name/arity (that pre-mint was what turned `step(I, O)` into a call of a
Python constructor: `type_error(callable, <function step>)` on main, the
`NotImplementedError` above before that). Pinned by
tests/test_term_expansion.py::TestHelperInTheSameModule.
