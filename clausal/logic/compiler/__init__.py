"""clausal.logic.compiler — predicate compiler package.

This package is currently a thin shim over ``_monolith.py`` (the former
``compiler.py``).  Subsequent phases of the module-split plan (see
``implementation_plans/COMPILER_MODULE_SPLIT.md``) will migrate cohesive
groups of functions out of ``_monolith.py`` into focused submodules.
The public import surface stays stable throughout.

During the split, ``__getattr__`` delegates unknown attribute lookups
to ``_monolith``, so both public entrypoints and private helpers remain
importable from ``clausal.logic.compiler`` without needing to enumerate
every symbol here.  After Phase 18 (retirement of ``_monolith.py``) this
shim is replaced by an explicit re-export list.
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

    Tests and internal modules import a few private helpers
    (``_body_multi_star_unify``, ``_build_star_list``,
    ``_extract_first_arg_key``, …) from ``clausal.logic.compiler``.
    Rather than enumerate each one during the split, we delegate.
    Once all symbols have migrated to focused submodules, this
    delegation is replaced by explicit re-exports.
    """
    try:
        return getattr(_monolith, name)
    except AttributeError:
        raise AttributeError(
            f"module 'clausal.logic.compiler' has no attribute {name!r}"
        ) from None
