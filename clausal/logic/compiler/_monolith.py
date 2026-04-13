"""clausal.logic.compiler — predicate compiler (Steps 4 + 5).

Step 4 (head patterns): head_to_match_pattern, compile_head_to_match_case
Step 5 (body goals):    term_to_ast_expr, arith_to_ast_expr, compile_goal,
                        compile_body, _make_body_compiler

List patterns:  Bidirectional ``[HEAD, *TAIL]`` via _head_list_unify_input/output.
                Repeated head vars via dup_guards.  See block comment above
                ``_head_list_unify_input`` for the full design.

Two compilation strategies are provided:

**Shallow / short-stack** (``compile_predicate_shallow``)
    Each clause becomes a ``match`` arm.  The body ends with ``yield None``
    for each solution.  Sub-predicate calls use Python ``for`` loops so the
    Python call stack grows with recursion depth.  Safe only for predicates
    with bounded call depth (e.g., fact tables, leaf predicates).  Declared
    via the ``-shallow([pred/arity, ...])`` directive in ``.clausal`` files.

    Compiled function signature::

        def {functor}__{arity}(arg0, …, argN, trail, k):
            …
            yield None   # ← one solution

**Trampoline / stack-safe** (``compile_predicate_trampoline``)
    Every generated function participates in the
    ``clausal.logic.trampoline`` tuple protocol.  Sub-predicate calls use
    ``StepGenerator(dispatch, this_generator, …)`` so the Python call stack
    does *not* grow.  Solutions are surfaced via ``yield (parent, None)``;
    exhaustion via ``yield (parent, DONE)``.  The trampoline drives all
    generators.

    Compiled function signature::

        def {functor}__{arity}(this_generator, parent, arg0, …, argN, trail):
            …
            yield (parent, _DONE)   # ← search exhausted
"""

from __future__ import annotations

import ast
import dataclasses
import threading
from fractions import Fraction
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref, unify
from clausal.logic.trampoline import Step, DONE, StepGenerator
from clausal.terms import (
    Compound,
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    Negate,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    Call, LoadName, LoadAttr,
    SegList, ConcreteSeg, VarSeg, _seglist_unify_gen, _multi_star_splits,
    SegString,
)
from clausal.pythonic_ast.nodes import IfExpr, Lambda
from clausal.pythonic_ast.nodes import StarUnpack, TupleLiteral, DictLiteral, SetLiteral
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.codegen import functiondef_to_function
from clausal.logic.solve import _deref_walk as _deref_walk_fn

# ── Phase-0.5a runtime-helper aliases moved to predicate.py ─────────────────
# These were originally hoisted here during the Phase 0.5a pass (inner
# imports scattered through compile entrypoints, moved to module scope).
# Slice B1a of the post-split migration (see
# implementation_plans/SLICE_B_PROGRESS.md) moved them into
# ``predicate.py`` directly, where ``base_globals`` construction uses them.
# ``_monolith`` no longer bulk-supplies aliases to ``predicate.py`` via
# ``for _n in dir(_m): globals().setdefault(_n, getattr(_m, _n))``.
#
# Two builtins-related names still live here because ``_monolith``'s own
# re-export block (the legacy back-compat ``__getattr__`` delegation)
# continues to need them; they get retired together in slice B6 when
# ``_monolith.py`` is deleted.
from clausal.logic.builtins import (  # noqa: E402
    get_builtin_predicate,
    BuiltinPredicate,
    _BUILTIN_CLASSES,
)

# ── Compiled-code naming constants (moved to ._ast_helpers) ──────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _MARK_PREFIX, _TRAIL_PARAM_NAME, _K_PARAM_NAME, _DISP_PREFIX,
    _TRAMP_PARENT_NAME, _THIS_GEN_NAME,
)


# Phase 7: thread-local context for locked-predicate dispatch caching.
# Set during compile_predicate_trampoline / compile_predicate so that
# _dispatch_call_trampoline / _dispatch_call_iter can emit a direct name
# reference (_disp_Foo_2) instead of Foo._get_dispatch() for locked predicates.
_compile_context_local: threading.local = threading.local()


# ── ast helpers (moved to ._ast_helpers, re-imported here) ───────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _name, _attr, _call, _fresh, _compile_counter,
)

# ── Bidirectional list pattern unification (moved to clausal.logic.runtime) ──
from clausal.logic.runtime.list_unify import (  # noqa: E402,F401
    _head_list_unify_input_py,
    _head_list_unify_output_py,
    _head_list_unify_input,
    _head_list_unify_output,
    _head_multi_star_error,
)
from clausal.logic.runtime.body_star_unify import (  # noqa: E402,F401
    _body_star_unify,
    _build_star_list,
    _build_multi_star_list,
    _in_iter,
    _body_multi_star_unify,
)
from clausal.logic.runtime.tramp_call import _tramp_call  # noqa: E402,F401

# ── Variable naming (moved to ._vars) ─────────────────────────────────────────
from ._vars import _var_python_name, _collect_vars  # noqa: E402,F401

# ── Globals-environment construction (moved to .globals_env) ─────────────────
from .globals_env import (  # noqa: E402,F401
    _set_of_dedup,
    _DbDispatchAdapter,
    _GlobalsDb,
    _collect_head_types,
    _collect_py_thunks,
    _collect_types_from_term,
    _collect_call_targets,
    _collect_globals_info,
    _disp_key,
    _merge_builtin,
    _inject_call_targets,
    _inject_resolved_targets,
    _preallocate_body_vars,
)


# ── Term → AST expression (moved to .terms_to_ast) ───────────────────────────
from .terms_to_ast import (  # noqa: E402,F401
    term_to_ast_expr, arith_to_ast_expr,
    _is_star_list, _parse_star_segments, _count_stars,
    _dotted_name_from_loadattr,
)

# ── Misc AST-building helpers (moved to ._ast_helpers) ────────────────────────
from ._ast_helpers import (  # noqa: E402,F401
    _yield_none_stmt, _assign, _assign_mark, _undo_stmt, _if, _in_iter_expr,
)





# ── Reified ITE helpers (moved to .ite_reified) ──────────────────────────────
from .ite_reified import (  # noqa: E402,F401
    _is_reifiable,
    _compile_reified_ite, _compile_reified_ite_eq, _compile_reified_ite_fd,
    _compile_general_ite,
    _compile_reified_ite_trampoline, _compile_reified_ite_eq_trampoline,
    _compile_reified_ite_fd_trampoline,
    _compile_general_ite_trampoline,
)

from .star_segments import (  # noqa: E402,F401
    _compile_star_is, _compile_single_star_is, _compile_multi_star_is,
)

from .tabled_naf import (  # noqa: E402,F401
    _is_tabled_naf, _compile_tabled_naf_simple,
)

from .control_constructs import (  # noqa: E402,F401
    _compile_arith_cmp, _deref_cmp,
    _compile_once, _compile_call_nth, _compile_count_all,
    _compile_setup_call_cleanup, _compile_freeze, _compile_when,
    _compile_find_all_core,
    _catcher_to_structural, _compile_throw,
    _compile_catch, _compile_catch_trampoline,
    _compile_goal_lambda, _flatten_conjunction, _hoist_lambda_args,
)



# ── Destructive-reuse optimization (moved to .destructive_reuse) ─────────────
from .destructive_reuse import (  # noqa: E402,F401
    _DR_CANDIDATES,
    _head_aliased_var_ids, _collect_unify_pairs_from_and,
    _flatten_and_goals, _flatten_and_single,
    _find_destructive_reuse_goals, _apply_destructive_reuse,
)


# ── Goal & body compilation (moved to .goal_shallow / .goal_trampoline) ─────
# Placed after destructive-reuse because goal_trampoline imports
# _flatten_and_goals / _find_destructive_reuse_goals / _apply_destructive_reuse
# from _monolith at load time.
from .goal_shallow import (  # noqa: E402,F401
    compile_goal, compile_body, _make_body_compiler,
    _compile_predicate_call, _dispatch_call_iter,
)
from .goal_trampoline import (  # noqa: E402,F401
    compile_goal_trampoline, compile_body_trampoline,
    _make_body_compiler_trampoline,
    _compile_predicate_call_trampoline,
    _dispatch_call_trampoline, _inject_bucket_refs_trampoline,
    _step_expr, _yield_step_stmt, _assign_yield_step,
)


# ── List dispatch (moved to .list_dispatch) ──────────────────────────────────
from .list_dispatch import (  # noqa: E402,F401
    _get_head_arg, _lift_clause_at_pos,
    _classify_list_key, _find_list_dispatch_pos, _build_list_dispatch_guard,
)

# ── TRO (moved to .tro) ─────────────────────────────────────────────────────
from .tro import (  # noqa: E402,F401
    _is_deterministic_goal, _detect_tro_clause, _get_tro_check_indices,
    _tro_args_safe,
    _head_has_unifying_list_pattern, _list_has_nonvar_constant,
    _contains_star_unpack,
    _compile_tro_tail, _compile_tro_body,
)

# ── Argument indexing / dispatch builders (moved to .arg_index) ──────────────
from .arg_index import (  # noqa: E402,F401
    _INDEX_VAR, _INDEXABLE_TYPES, _INDEX_THRESHOLD, _JOINT_COVERAGE_THRESHOLD,
    _arg_to_index_key, _runtime_arg_key, _static_call_key,
    _bucket_key, _joint_bucket_key,
    _extract_arg_key, _extract_first_arg_key,
    _build_arg_index, _build_first_arg_index,
    _analyze_index_positions,
    _build_joint_arg_index, _analyze_joint_index_positions,
    _make_joint_dispatch_simple, _make_joint_dispatch_trampoline,
    _build_secondary_index,
    _make_secondary_dispatch_simple, _make_secondary_dispatch_trampoline,
    _make_indexed_dispatch_simple, _make_indexed_dispatch_trampoline,
    _make_groundness_dispatch_simple, _make_groundness_dispatch_trampoline,
)


# ── head_to_match_pattern et al (moved to .head_match) ───────────────────────
from .head_match import (  # noqa: E402,F401
    _wrap_yields_with_output_guards,
    head_to_match_pattern,
    _compile_multi_star_guard,
    compile_head_to_match_case,
    _head_arg_patterns,
)

# ── Predicate-compilation entrypoints (moved to .predicate) ─────────────────
from .predicate import (  # noqa: E402,F401
    compile_predicate_trampoline, compile_predicate_trampoline_ast,
    compile_predicate_shallow, compile_predicate_shallow_ast,
    compile_predicate, compile_predicate_ast,
    _build_predicate_funcdef, _build_predicate_trampoline_funcdef,
    _shallow_to_trampoline,
    _compile_always_fail, _compile_always_fail_trampoline,
    _install, _stub_body_stmts,
    _EXTRA_FUNCDEF,
)


__all__ = [
    # Shallow / short-stack compilation (bounded-depth predicates)
    "compile_predicate_shallow",
    "compile_predicate_shallow_ast",
    "compile_goal",
    "compile_body",
    # Trampoline / stack-safe compilation (production default)
    "compile_predicate_trampoline",
    "compile_predicate_trampoline_ast",
    "compile_goal_trampoline",
    "compile_body_trampoline",
    "DONE",
    # Shared utilities
    "head_to_match_pattern",
    "compile_head_to_match_case",
    "term_to_ast_expr",
    "arith_to_ast_expr",
    # Deprecated aliases
    "compile_predicate",
    "compile_predicate_ast",
]
