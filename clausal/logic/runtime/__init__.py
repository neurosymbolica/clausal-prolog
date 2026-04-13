"""Runtime helpers for compiled Clausal predicates.

Code in this package runs **inside** compiled predicates at logic-
execution time.  It is referenced by name from generated code via
the compiled function's ``__globals__`` dict (``base_globals`` —
constructed in ``clausal.logic.compiler.predicate``).

This package **must not** import from ``clausal.logic.compiler``.
The compiler generates code that refers to names in
``base_globals``; it does not link its own module graph to the
runtime graph.  Enforced by ``tests/test_runtime_compiler_boundary.py``
(see also ``todo/run_tests_in_ci.md`` — the tests need to be wired
into CI for the enforcement to bite on merge).

Submodules:

- ``list_unify``      — bidirectional head list-pattern unification
                        (``_head_list_unify_input`` / ``_output``) plus
                        the C-accelerated fallback loader and
                        ``_head_multi_star_error``.
- ``body_star_unify`` — body-Is star-list runtime helpers
                        (``_body_star_unify`` / ``_build_star_list`` /
                        ``_build_multi_star_list`` / ``_in_iter`` /
                        ``_body_multi_star_unify``).
- ``tramp_call``      — simple-mode-to-trampoline-mode bridge
                        (``_tramp_call``).
"""
