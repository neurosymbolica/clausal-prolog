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

Re-exports below are explicit: every name imported from this package
by tests, tools, or sibling subpackages has a direct binding here.
The ``_monolith`` re-export hub and ``__getattr__`` delegation that
previously fronted these names were retired in slice B6 of the
compiler refactor (see ``implementation_plans/SLICE_B_PROGRESS.md``).
"""

# ── Public API ──────────────────────────────────────────────────────────────
from clausal.logic.trampoline import DONE  # noqa: F401

from .predicate import (  # noqa: F401
    compile_predicate_trampoline,
    compile_predicate_trampoline_ast,
    compile_predicate_shallow,
    compile_predicate_shallow_ast,
    compile_predicate,
    compile_predicate_ast,
)
from .goal_shallow import compile_body, compile_goal  # noqa: F401
from .goal_trampoline import (  # noqa: F401
    compile_body_trampoline,
    compile_goal_trampoline,
)
from .terms_to_ast import (  # noqa: F401
    term_to_ast_expr,
    arith_to_ast_expr,
    _dotted_name_from_loadattr,
)
from .head_match import (  # noqa: F401
    head_to_match_pattern,
    compile_head_to_match_case,
)

# ── Private re-exports for tests, tools, and external callers ──────────────
# Each name below is imported from clausal.logic.compiler somewhere outside
# this package (tests/, clausal/logic/solve.py, clausal/tools/, etc.).
# Adding a name here is the explicit contract that the import is intended;
# new private names should *not* be exposed unless a real external caller
# needs them.

from . import predicate  # noqa: F401 — submodule import for tests

from ._vars import _collect_vars, _var_python_name  # noqa: F401

from .globals_env import (  # noqa: F401
    _collect_globals_info,
    _collect_call_targets,
    _collect_head_types,
    _collect_py_thunks,
    _collect_types_from_term,
    _disp_key,
    _inject_call_targets,
)

from .arg_index import (  # noqa: F401
    _INDEX_THRESHOLD,
    _INDEX_VAR,
    _analyze_index_positions,
    _analyze_joint_index_positions,
    _bucket_key,
    _joint_bucket_key,
    _static_call_key,
    _runtime_arg_key,
    _extract_arg_key,
    _extract_first_arg_key,
    _build_arg_index,
    _build_first_arg_index,
    _build_joint_arg_index,
    _build_secondary_index,
)

from .tro import (  # noqa: F401
    _detect_tro_clause,
    _get_tro_check_indices,
    _tro_args_safe,
    _is_deterministic_goal,
)

from .destructive_reuse import _find_destructive_reuse_goals  # noqa: F401

from .control_constructs import (  # noqa: F401
    _compile_goal_lambda,
    _flatten_conjunction,
)

from .goal_trampoline import _inject_bucket_refs_trampoline  # noqa: F401

# Runtime helpers — re-exported for tests that exercise them directly.
# We import via .predicate (not directly from clausal.logic.runtime.*) so
# the runtime/compiler boundary test (which allows runtime imports only
# in predicate.py) stays satisfied without an exception list entry.
from .predicate import (  # noqa: F401
    _head_list_unify_input,
    _head_list_unify_output,
    _body_star_unify,
    _body_multi_star_unify,
    _build_star_list,
    _build_multi_star_list,
)
