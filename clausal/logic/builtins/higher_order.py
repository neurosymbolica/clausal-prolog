"""Higher-order builtins: call_goal/1..8, call/1..8, maplist/2,3,
include/3, exclude/3, partition/4, tfilter/3, tpartition/4, foldl/4,
take_while/3, drop_while/3, span/4, group_by/3, sort_by/3,
max_by/3, min_by/3, filter_map/3."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.builtins.lists import _as_items, _seq_result

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _ensure_trampoline_dispatch,
    _BUILTINS, _BUILTIN_FIELDS,
)


# ── call_goal/1,2,3 — invoke a goal closure (V2-9 lambdas) ──────────────────


def _make_call_goal_trampoline(extra_n: int):
    """Generate a native trampoline call_goal builtin for *extra_n* extra args."""
    def _call_goal_n(this_generator, _proceed, _fail, _catcher, *args):
        # args = (goal, extra1, ..., extraN, trail)
        goal_val = deref(args[0])
        if callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
            dispatch = _ensure_trampoline_dispatch(goal_val)
            derefed = [deref(a) for a in args[1:extra_n + 1]]
            trail = args[extra_n + 1]
            sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *derefed, trail)
            _st = yield (sg, None)
            while _st is not DONE:
                yield (_proceed, None)
                _st = yield (sg, None)
        yield (_fail, DONE)
    return _call_goal_n


for _n in range(0, 8):  # extra_n=0..7 → arity 1..8
    _cg_arity = _n + 1
    _BUILTINS[("call_goal", _cg_arity)] = _make_call_goal_trampoline(_n)
    _BUILTIN_FIELDS[("call_goal", _cg_arity)] = ("goal",) + tuple(f"a{i}" for i in range(_n))

# call/1..8 — aliases: call(Goal, A1, ...) = call_goal(Goal, A1, ...)
for _n in range(1, 9):
    _key = ("call_goal", _n)
    if _key in _BUILTINS:
        _BUILTINS[("call", _n)] = _BUILTINS[_key]
        _BUILTIN_FIELDS[("call", _n)] = _BUILTIN_FIELDS[_key]

del _n, _cg_arity, _key  # clean up loop variables


# ── Higher-order list predicates (V2-11) ──────────────────────────────────────


@_trampoline_builtin("maplist", 2)
def _map_list__2(this_generator, _proceed, _fail, _catcher, goal, lst, trail):
    """map_list(Goal, List) — Goal(Elem) succeeds for each element."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    for elem in items:
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        # Got first solution — committed choice, move to next element
    yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("maplist", 3)
def _map_list__3(this_generator, _proceed, _fail, _catcher, goal, xs, ys, trail):
    """map_list(Goal, Xs, Ys) — Goal(X, Y) maps each X to Y.

    F063 (C9 audit, option A): result is wrapped via ``_seq_result`` so
    str input with all-1-char-str result elements collapses to a
    ``str``; list input keeps list output.
    """
    xs_val = deref(xs)
    goal_val = deref(goal)
    xs_items = _as_items(xs_val)
    if xs_items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(xs_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    results = []
    for x in xs_items:
        y = Var()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(x), y, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        results.append(deref(y))
    if unify(ys, _seq_result(results, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("include", 3)
def _include__3(this_generator, _proceed, _fail, _catcher, goal, lst, included, trail):
    """include(Goal, List, Included) — keep elements where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F003: keep the successful test's bindings (SWI `->`
            # semantics) so a Var element the test bound persists into the
            # result; only a FAILED test's half-bindings are undone.
            kept.append(deref(elem))
        else:
            trail.undo(mark)
    if unify(included, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("exclude", 3)
def _exclude__3(this_generator, _proceed, _fail, _catcher, goal, lst, excluded, trail):
    """exclude(Goal, List, Excluded) — keep elements where Goal(Elem) fails."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            # A09-F003: goal failed → element kept; undo its half-bindings.
            trail.undo(mark)
            kept.append(deref(elem))
        # goal succeeded → excluded; its bindings persist (SWI `->`).
    if unify(excluded, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("foldl", 4)
def _foldl__4(this_generator, _proceed, _fail, _catcher, goal, lst, v0, v, trail):
    """foldl(Goal, List, V0, V) — left fold with Goal(Elem, Acc0, Acc1)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    acc = v0
    for elem in items:
        next_acc = Var()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), deref(acc), next_acc, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        acc = next_acc
    if unify(v, deref(acc), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


# ── V3-5: Extended higher-order list predicates ──────────────────────────────


def _is_goal(val):
    """Check if val is a callable goal (closure or predicate with dispatch)."""
    return callable(val) or hasattr(val, '_get_dispatch')


@_trampoline_builtin("take_while", 3)
def _take_while__3(this_generator, _proceed, _fail, _catcher, goal, lst, prefix, trail):
    """take_while(Goal, List, Prefix) — longest prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    taken = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        taken.append(deref(elem))  # keep the successful test's bindings
    if unify(prefix, _seq_result(taken, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("drop_while", 3)
def _drop_while__3(this_generator, _proceed, _fail, _catcher, goal, lst, suffix, trail):
    """drop_while(Goal, List, Suffix) — drop prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    i = 0
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        i += 1
    if unify(suffix, _seq_result(items[i:], was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("span", 4)
def _span__4(this_generator, _proceed, _fail, _catcher, goal, lst, yes, no, trail):
    """span(Goal, List, Yes, No) — take_while + drop_while in one pass."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    taken = []
    i = 0
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if not found:
            trail.undo(mark)  # A09-F003: discard failed test's half-bindings
            break
        taken.append(deref(elem))  # keep the successful test's bindings
        i += 1
    if unify(yes, _seq_result(taken, was_str), trail) and unify(no, _seq_result(items[i:], was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("group_by", 3)
def _group_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, groups, trail):
    """group_by(Goal, List, Groups) — group consecutive elements by key via Goal(Elem, Key).

    F063 (C9 audit, option A): inner groups and the outer container
    are wrapped via ``_seq_result`` so str input collapses each inner
    group (slice of the input) and the outer list of groups to str
    when the elements are 1-char strs; list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    result: list[list] = []
    prev_key = object()  # sentinel
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        if k == prev_key and result:
            result[-1].append(deref(elem))
        else:
            result.append([deref(elem)])
            prev_key = k
    # F063: each inner group is a slice of the input — promote to str
    # when the input was a str. The outer container stays a list (a
    # str cannot contain str elements as distinct cells under the
    # strings-as-lists contract).
    final = [_seq_result(g, was_str) for g in result]
    if unify(groups, final, trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("sort_by", 3)
def _sort_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, sorted_lst, trail):
    """sort_by(Goal, List, Sorted) — sort List by key projected via Goal(Elem, Key).

    F063 (C9 audit, option A): result is wrapped via ``_seq_result``
    so str input with all-1-char-str elements collapses to a ``str``;
    list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    try:
        keyed.sort(key=lambda pair: pair[0])
    except TypeError:
        keyed.sort(key=lambda pair: (type(pair[0]).__name__, repr(pair[0])))
    result = [e for _, e in keyed]
    if unify(sorted_lst, _seq_result(result, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("max_by", 3)
def _max_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, maximum, trail):
    """max_by(Goal, List, max_) — element with largest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not items or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    # A09-F012: incomparable keys (e.g. int vs str) raised a raw TypeError
    # from `k > best_key`, uncatchable by catch/3 — while sort_by silently
    # falls back. Use the same (type-name, repr) fallback so max_by/min_by
    # are consistent with sort_by instead of crashing.
    if keyed:
        try:
            best_elem = max(keyed, key=lambda pair: pair[0])[1]
        except TypeError:
            best_elem = max(keyed, key=lambda pair: (type(pair[0]).__name__, repr(pair[0])))[1]
    else:
        best_elem = None
    if best_elem is not None:
        m = trail.mark()
        if unify(maximum, best_elem, trail):
            yield (_proceed, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("min_by", 3)
def _min_by__3(this_generator, _proceed, _fail, _catcher, goal, lst, minimum, trail):
    """min_by(Goal, List, min_) — element with smallest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not items or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in items:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (_fail, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    # A09-F012: same (type-name, repr) fallback as sort_by / max_by so
    # incomparable keys do not leak a raw TypeError.
    if keyed:
        try:
            best_elem = min(keyed, key=lambda pair: pair[0])[1]
        except TypeError:
            best_elem = min(keyed, key=lambda pair: (type(pair[0]).__name__, repr(pair[0])))[1]
    else:
        best_elem = None
    if best_elem is not None:
        m = trail.mark()
        if unify(minimum, best_elem, trail):
            yield (_proceed, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("filter_map", 3)
def _filter_map__3(this_generator, _proceed, _fail, _catcher, goal, lst, result, trail):
    """filter_map(Goal, List, Result) — map+filter: keep mapped value when Goal(Elem, Out) succeeds.

    F063 (C9 audit, option A): result is wrapped via ``_seq_result``
    so str input with all-1-char-str result elements collapses to a
    ``str``; list input keeps list output.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not _is_goal(goal_val):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        out = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), out, trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F002: keep the goal's bindings — deref(out) is a top-level
            # walk, so undoing here would strip the bindings the goal made
            # INSIDE the output term (e.g. pair(X, Y) with Y bound).
            kept.append(deref(out))
        else:
            trail.undo(mark)
    if unify(result, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("partition", 4)
def _partition__4(this_generator, _proceed, _fail, _catcher, goal, lst, included, excluded, trail):
    """partition(Goal, List, Included, Excluded) — split list by Goal.

    Included contains elements where Goal(Elem) succeeds.
    Excluded contains elements where Goal(Elem) fails.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in items:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            # A09-F003: keep the successful test's bindings (SWI `->`).
            yes.append(deref(elem))
        else:
            trail.undo(mark)  # discard a failed test's half-bindings
            no.append(deref(elem))
    if unify(included, _seq_result(yes, was_str), trail) and unify(excluded, _seq_result(no, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("tfilter", 3)
def _tfilter__3(this_generator, _proceed, _fail, _catcher, goal, lst, filtered, trail):
    """tfilter(Goal, List, Filtered) — reified filter.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Keep elements where the first solution binds T to True.

    This is the reified counterpart of include/3: instead of testing whether
    Goal(Elem) succeeds or fails, it inspects the truth value that Goal
    binds its last argument to.  Useful with reified predicates like eq/3
    and dif_t/3 that always succeed but bind T to True or False.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in items:
        t_var = Var()
        mark = trail.mark()
        # Run the goal inline (simple-mode) to get the truth value
        # without going through the trampoline yield protocol.
        t_val = None
        for _ in _run_goal_once(dispatch, deref(elem), t_var, trail):
            t_val = deref(t_var)
            break  # committed choice: take first solution only
        trail.undo(mark)
        if t_val is True:
            kept.append(deref(elem))
    if unify(filtered, _seq_result(kept, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


@_trampoline_builtin("tpartition", 4)
def _tpartition__4(this_generator, _proceed, _fail, _catcher, goal, lst, included, excluded, trail):
    """tpartition(Goal, List, Included, Excluded) — reified partition.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Elements where first solution gives T=True go into Included,
    T=False into Excluded.

    This is the reified counterpart of partition/4.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    items = _as_items(lst_val)
    if items is None or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (_fail, DONE)
        return
    was_str = isinstance(lst_val, str)
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in items:
        t_var = Var()
        mark = trail.mark()
        t_val = None
        for _ in _run_goal_once(dispatch, deref(elem), t_var, trail):
            t_val = deref(t_var)
            break
        trail.undo(mark)
        if t_val is True:
            yes.append(deref(elem))
        elif t_val is False:
            no.append(deref(elem))
    if unify(included, _seq_result(yes, was_str), trail) and unify(excluded, _seq_result(no, was_str), trail):
        yield (_proceed, None)
    trail.undo(outer_mark)
    yield (_fail, DONE)


def _run_goal_once(dispatch, *args_and_trail):
    """Run a trampoline dispatch function and yield for each solution.

    Drives the trampoline mini-loop internally so callers can iterate
    solutions with a plain ``for _ in _run_goal_once(...):`` loop.
    """
    gen = dispatch(None, None, None, None, *args_and_trail)
    for _parent, value in gen:
        if value is DONE:
            return
        yield value
