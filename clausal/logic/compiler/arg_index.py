"""Argument-indexing and multi-strategy dispatch construction.

Functions that inspect a clause list and build a runtime dispatch
table keyed on the value at one or more argument positions.  The big
``_make_*_dispatch_*`` family emits closures that route calls to the
right subset of clauses; shallow and trampoline variants are kept
side-by-side so the future de-dup refactor is a single-file diff.

This module is heavily used by ``compile_predicate_shallow`` and
``compile_predicate_trampoline`` (in ``.predicate``).
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


def _charlist_to_str_or_none(seq) -> str | None:
    """Canonicalise a list/tuple of 1-char strings to its joined str equivalent.

    Returns ``None`` when *seq* is empty or contains any non-1-char element
    (including non-str elements).  Used by the indexer to coalesce the
    strings-as-lists shape duality: a head ``Foo(['a','b','c'])`` and a
    head ``Foo("abc")`` produce the same bucket key, and a caller passing
    either container shape routes to that same bucket.

    F095 fix (Phase 2 Task 8): char-list-of-1-char-strs canonicalises to
    str at both compile-time (``_arg_to_index_key`` / ``_static_call_key``)
    and runtime (``_runtime_arg_key``).  Required for F046 (C4) to fully
    restore the strings-as-lists contract at the dispatch layer — see
    docs/superpowers/audits/2026-05-25-string-implementation/findings.md.
    """
    if not seq:
        return None
    for c in seq:
        if type(c) is not str or len(c) != 1:
            return None
    return "".join(seq)


def _bytelist_to_bytes_or_none(seq) -> bytes | None:
    """Canonicalise a list/tuple of ints in [0, 255] to its joined bytes.

    Returns ``None`` when *seq* is empty or contains any non-int / bool /
    out-of-range element. The bytes-as-lists analog of
    ``_charlist_to_str_or_none``: a head ``Foo(b"abc")`` and a caller passing
    ``[97, 98, 99]`` produce the same bucket key.
    """
    if not seq:
        return None
    for c in seq:
        if type(c) is not int or not (0 <= c <= 255):
            return None
    return bytes(seq)


def _arg_to_index_key(arg: Any) -> Any:
    """Compile-time: convert a head argument to its index key.

    Returns a hashable key for indexable terms:
    - Scalars (int, float, str, bytes, bool, None) → the value itself
    - ``list``/``tuple`` of 1-char strings → the joined ``str``
      (Phase 2 Task 8 — coalesce with the str scalar branch for F095)
    - Compound nodes → ``(functor, arity)`` tuple  (Phase 9a)
    - PredicateMeta instances → ``(class_name, field_count)`` tuple  (Phase 9a)
    - ``Call(LoadName(qn), args)`` (imported-compound head arg) →
      ``(qn.rsplit('.', 1)[-1], len(args))`` so the bucket matches the
      runtime ``(cls.__name__, n_fields)`` key emitted by
      :func:`_runtime_arg_key` for a real instance of that class.
      Must run BEFORE the ``is_term_instance`` branch — Call is itself a
      dataclass and would otherwise key as ``('Call', 4)``, which no
      runtime value ever matches.
    - Anything else (Var, non-charlist list, DictTerm, …) → ``_INDEX_VAR``
    """
    if isinstance(arg, _INDEXABLE_TYPES):
        return arg
    if isinstance(arg, (list, tuple)):
        s = _charlist_to_str_or_none(arg)
        if s is not None:
            return s
        b = _bytelist_to_bytes_or_none(arg)
        if b is not None:
            return b
        return _INDEX_VAR
    if isinstance(arg, Compound):
        return (arg.functor, len(arg.args))
    if isinstance(arg, Call) and isinstance(arg.func, LoadName):
        basename = arg.func.name.rsplit(".", 1)[-1]
        return (basename, len(arg.args))
    # Bare name reference (``LoadName('Red')`` / ``LoadAttr(mod, 'Red')``) — a
    # 0-arity atom used as a value, e.g. the RHS of the ``Unify`` body goal that
    # a keyword-atom fact ``Color(C=Red)`` compiles to.  Key as ``(name, 0)`` so
    # the bucket matches the runtime ``(atom.__name__, 0)`` key that
    # :func:`_runtime_arg_key` emits when the atom resolves to a PredicateMeta.
    # Must run BEFORE ``is_term_instance`` — LoadName/LoadAttr are themselves
    # dataclasses and would otherwise key as ``('LoadName', 2)``, which no
    # runtime value ever matches (leaving ground callers with no bucket and an
    # empty default set → spurious "no solutions").
    if isinstance(arg, (LoadName, LoadAttr)):
        dotted = _dotted_name_from_loadattr(arg)
        if dotted is not None:
            return (dotted.rsplit(".", 1)[-1], 0)
        return _INDEX_VAR
    # PredicateMeta atom (zero-arity predicate class used as a value). Keyed as
    # ``(name, 0)`` so atom-headed clauses are indexable again — the string→
    # PredicateMeta migration (commit 92ce2636) dropped atoms out of the
    # indexable set, forcing a linear scan. Matches the runtime key emitted by
    # :func:`_runtime_arg_key`. Must precede ``is_term_instance`` (False for a
    # class, but kept adjacent for clarity).
    if isinstance(arg, type) and isinstance(arg, PredicateMeta):
        return (arg.__name__, 0)
    if is_term_instance(arg):
        cls = type(arg)
        return (cls.__name__, len(term_field_names(arg)))
    return _INDEX_VAR


def _runtime_arg_key(a: Any) -> Any:
    """Runtime: extract the index key from a deref'd argument value.

    Mirrors :func:`_arg_to_index_key` for the runtime dispatch path.
    All four dispatch closure factories use this so that compound-term
    buckets (Phase 9a) are reachable without special-casing.

    Phase 2 Task 8 (F095): a ``list``/``tuple`` of 1-char strings is
    canonicalised to its joined ``str`` so str-headed and charlist-headed
    clauses share a bucket and a caller of either container shape routes
    to it.
    """
    t = type(a)
    if t is int or t is str:
        return a
    if isinstance(a, _INDEXABLE_TYPES):
        return a
    if isinstance(a, (list, tuple)):
        s = _charlist_to_str_or_none(a)
        if s is not None:
            return s
        b = _bytelist_to_bytes_or_none(a)
        if b is not None:
            return b
        return _INDEX_VAR
    if isinstance(a, Compound):
        return (a.functor, len(a.args))
    # PredicateMeta atom: mirror _arg_to_index_key so a runtime atom argument
    # routes to the same bucket as its head key.
    if isinstance(a, type) and isinstance(a, PredicateMeta):
        return (a.__name__, 0)
    if is_term_instance(a):
        cls = type(a)
        return (cls.__name__, len(term_field_names(a)))
    return _INDEX_VAR


def _static_call_key(arg_expr: ast.expr) -> Any | None:
    """Return the index key if *arg_expr* is statically known at compile time.

    Mirrors :func:`_runtime_arg_key` for the compile-time call-site analysis
    path.  Returns ``None`` if the argument is a variable or otherwise unknown.

    Phase 2 Task 8 (F095): a literal list/tuple of 1-char string constants
    canonicalises to its joined ``str`` for the same reason
    :func:`_runtime_arg_key` does — see :func:`_charlist_to_str_or_none`.
    """
    if isinstance(arg_expr, ast.Constant):
        # scalar: int, str, float, bool, None — key is the value itself
        return arg_expr.value
    if isinstance(arg_expr, (ast.List, ast.Tuple)):
        # literal list/tuple — if every element is a 1-char str constant,
        # canonicalise to the joined str so dispatch sees the same bucket
        # as a str caller.  Otherwise, no static key.
        elts = []
        for e in arg_expr.elts:
            if not isinstance(e, ast.Constant):
                return None
            elts.append(e.value)
        s = _charlist_to_str_or_none(elts)
        if s is not None:
            return s
        return _bytelist_to_bytes_or_none(elts)
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


def _drive_tro_bucket(gen, tro_state, arity, pending):
    """Yield from a signal-mode bucket generator while snapshotting a pending
    TRO tail-call signal into *pending* the instant it appears.

    A signal-mode TRO clause sets ``tro_state[0] = True`` and falls through
    (it does not yield); a LATER match arm in the same bucket may then yield a
    solution while the flag is still pending, suspending this generator.  Any
    re-entry into the same predicate during that suspension (a sibling goal, a
    nested self-call) resets the shared ``tro_state[0]`` at its own dispatch
    entry, which would silently drop the pending tail call — the enclosing
    dispatch loop would then read ``False`` and lose every remaining solution.
    See todo/tro-signal-flag-clobbered-by-later-match-arms.md.

    Capturing the signal into the per-activation *pending* list before each
    downstream ``yield`` makes the dispatch loop immune to that clobber: it
    re-dispatches from *pending*, not from the shared (re-entrant) cell.

    *pending* is a list of length ``arity + 1``: ``pending[0]`` is the
    tail-pending flag, ``pending[1:]`` the snapshotted tail-call args.  On a
    later signal the snapshot is overwritten (last-write-wins), matching the
    pre-fix semantics where the after-arms check read the final ``tro_state``.

    This is a full delegating generator (PEP-380 ``yield from`` semantics):
    it forwards ``send``/``throw``/``close`` to *gen* so the trampoline Step
    protocol — which resumes buckets via ``.send(value)`` and unwinds via
    ``.throw()`` for catch/3 — keeps working.  A plain ``for``-loop wrapper
    would swallow sent values and break it.
    """
    def _snapshot():
        if tro_state[0]:
            pending[0] = True
            for _i in range(arity):
                pending[_i + 1] = tro_state[_i + 1]

    try:
        _y = next(gen)
    except StopIteration:
        _snapshot()
        return
    while True:
        _snapshot()  # capture BEFORE yielding — before any re-entry can clobber
        try:
            _sent = yield _y
        except GeneratorExit:
            gen.close()
            raise
        except BaseException as _exc:
            try:
                _y = gen.throw(_exc)
            except StopIteration:
                _snapshot()
                return
        else:
            try:
                _y = gen.send(_sent)
            except StopIteration:
                _snapshot()
                return


def _make_call_site_bucket_trampoline(bucket_fn, dispatch_fn, done,
                                      tro_state=None, arity=0):
    """Wrap a SIGNAL-mode bucket for direct call-site use (Phase 10 /
    ``call_site`` optimisation).

    Buckets are compiled with ``emit_done=False``: they neither emit the
    terminal ``yield (fail, done)`` nor loop on TRO tail calls — the
    enclosing dispatch closure does both.  A call-site-specialised caller
    (``SubCall.direct_bucket_ref``) drives the bucket *directly* via
    ``StepGenerator``, so the function exposed through ``_index_plans`` /
    ``_index_plans_joint`` must complete the trampoline contract itself:
    emit the terminal done, and when the bucket signals a TRO tail call,
    delegate to the full *dispatch_fn* (the new args may key to a
    different bucket).  Driving a raw bucket instead raises
    ``RuntimeError: StepGenerator inner generator returned unexpectedly
    (no final yield)`` — see
    todo/call-site-imported-ground-arg-4plus-clauses-runtime-error.md.
    """
    if tro_state is None:
        def call_site_fn(*args):
            _fail = args[2]
            yield from bucket_fn(*args)
            yield (_fail, done)
    else:
        def call_site_fn(*args):
            _fail = args[2]
            tro_state[0] = False
            _pending = [False] + [None] * arity
            yield from _drive_tro_bucket(
                bucket_fn(*args), tro_state, arity, _pending)
            if _pending[0]:
                args_list = list(args)
                for _i in range(arity):
                    args_list[_i + 4] = _pending[_i + 1]
                # dispatch_fn loops on any further tail calls and emits
                # its own terminal ``(fail, done)``.
                yield from dispatch_fn(*args_list)
            else:
                yield (_fail, done)
    call_site_fn.__name__ = bucket_fn.__name__
    call_site_fn.__qualname__ = bucket_fn.__qualname__
    return call_site_fn


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
        _ki = _runtime_arg_key(_ai)
        _kj = _runtime_arg_key(_aj)
        # A02-F001: an uncomputable component means the joint key can't be
        # formed. Degrade to the single-position dispatch on the OTHER
        # (computable) component — which itself scans when its key is also
        # uncomputable — rather than hitting the joint default (often an
        # always-fail bucket that drops all solutions).
        if _ki is _INDEX_VAR and _kj is _INDEX_VAR:
            yield from fallback_fn(*args)
        elif _ki is _INDEX_VAR:
            yield from single_j_dispatch(*args)
        elif _kj is _INDEX_VAR:
            yield from single_i_dispatch(*args)
        else:
            _jk = (_ki, _kj)
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
    with the trampoline Step protocol (``(_fail, DONE)`` tail-yield)
    and, when *tro_state* is supplied, an inner TRO tail-call loop that
    restarts dispatch when a clause signals a tail call.
    """
    # Phase 2: trampoline layout is
    # (this_generator, _proceed, _fail, _catcher, arg0, ..., trail).
    # Skip four slots (this_generator + three continuations) to reach arg0.
    offset_i = pos_i + 4
    offset_j = pos_j + 4

    if tro_state is not None:
        def dispatch(*args):
            _fail = args[2]
            args_list = list(args)
            while True:
                tro_state[0] = False
                # Select the route, then drive it through _drive_tro_bucket so
                # a tail call signalled from a non-last arm survives re-entrant
                # clobbering of the shared tro_state (see _drive_tro_bucket).
                _ai = deref(args_list[offset_i])
                _aj = deref(args_list[offset_j])
                if not is_var(_ai) and not is_var(_aj):
                    _ki = _runtime_arg_key(_ai)
                    _kj = _runtime_arg_key(_aj)
                    # A02-F001: an uncomputable component means the joint
                    # key can't be formed — degrade exactly like the non-TRO
                    # body (_joint_dispatch_body): both uncomputable → full
                    # scan; one uncomputable → single-position dispatch on
                    # the OTHER (computable) component. Every route is compiled
                    # in SIGNAL mode (buckets/fallback) or owns its own TRO
                    # loop (single dispatches), so re-dispatch is uniform.
                    if _ki is _INDEX_VAR and _kj is _INDEX_VAR:
                        _bfn = fallback_fn
                    elif _ki is _INDEX_VAR:
                        _bfn = single_j_dispatch
                    elif _kj is _INDEX_VAR:
                        _bfn = single_i_dispatch
                    else:
                        _jk = (_ki, _kj)
                        try:
                            _bfn = joint_dict.get(_jk)
                        except TypeError:
                            _bfn = None
                        if _bfn is None:
                            _bfn = joint_default_fn
                elif not is_var(_ai):
                    _bfn = single_i_dispatch
                elif not is_var(_aj):
                    _bfn = single_j_dispatch
                else:
                    # A02-F001: neither arg ground — full scan (signal-mode).
                    _bfn = fallback_fn
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _bfn(*args_list), tro_state, arity, _pending)
                if _pending[0]:
                    for _i in range(arity):
                        args_list[_i + 4] = _pending[_i + 1]
                    continue
                break
            yield (_fail, done)
    else:
        def dispatch(*args):
            _fail = args[2]
            yield from _joint_dispatch_body(
                args, offset_i, offset_j, joint_dict, joint_default_fn,
                single_i_dispatch, single_j_dispatch, fallback_fn,
            )
            yield (_fail, done)

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
    tro_state=None,
    arity: int = 0,
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

    - ``arg_offset``: 0 for simple, 4 for trampoline. The Phase-2 trampoline
      layout is ``(this_generator, _proceed, _fail, _catcher, arg0, …,
      trail)`` — skip four slots (this_generator + three continuations) to
      reach arg0.
    - ``tail_yield``: ``None`` for simple (early returns terminate the
      generator); ``lambda args: (args[2], done)`` for trampoline, which
      emits the ``(_fail, DONE)`` exhaustion sentinel at the end
      (``args[2]`` is the ``_fail`` continuation in the Phase-2 layout).
    - ``tro_state`` / ``arity``: when *tro_state* is supplied (trampoline
      TRO), the dispatch loops: level-0/level-1 buckets never signal
      (compiled without ``tro_indices``), but *fallback_fn* is the shared
      SIGNAL-mode ``{functor}__all`` — after each route, if
      ``tro_state[0]`` is set the args are updated from
      ``tro_state[1..arity]`` and the decision tree re-runs (the updated
      args may now key into a level-0 bucket). Without the loop a
      fallback tail call is silently dropped (0 solutions).
    """
    pos_i = sec_idx["pos_i"] + arg_offset
    pos_j = sec_idx["pos_j"] + arg_offset

    def _route(args):
        _ai = deref(args[pos_i])
        _ki = _runtime_arg_key(_ai) if not is_var(_ai) else None
        if is_var(_ai) or _ki is _INDEX_VAR:
            # A02-F001: an unbound arg OR a non-var arg with an uncomputable
            # level-0 key (partial container, Decimal, …) must scan all
            # clauses. Routing an uncomputable key to the level-0 default —
            # an always-fail bucket when no clause has a var first arg —
            # would drop every solution the arg would unify with.
            yield from fallback_fn(*args)
        else:
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

    if tro_state is not None:
        def dispatch(*args):
            # The level-0/level-1 buckets are compiled without TRO, but
            # fallback_fn is the shared SIGNAL-mode `{functor}__all` — a
            # tail call signalled there must re-dispatch (the updated args
            # may now key into a level-0 bucket), not be dropped.
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _route(_current), tro_state, arity, _pending)
                if _pending[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + arg_offset] = _pending[_i + 1]
                    continue
                break
            if tail_yield is not None:
                yield tail_yield(args)
    else:
        def dispatch(*args):
            yield from _route(args)
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
    tro_state=None,
    arity: int = 0,
) -> Callable:
    """Build a two-level hierarchical dispatch for trampoline mode.  (Phase 9c)"""
    return _make_secondary_dispatch_impl(
        sec_idx, level0_compiled, level0_default_fn, fallback_fn,
        arg_offset=4,
        tail_yield=lambda args: (args[2], done),
        tro_state=tro_state, arity=arity,
    )


def _make_indexed_dispatch_impl(all_fn, idx_dict, default_fn, *, arg_offset, tail_yield):
    """Shared indexed-dispatch builder.

    Routes on the first predicate argument (at ``args[arg_offset]``):

    - unbound Var → ``all_fn`` (covers every clause)
    - otherwise   → ``idx_dict[key]`` if known, else ``default_fn``

    The strategy differences are minimal:

    - ``arg_offset``: 0 for simple (predicate args start at position 0);
      4 for trampoline. The Phase-2 trampoline layout is
      ``(this_generator, _proceed, _fail, _catcher, arg0, …, trail)`` — skip
      four slots (this_generator + three continuations) to reach arg0.
    - ``tail_yield``: ``None`` for simple; ``lambda args: (args[2], done)``
      for trampoline, which terminates with a ``(_fail, DONE)`` tuple
      (``args[2]`` is the ``_fail`` continuation in the Phase-2 layout)
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
        arg_offset=4,
        tail_yield=lambda args: (args[2], done),
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
    if _k is _INDEX_VAR:
        # A02-F001: a non-var arg whose index key is uncomputable (partial
        # char/code-list, empty list, SegList, Decimal, …) must scan ALL
        # clauses — not the default bucket (var-headed only), which would
        # silently drop keyed buckets the arg would happily unify with.
        yield from fallback_fn(*args)
        return
    try:
        _bfn = idx_dict.get(_k)
    except TypeError:
        # Unhashable key (defensive) → same uncomputable-key fallback.
        yield from fallback_fn(*args)
        return
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

    ``arg_offset`` is added to each plan's ``pos`` — 0 for simple mode, 4 for
    trampoline. The Phase-2 trampoline layout is ``(this_generator, _proceed,
    _fail, _catcher, arg0, …, trail)`` — skip four slots (this_generator +
    three continuations) to reach arg0.
    """
    for _pos, _idx_dict, _dflt_fn in plans:
        _a = deref(args[_pos + arg_offset])
        if not is_var(_a):
            _k = _runtime_arg_key(_a)
            if _k is _INDEX_VAR:
                # A02-F001: uncomputable key at this plan — try the NEXT
                # plan (another position may index) before falling back.
                continue
            try:
                _bfn = _idx_dict.get(_k)
            except TypeError:
                continue
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
    the trampoline arg layout
    ``(this_generator, _proceed, _fail, _catcher, arg0, ..., trail)``
    (Phase 2 split-continuation) and emits a trailing
    ``yield (_fail, done)`` after search exhaustion.

    when *tro_state* is not None, the dispatch loops: after each bucket
    ``yield from`` completes, it checks ``tro_state[0]``.  If True, updates
    args from ``tro_state[1..N]`` and re-dispatches (potentially to a
    different bucket).
    """
    if len(plans) == 1:
        pos, idx_dict, dflt_fn = plans[0]
        offset = pos + 4  # skip this_generator, _proceed, _fail, _catcher
        if tro_state is not None:
            def dispatch(*args):
                _fail = args[2]
                args_list = None
                while True:
                    tro_state[0] = False
                    _current = args_list if args_list is not None else args
                    _a = deref(_current[offset])
                    # A02-F001: an unbound Var, a non-var arg with an
                    # uncomputable key (partial char/code-list, Decimal, …),
                    # or an unhashable key (defensive) must scan ALL clauses,
                    # not the default bucket — mirror the non-TRO
                    # _groundness_dispatch_body_single guard. The fallback is
                    # compiled in SIGNAL mode (emit_done=False ⇒
                    # tro_mode="signal"), exactly like the buckets, so it must
                    # fall through to the tro_state check below: a tail call
                    # signalled from its TRO clause re-dispatches (possibly
                    # into an indexed bucket) instead of being dropped.
                    if is_var(_a):
                        _bfn = fallback_fn
                    else:
                        _k = _runtime_arg_key(_a)
                        if _k is _INDEX_VAR:
                            _bfn = fallback_fn
                        else:
                            try:
                                _bfn = idx_dict.get(_k)
                            except TypeError:
                                _bfn = fallback_fn
                            if _bfn is None:
                                _bfn = dflt_fn
                    _pending = [False] + [None] * arity
                    yield from _drive_tro_bucket(
                        _bfn(*_current), tro_state, arity, _pending)
                    if _pending[0]:
                        if args_list is None:
                            args_list = list(args)
                        for _i in range(arity):
                            args_list[_i + 4] = _pending[_i + 1]
                        continue
                    break
                yield (_fail, done)
        else:
            def dispatch(*args):
                _fail = args[2]
                yield from _groundness_dispatch_body_single(
                    args, offset, idx_dict, dflt_fn, fallback_fn,
                )
                yield (_fail, done)
        dispatch.__name__ = fallback_fn.__name__
        dispatch.__qualname__ = fallback_fn.__qualname__
        return dispatch

    if tro_state is not None:
        def dispatch(*args):
            _fail = args[2]
            args_list = None
            while True:
                tro_state[0] = False
                _current = args_list if args_list is not None else args
                _bfn = None
                for _pos, _idx_dict, _dflt_fn in plans:
                    _a = deref(_current[_pos + 4])
                    if not is_var(_a):
                        _k = _runtime_arg_key(_a)
                        if _k is _INDEX_VAR:
                            # A02-F001: uncomputable key at this plan — try
                            # the NEXT plan (another position may index)
                            # before the full-scan fallback, mirroring the
                            # non-TRO _groundness_dispatch_body_multi.
                            continue
                        try:
                            _cand = _idx_dict.get(_k)
                        except TypeError:
                            continue
                        _bfn = _cand if _cand is not None else _dflt_fn
                        break
                if _bfn is None:
                    # A02-F001: no plan had a ground arg with a computable
                    # key — full scan. The fallback is compiled in SIGNAL
                    # mode (like the buckets), so its tail call re-dispatches.
                    _bfn = fallback_fn
                _pending = [False] + [None] * arity
                yield from _drive_tro_bucket(
                    _bfn(*_current), tro_state, arity, _pending)
                if _pending[0]:
                    if args_list is None:
                        args_list = list(args)
                    for _i in range(arity):
                        args_list[_i + 4] = _pending[_i + 1]
                    continue
                break
            yield (_fail, done)
    else:
        def dispatch(*args):
            _fail = args[2]
            yield from _groundness_dispatch_body_multi(
                args, plans, fallback_fn, arg_offset=4,
            )
            yield (_fail, done)
    dispatch.__name__ = fallback_fn.__name__
    dispatch.__qualname__ = fallback_fn.__qualname__
    return dispatch
