"""clausal.logic.compiler — predicate compiler package.

Organized by functional cohesion (see
``implementation_plans/COMPILER_MODULE_SPLIT.md``):

- ``_ast_helpers``      — AST-construction leaves + naming constants
- ``_vars``             — Var-collection and -naming helpers
- ``clausal.logic.runtime.list_unify`` — runtime bidirectional
                          list-pattern unification (moved out of
                          this package — see §7 of ``README.md``)
- ``terms_to_ast``      — term → Python AST lowering (+ star parsing)
- ``star_segments``     — body-Is star-list compilation
- ``globals_env``       — compile-time globals-dict construction
- ``head_match``        — head term → match-case patterns
- ``ite_reified``       — reified if-then-else (shallow + trampoline)
- ``tabled_naf``        — WFS tabled negation helpers
- ``control_constructs``— once, catch, setup_call_cleanup, freeze, when, …
- ``goal_shallow``      — ``compile_goal`` / ``compile_body`` (shallow)
- ``goal_trampoline``   — trampoline counterparts
- ``list_dispatch``     — single-position list-structure dispatch
- ``arg_index``         — first-arg + joint + secondary + groundness dispatch
- ``destructive_reuse`` — dead-source container-reuse rewrite
- ``tro``               — tail-recursion optimization analysis + rewrite
- ``predicate``         — top-level ``compile_predicate_*`` entrypoints
- ``_monolith``         — residual shared state + re-export hub (see below)

The ``_monolith`` submodule holds the hoisted Phase 0.5a runtime-helper
aliases (``_fd_eq_fn``, ``_DictTerm_t``, …); these are shared module-
level state that multiple submodules reference lazily.  It also
re-exports every moved-out symbol so external code can still import
any name from ``clausal.logic.compiler`` regardless of which submodule
owns it.

The ``__getattr__`` delegation below forwards unknown-attribute lookups
to ``_monolith``.  This preserves backward compatibility with the many
call sites (tests, builtins, tools) that import private helpers like
``_body_multi_star_unify`` or ``_extract_first_arg_key`` directly from
``clausal.logic.compiler``.
"""

from . import _monolith as _monolith

# Explicit re-exports — the documented public API surface.
from ._monolith import (  # noqa: F401
    compile_predicate_trampoline,
    compile_predicate_trampoline_ast,
    compile_predicate_shallow,
    compile_predicate_shallow_ast,
    compile_predicate,
    compile_predicate_ast,
    compile_goal,
    compile_goal_trampoline,
    compile_body,
    compile_body_trampoline,
    term_to_ast_expr,
    arith_to_ast_expr,
    head_to_match_pattern,
    compile_head_to_match_case,
)


def __getattr__(name):
    """Forward unknown-attribute lookups to ``_monolith``.

    Tests and internal modules import private helpers
    (``_body_multi_star_unify``, ``_build_star_list``,
    ``_extract_first_arg_key``, …) from ``clausal.logic.compiler``.
    Rather than enumerate each one, we delegate — ``_monolith``
    re-exports every symbol from the topic-specific submodules.
    """
    try:
        return getattr(_monolith, name)
    except AttributeError:
        raise AttributeError(
            f"module 'clausal.logic.compiler' has no attribute {name!r}"
        ) from None
