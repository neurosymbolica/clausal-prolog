# fix(A10-F011): zero-arity trailing-comma fact `flag,` is silently discarded

**Problem.** The fact branch in `EmbedTransformer.visit_Expr`
(term_rewriting.py:2436-2440) requires the 1-tuple element to be a `Call`; a
bare `Name` (`flag,`) falls through to a plain tuple expression statement that
evaluates and discards `(flag,)` — no `$define_predicate`, no clause, no
diagnostic. Asymmetric with `flag <- True`, which correctly defines `flag/0`.

**Repro/test.** test_10_rewriting_import.py::test_F011_zero_arity_fact (xfail);
guard ::test_F011_guard_zero_arity_rule.

**Fix.** In the single-element-tuple case, also accept
`isinstance(single_element, Name)` (non-logic-var) and emit the same
`Predicate(head=<functor call with no fields>, body=True)` definition the
`Call` path emits (reusing the 0-arity functor-class generation the `-module`
bare-atom path already has). If 0-arity facts are intentionally unsupported,
raise a SyntaxError pointing at `flag <- True` instead — silence is the bug.
