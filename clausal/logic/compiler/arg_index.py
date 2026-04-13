"""Argument-indexing and multi-strategy dispatch construction.

Functions that inspect a clause list and build a runtime dispatch
table keyed on the value at one or more argument positions.  The big
``_make_*_dispatch_*`` family emits closures that route calls to the
right subset of clauses; shallow and trampoline variants are kept
side-by-side so the future de-dup refactor is a single-file diff.

This module is heavily used by ``compile_predicate_shallow`` and
``compile_predicate_trampoline`` (still in ``_monolith``) — their
re-imports from here stay stable as the predicate entrypoints move to
``.predicate`` in phase 17.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any, Callable

from clausal.logic.variables import Var, is_var, deref  # noqa: F401
from clausal.logic.trampoline import DONE, StepGenerator  # noqa: F401
from clausal.terms import (
    Compound,
    Call, LoadName, LoadAttr,
    Unify,
)
from clausal.pythonic_ast.nodes import StarUnpack  # noqa: F401
from clausal.logic.predicate import is_term_instance, term_field_names, PredicateMeta  # noqa: F401
from clausal.logic.database import Clause

from ._ast_helpers import _name, _call, _assign  # noqa: F401
from .terms_to_ast import term_to_ast_expr, _dotted_name_from_loadattr  # noqa: F401


# ── First-argument indexing (V2-1) ────────────────────────────────────────────

_INDEX_VAR = object()  # sentinel: clause has variable/non-indexable first arg
_INDEXABLE_TYPES = (int, float, str, bytes, bool, type(None))
_INDEX_THRESHOLD = 4  # minimum clauses before indexing kicks in
_JOINT_COVERAGE_THRESHOLD = 0.8  # min fraction of clauses needing joint key for 9b


# ── Phase 9a: key helpers ────────────────────────────────────────────────────


def _arg_to_index_key(arg: Any) -> Any:
    """Compile-time: convert a head argument to its index key.

    Returns a hashable key for indexable terms:
    - Scalars (int, float, str, bytes, bool, None) → the value itself
    - Compound nodes → ``(functor, arity)`` tuple  (Phase 9a)
    - PredicateMeta instances → ``(class_name, field_count)`` tuple  (Phase 9a)
    - Anything else (Var, list, DictTerm, …) → ``_INDEX_VAR``
    """
    if isinstance(arg, _INDEXABLE_TYPES):
        return arg
    if isinstance(arg, Compound):
        return (arg.functor, len(arg.args))
    if is_term_instance(arg):
        cls = type(arg)
        return (cls.__name__, len(term_field_names(arg)))
    return _INDEX_VAR


def _runtime_arg_key(a: Any) -> Any:
    """Runtime: extract the index key from a deref'd argument value.

    Mirrors :func:`_arg_to_index_key` for the runtime dispatch path.
    All four dispatch closure factories use this so that compound-term
    buckets (Phase 9a) are reachable without special-casing.
    """
    t = type(a)
    if t is int or t is str:
        return a
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR


def _static_call_key(arg_expr: ast.expr) -> Any | None:
    """Return the index key if *arg_expr* is statically known at compile time.

    Mirrors :func:`_runtime_arg_key` for the compile-time call-site analysis
    path.  Returns ``None`` if the argument is a variable or otherwise unknown.
    """
    if isinstance(arg_expr, ast.Constant):
        # scalar: int, str, float, bool, None — key is the value itself
        return arg_expr.value
    if isinstance(arg_expr, ast.Call):
        # compound term constructor: Dog(_v_name, _v_age) or mod.Dog(...)
        func = arg_expr.func
        if isinstance(func, ast.Name):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.id, n_args)
        if isinstance(func, ast.Attribute):
            n_args = len(arg_expr.args) + len(arg_expr.keywords)
            return (func.attr, n_args)
    return None


def _bucket_key(fname: str, pos: int, key: Any) -> str:
    """Readable globals key for a single-position bucket function.

    The returned string is used as an ``ast.Name`` id and as a
    ``base_globals`` key.  It is not a valid Python identifier (it contains
    dots, brackets, and quotes) so generated code won't re-parse, but
    ``ast.unparse()`` renders it readably and ``compile(ast_tree, ...)``
    resolves it via a plain dict lookup.
    """
    return f"{fname}.bucket(pos={pos}, {key!r})"


def _joint_bucket_key(fname: str, pos_i: int, pos_j: int,
                      ki: Any, kj: Any) -> str:
    """Readable globals key for a joint (two-position) bucket function."""
    return f"{fname}.bucket(pos=({pos_i},{pos_j}), ({ki!r},{kj!r}))"


def _extract_arg_key(clause: Clause, pos: int, arity: int) -> Any:
    """Extract the indexing key for a clause's argument at position *pos*.

    Returns a hashable key (scalar or ``(functor, arity)`` tuple) for
    indexable clauses, or ``_INDEX_VAR`` for variable/non-indexable args.
    """
    if arity == 0 or pos >= arity:
        return _INDEX_VAR
    head = clause.head
    # Get arg at position pos from head
    if isinstance(head, Compound):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif isinstance(head, Call) and isinstance(head.func, LoadName):
        if len(head.args) <= pos:
            return _INDEX_VAR
        arg = head.args[pos]
    elif is_term_instance(head):
        fields = term_field_names(head)
        if len(fields) <= pos:
            return _INDEX_VAR
        arg = getattr(head, fields[pos])
    else:
        return _INDEX_VAR
    # Direct ground term (scalar or compound) — Phase 9a extends to compounds.
    key = _arg_to_index_key(arg)
    if key is not _INDEX_VAR:
        return key
    # Var + Unify pattern (from _normalize_dataclass_fact).
    # Phase 9a: also extract compound/predicate keys from Unify targets.
    if is_var(arg):
        for goal in clause.body:
            if isinstance(goal, Unify):
                if goal.left is arg:
                    k = _arg_to_index_key(goal.right)
                    if k is not _INDEX_VAR:
                        return k
                elif goal.right is arg:
                    k = _arg_to_index_key(goal.left)
                    if k is not _INDEX_VAR:
                        return k
        return _INDEX_VAR
    return _INDEX_VAR


def _extract_first_arg_key(clause: Clause, arity: int) -> Any:
    """Extract the indexing key for a clause's first argument.

    Convenience wrapper around :func:`_extract_arg_key` for position 0.
    """
    return _extract_arg_key(clause, 0, arity)


def _build_arg_index(
    clauses: list[Clause], arity: int, pos: int,
    threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """partition clauses into buckets keyed on argument *pos*.

    Returns None if indexing is not beneficial (too few clauses, all defaults,
    or arity == 0).  Otherwise returns::

        {"buckets": {key: [Clause, ...]},  # merged with defaults
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int}

    Each bucket's clause list includes the default (var-headed) clauses
    interleaved in their original order, preserving Prolog clause ordering.
    """
    if arity == 0 or pos >= arity or len(clauses) < threshold:
        return None
    keys = [_extract_arg_key(c, pos, arity) for c in clauses]
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if not specific_indices:
        return None  # all defaults — indexing won't help
    # Group specific clauses by key
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    # Each bucket = bucket-specific + default clauses, merged in original order
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
    }


def _build_first_arg_index(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """partition clauses into first-arg buckets.

    Convenience wrapper around :func:`_build_arg_index` for position 0.
    """
    return _build_arg_index(clauses, arity, 0, threshold)


def _analyze_index_positions(
    clauses: list[Clause], arity: int, threshold: int = _INDEX_THRESHOLD,
) -> list[tuple[int, dict]]:
    """Find argument positions suitable for indexing, sorted by selectivity.

    Returns a list of ``(pos, index_info)`` tuples where each *index_info*
    is the dict from :func:`_build_arg_index`.  Positions are sorted by
    number of distinct keys (most distinct first = most selective).
    """
    if arity == 0 or len(clauses) < threshold:
        return []
    results = []
    for pos in range(arity):
        idx = _build_arg_index(clauses, arity, pos, threshold)
        if idx is not None:
            results.append((pos, idx))
    # Sort by selectivity: most distinct keys first
    results.sort(key=lambda x: -x[1]["n_distinct"])
    return results


# ── Phase 9b: joint (argI, argJ) indexing ───────────────────────────────────


def _build_joint_arg_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
) -> dict | None:
    """Build a flat joint index keyed on ``(key_i, key_j)`` tuples.

    Returns ``None`` when fewer than *threshold* clauses have both args
    indexable.  Otherwise returns the same shape as :func:`_build_arg_index`
    but with tuple keys::

        {"buckets": {(ki, kj): [Clause, ...]},
         "defaults": [Clause, ...],
         "all": [Clause, ...],
         "n_distinct": int,
         "coverage": float}   # fraction of clauses with both args indexable
    """
    if arity < 2 or pos_i == pos_j or pos_i >= arity or pos_j >= arity:
        return None
    keys = []
    for c in clauses:
        ki = _extract_arg_key(c, pos_i, arity)
        kj = _extract_arg_key(c, pos_j, arity)
        if ki is not _INDEX_VAR and kj is not _INDEX_VAR:
            keys.append((ki, kj))
        else:
            keys.append(_INDEX_VAR)
    specific_indices = [i for i, k in enumerate(keys) if k is not _INDEX_VAR]
    if len(specific_indices) < threshold:
        return None
    default_indices = [i for i, k in enumerate(keys) if k is _INDEX_VAR]
    bucket_map: dict[Any, list[int]] = defaultdict(list)
    for i in specific_indices:
        bucket_map[keys[i]].append(i)
    merged_buckets: dict[Any, list[Clause]] = {}
    for key, b_indices in bucket_map.items():
        merged = sorted(b_indices + default_indices)
        merged_buckets[key] = [clauses[i] for i in merged]
    return {
        "buckets": merged_buckets,
        "defaults": [clauses[i] for i in default_indices],
        "all": clauses,
        "n_distinct": len(bucket_map),
        "coverage": len(specific_indices) / len(clauses),
    }


def _analyze_joint_index_positions(
    clauses: list[Clause], arity: int,
    single_indexes: list[tuple[int, dict]],
    min_gain: float = 1.5,
) -> tuple[int, int, dict] | None:
    """Find the best ``(pos_i, pos_j)`` pair for joint indexing.

    Considers pairs ``(best_single_pos, k)`` for all remaining positions *k*.
    Returns ``(pos_i, pos_j, joint_index_info)`` if the joint index offers at
    least *min_gain* × more distinct keys than the best single-arg index, else
    ``None``.
    """
    if not single_indexes or arity < 2:
        return None
    best_single_pos, best_single_idx = single_indexes[0]
    best_single_distinct = best_single_idx["n_distinct"]
    best_joint: tuple[int, int, dict] | None = None
    best_joint_distinct = 0
    for pos in range(arity):
        if pos == best_single_pos:
            continue
        joint = _build_joint_arg_index(clauses, arity, best_single_pos, pos)
        if joint is None:
            continue
        if joint["n_distinct"] > best_joint_distinct:
            best_joint_distinct = joint["n_distinct"]
            best_joint = (best_single_pos, pos, joint)
    if best_joint is None:
        return None
    pos_i, pos_j, joint = best_joint
    if joint["n_distinct"] > best_single_distinct * min_gain:
        return pos_i, pos_j, joint
    return None


def _joint_dispatch_body(
    args, pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn,
):
    """Yield from the appropriate clause bucket given *args* at (pos_i, pos_j).

    Returns a bool indicating whether the fallback path was taken — the
    TRO variant uses this to know when the internal loop must break
    (the fallback itself owns the TRO loop).
    """
    _ai = deref(args[pos_i])
    _aj = deref(args[pos_j])
    if not is_var(_ai) and not is_var(_aj):
        _jk = (_runtime_arg_key(_ai), _runtime_arg_key(_aj))
        try:
            _bfn = joint_dict.get(_jk)
        except TypeError:
            _bfn = None
        if _bfn is not None:
            yield from _bfn(*args)
        else:
            yield from joint_default_fn(*args)
    elif not is_var(_ai):
        yield from single_i_dispatch(*args)
    elif not is_var(_aj):
        yield from single_j_dispatch(*args)
    else:
        yield from fallback_fn(*args)


def _make_joint_dispatch_simple(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn,
) -> Callable:
    """Build a flat joint-key dispatch for simple/short-stack mode.

    Decision tree (Phase 9b):
    1. Both *pos_i* and *pos_j* ground → joint dict lookup (O(1))
    2. Only *pos_i* ground → single-arg dispatch on *pos_i*
    3. Only *pos_j* ground → single-arg dispatch on *pos_j*
    4. Neither ground → *fallback_fn* (linear scan)
    """
    def dispatch(*args):
        yield from _joint_dispatch_body(
            args, pos_i, pos_j, joint_dict, joint_default_fn,
            single_i_dispatch, single_j_dispatch, fallback_fn,
        )
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_joint_dispatch_trampoline(
    pos_i: int, pos_j: int,
    joint_dict: dict, joint_default_fn,
    single_i_dispatch, single_j_dispatch,
    fallback_fn, done,
    tro_state=None, arity=0,
) -> Callable:
    """Build a flat joint-key dispatch for trampoline mode.  (Phase 9b)

    Same decision tree as :func:`_make_joint_dispatch_simple`, wrapped
    with the trampoline Step protocol (``(parent, DONE)`` tail-yield)
    and, when *tro_state* is supplied, an inner TRO tail-call loop that
    restarts dispatch when a clause signals a tail call.
    """
    offset_i = pos_i + 2
    offset_j = pos_j + 2

    if tro_state is not None:
        def dispatch(*args):
            parent = args[1]
            args_list = list(args)
            while True:
                tro_state[0] = False
                # The fallback path owns its own TRO loop, so we must break
                # out of this outer loop when it fires.  Inline the body
                # here to detect that case via which branch was taken.
                _ai = deref(args_list[offset_i])
                _aj = deref(args_list[offset_j])
                if not is_var(_ai) and not is_var(_aj):
                    _jk = (_runtime_arg_key(_ai), _runtime_arg_key(_aj))
                    try:
                        _bfn = joint_dict.get(_jk)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*args_list)
                    else:
                        yield from joint_default_fn(*args_list)
                elif not is_var(_ai):
                    yield from single_i_dispatch(*args_list)
                elif not is_var(_aj):
                    yield from single_j_dispatch(*args_list)
                else:
                    yield from fallback_fn(*args_list)
                    break  # fallback has internal TRO loop
                if tro_state[0]:
                    for _i in range(arity):
                        args_list[_i + 2] = tro_state[_i + 1]
                    continue
                break
            yield (parent, done)
    else:
        def dispatch(*args):
            parent = args[1]
            yield from _joint_dispatch_body(
                args, offset_i, offset_j, joint_dict, joint_default_fn,
                single_i_dispatch, single_j_dispatch, fallback_fn,
            )
            yield (parent, done)

    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


# ── Phase 9c: secondary (hierarchical) dispatch ──────────────────────────────


def _build_secondary_index(
    clauses: list[Clause], arity: int, pos_i: int, pos_j: int,
    threshold: int = _INDEX_THRESHOLD,
    secondary_threshold: int = 2,
) -> dict | None:
    """Build a two-level hierarchical index: level-0 on *pos_i*, level-1 on *pos_j*.

    Level-0 partitions clauses by key at *pos_i* exactly as
    :func:`_build_arg_index` does.  Within each level-0 bucket a second
    :func:`_build_arg_index` on *pos_j* is attempted (using a lower threshold
    since the sub-buckets are smaller).

    Returns::

        {"level0": {ki: (level1_buckets or None, level1_default_clause_list)},
         "level0_defaults": [Clause, ...],
         "pos_i": pos_i,
         "pos_j": pos_j,
         "n_level0": int}

    or ``None`` if the primary index is not viable.
    """
    primary = _build_arg_index(clauses, arity, pos_i, threshold)
    if primary is None:
        return None
    level0: dict[Any, tuple] = {}
    for ki, bucket in primary["buckets"].items():
        secondary = _build_arg_index(bucket, arity, pos_j,
                                     threshold=secondary_threshold)
        if secondary is not None:
            # level-1 default: all clauses in this level-0 bucket.
            # Using bucket (= secondary["all"]) rather than secondary["defaults"]
            # ensures that unbound arg_j queries still scan every matching clause.
            level0[ki] = (secondary["buckets"], bucket)
        else:
            level0[ki] = (None, bucket)
    return {
        "level0": level0,
        "level0_defaults": primary["defaults"],
        "pos_i": pos_i,
        "pos_j": pos_j,
        "n_level0": primary["n_distinct"],
    }


def _make_secondary_dispatch_impl(
    sec_idx: dict,
    level0_compiled: dict,
    level0_default_fn: Callable,
    fallback_fn: Callable,
    *,
    arg_offset: int,
    tail_yield,
) -> Callable:
    """Shared two-level hierarchical dispatch builder.

    Decision tree:
    - *pos_i* var → ``fallback_fn``
    - *pos_i* ground, key unknown → ``level0_default_fn``
    - *pos_i* ground, key found:
      - *pos_j* var or no level-1 index → level-1 default fn
      - *pos_j* ground, key found → level-1 bucket fn
      - *pos_j* ground, key unknown → level-1 default fn

    Strategy differences are the same as in ``_make_indexed_dispatch_impl``:

    - ``arg_offset``: 0 for simple, 2 for trampoline (to skip the
      ``self_generator``/``parent`` prefix in trampoline-mode args).
    - ``tail_yield``: ``None`` for simple (early returns terminate the
      generator); ``lambda args: (args[1], done)`` for trampoline, which
      emits the ``(parent, DONE)`` exhaustion sentinel at the end.
    """
    pos_i = sec_idx["pos_i"] + arg_offset
    pos_j = sec_idx["pos_j"] + arg_offset

    def dispatch(*args):
        _ai = deref(args[pos_i])
        if is_var(_ai):
            yield from fallback_fn(*args)
        else:
            _ki = _runtime_arg_key(_ai)
            try:
                _entry = level0_compiled.get(_ki)
            except TypeError:
                _entry = None
            if _entry is None:
                yield from level0_default_fn(*args)
            else:
                level1_fns, level1_default_fn = _entry
                if level1_fns is None:
                    yield from level1_default_fn(*args)
                else:
                    _aj = deref(args[pos_j])
                    if is_var(_aj):
                        yield from level1_default_fn(*args)
                    else:
                        _kj = _runtime_arg_key(_aj)
                        try:
                            _bfn = level1_fns.get(_kj)
                        except TypeError:
                            _bfn = None
                        if _bfn is not None:
                            yield from _bfn(*args)
                        else:
                            yield from level1_default_fn(*args)
        if tail_yield is not None:
            yield tail_yield(args)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_secondary_dispatch_simple(
    sec_idx: dict,
    level0_compiled: dict,     # {ki: (level1_fn_dict or None, level1_default_fn)}
    level0_default_fn: Callable,
    fallback_fn: Callable,
) -> Callable:
    """Build a two-level hierarchical dispatch for simple mode.  (Phase 9c)

    See ``_make_secondary_dispatch_impl`` for the decision tree.
    """
    return _make_secondary_dispatch_impl(
        sec_idx, level0_compiled, level0_default_fn, fallback_fn,
        arg_offset=0,
        tail_yield=None,
    )


def _make_secondary_dispatch_trampoline(
    sec_idx: dict,
    level0_compiled: dict,
    level0_default_fn: Callable,
    fallback_fn: Callable,
    done: Any,
) -> Callable:
    """Build a two-level hierarchical dispatch for trampoline mode.  (Phase 9c)"""
    return _make_secondary_dispatch_impl(
        sec_idx, level0_compiled, level0_default_fn, fallback_fn,
        arg_offset=2,
        tail_yield=lambda args: (args[1], done),
    )


def _make_indexed_dispatch_impl(all_fn, idx_dict, default_fn, *, arg_offset, tail_yield):
    """Shared indexed-dispatch builder.

    Routes on the first predicate argument (at ``args[arg_offset]``):

    - unbound Var → ``all_fn`` (covers every clause)
    - otherwise   → ``idx_dict[key]`` if known, else ``default_fn``

    The strategy differences are minimal:

    - ``arg_offset``: 0 for simple (predicate args start at position 0);
      2 for trampoline (positions 0/1 are ``self_generator``/``parent``).
    - ``tail_yield``: ``None`` for simple; ``lambda args: (args[1], done)``
      for trampoline, which terminates with a ``(parent, DONE)`` tuple
      as required by the Step protocol.
    """
    def dispatch(*args):
        _a0 = deref(args[arg_offset])
        if is_var(_a0):
            yield from all_fn(*args)
        else:
            _k = _runtime_arg_key(_a0)
            try:
                _bfn = idx_dict.get(_k)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from default_fn(*args)
        if tail_yield is not None:
            yield tail_yield(args)
    dispatch.__name__ = all_fn.__name__
    dispatch.__qualname__ = all_fn.__qualname__
    return dispatch


def _make_indexed_dispatch_simple(all_fn, idx_dict, default_fn):
    """Build an indexed dispatch wrapper for simple/short-stack mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_simple` for V2-2.
    """
    return _make_indexed_dispatch_impl(
        all_fn, idx_dict, default_fn,
        arg_offset=0,
        tail_yield=None,
    )


def _make_indexed_dispatch_trampoline(all_fn, idx_dict, default_fn, done):
    """Build an indexed dispatch wrapper for trampoline mode.

    Legacy V2-1 wrapper — indexes only on the first argument.
    Superseded by :func:`_make_groundness_dispatch_trampoline` for V2-2.
    """
    return _make_indexed_dispatch_impl(
        all_fn, idx_dict, default_fn,
        arg_offset=2,
        tail_yield=lambda args: (args[1], done),
    )


# ── V2-2: Groundness-keyed dispatch ─────────────────────────────────────────


def _groundness_dispatch_body_single(args, pos, idx_dict, dflt_fn, fallback_fn):
    """Yield from the appropriate bucket for a single-position groundness plan.

    If ``args[pos]`` is an unbound Var, fall back to the all-clauses
    scan.  Otherwise look up the bucket keyed on the arg's runtime
    value; missing or TypeError key means the default fn.
    """
    _a = deref(args[pos])
    if is_var(_a):
        yield from fallback_fn(*args)
        return
    _k = _runtime_arg_key(_a)
    try:
        _bfn = idx_dict.get(_k)
    except TypeError:
        _bfn = None
    if _bfn is not None:
        yield from _bfn(*args)
    else:
        yield from dflt_fn(*args)


def _groundness_dispatch_body_multi(args, plans, fallback_fn, arg_offset):
    """Yield from the first plan whose position has a ground argument.

    ``plans`` is a list of ``(pos, idx_dict, default_fn)`` sorted by
    selectivity.  Each position is checked in order; the first ground
    arg triggers its index lookup and short-circuits.  If all positions
    are unbound Vars, fall back to the all-clauses scan.

    ``arg_offset`` is added to each plan's ``pos`` — 0 for simple mode,
    2 for trampoline (to skip ``self_generator`` / ``parent``).
    """
    for _pos, _idx_dict, _dflt_fn in plans:
        _a = deref(args[_pos + arg_offset])
        if not is_var(_a):
            _k = _runtime_arg_key(_a)
            try:
                _bfn = _idx_dict.get(_k)
            except TypeError:
                _bfn = None
            if _bfn is not None:
                yield from _bfn(*args)
            else:
                yield from _dflt_fn(*args)
            return
    yield from fallback_fn(*args)


def _make_groundness_dispatch_simple(plans, fallback_fn):
    """Build a groundness-keyed dispatch selector for simple/short-stack mode.

    *plans* is a list of ``(pos, idx_dict, default_fn)`` tuples, sorted by
    selectivity (most selective position first).  At call time the selector
    checks each position's argument; the first ground argument triggers
    index lookup on that position.  If no argument is ground, *fallback_fn*
    (all clauses, linear scan) is used.

    A single-position plan gets a specialised fast path that skips the
    iteration.  See ``_groundness_dispatch_body_single`` /
    ``_groundness_dispatch_body_multi`` for the shared bodies.
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn = plans[0]
        def dispatch(*args):
            yield from _groundness_dispatch_body_single(
                args, pos, idx_dict, dflt_fn, fallback_fn,
            )
    else:
        def dispatch(*args):
            yield from _groundness_dispatch_body_multi(
                args, plans, fallback_fn, arg_offset=0,
            )
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch


def _make_groundness_dispatch_trampoline(plans, fallback_fn, done,
                                         tro_state=None, arity=0):
    """Build a groundness-keyed dispatch selector for trampoline mode.

    Same logic as :func:`_make_groundness_dispatch_simple` but accounts for
    the trampoline arg layout ``(this_generator, parent, arg0, ..., trail)``
    and emits a trailing ``yield (parent, done)`` after search exhaustion.

    when *tro_state* is not None, the dispatch loops: after each bucket
    ``yield from`` completes, it checks ``tro_state[0]``.  If True, updates
    args from ``tro_state[1..N]`` and re-dispatches (potentially to a
    different bucket).
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn = plans[0]
        offset = pos + 2  # skip this_generator, parent
        if tro_state is not None:
            def dispatch(*args):
                parent = args[1]
                args_list = None
                while True:
                    tro_state[0] = False
                    _current = args_list if args_list is not None else args
                    _a = deref(_current[offset])
                    if is_var(_a):
                        yield from fallback_fn(*_current)
                        break  # fallback has its own internal TRO loop
                    _k = _runtime_arg_key(_a)
                    try:
                        _bfn = idx_dict.get(_k)
                    except TypeError:
                        _bfn = None
                    if _bfn is not None:
                        yield from _bfn(*_current)
                    else:
                        yield from dflt_fn(*_current)
                    if tro_state[0]:
                        if args_list is None:
                            args_list = list(args)
                        for _i in range(arity):
                            args_list[_i + 2] = tro_state[_i + 1]
                        continue
                    break
                yield (parent, done)
        else:
            def dispatch(*args):
                parent = args[1]
                yield from _groundness_dispatch_body_single(
                    args, offset, idx_dict, dflt_fn, fallback_fn,
                )
                yield (parent, done)
        dispatch.__name__ = fallback_fn.__name__
        dispatch.__qualname__ = fallback_fn.__qualname__
        return dispatch

    if tro_state is not None:
        def dispatch(*args):
            parent = args[1]
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _dispatched = False
                for _pos, _idx_dict, _dflt_fn in plans:
                    _a = deref(_current[_pos + 2])
                    if not is_var(_a):
                        _k = _runtime_arg_key(_a)
                        try:
                            _bfn = _idx_dict.get(_k)
                        except TypeError:
                            _bfn = None
                        if _bfn is not None:
                            yield from _bfn(*_current)
                        else:
                            yield from _dflt_fn(*_current)
                        _dispatched = True
                        break
                if not _dispatched:
                    yield from fallback_fn(*_current)
                    break  # fallback has its own internal TRO loop
                if tro_state[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + 2] = tro_state[_i + 1]
                    continue
                break
            yield (parent, done)
    else:
        def dispatch(*args):
            parent = args[1]
            yield from _groundness_dispatch_body_multi(
                args, plans, fallback_fn, arg_offset=2,
            )
            yield (parent, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch
