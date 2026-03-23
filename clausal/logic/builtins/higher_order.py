"""Higher-order builtins: CallGoal/1..8, Call/1..8, MapList/2,3,
Filter/3, Exclude/3, Partition/4, TFilter/3, TPartition/4, FoldLeft/4,
TakeWhile/3, DropWhile/3, Span/4, GroupBy/3, SortBy/3,
MaxBy/3, MinBy/3, FilterMap/3."""

from __future__ import annotations

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _ensure_trampoline_dispatch,
    _BUILTINS, _BUILTIN_FIELDS,
)


# ── call_goal/1,2,3 — invoke a goal closure (V2-9 lambdas) ──────────────────


def _make_call_goal_trampoline(extra_n: int):
    """Generate a native trampoline call_goal builtin for *extra_n* extra args."""
    def _call_goal_n(this_generator, parent, *args):
        # args = (goal, extra1, ..., extraN, trail)
        goal_val = deref(args[0])
        if callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
            dispatch = _ensure_trampoline_dispatch(goal_val)
            derefed = [deref(a) for a in args[1:extra_n + 1]]
            trail = args[extra_n + 1]
            sg = StepGenerator(dispatch, this_generator, *derefed, trail)
            _st = yield (sg, None)
            while _st is not DONE:
                yield (parent, None)
                _st = yield (sg, None)
        yield (parent, DONE)
    return _call_goal_n


for _n in range(0, 8):  # extra_n=0..7 → arity 1..8
    _cg_arity = _n + 1
    _BUILTINS[("CallGoal", _cg_arity)] = _make_call_goal_trampoline(_n)
    _BUILTIN_FIELDS[("CallGoal", _cg_arity)] = ("goal",) + tuple(f"a{i}" for i in range(_n))

# Call/1..8 — aliases: Call(Goal, A1, ...) = CallGoal(Goal, A1, ...)
for _n in range(1, 9):
    _key = ("CallGoal", _n)
    if _key in _BUILTINS:
        _BUILTINS[("Call", _n)] = _BUILTINS[_key]
        _BUILTIN_FIELDS[("Call", _n)] = _BUILTIN_FIELDS[_key]

del _n, _cg_arity, _key  # clean up loop variables


# ── Higher-order list predicates (V2-11) ──────────────────────────────────────


@_trampoline_builtin("MapList", 2)
def _map_list__2(this_generator, parent, goal, lst, trail):
    """map_list(Goal, List) — Goal(Elem) succeeds for each element."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    for elem in lst_val:
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        # Got first solution — committed choice, move to next element
    yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("MapList", 3)
def _map_list__3(this_generator, parent, goal, xs, ys, trail):
    """map_list(Goal, Xs, Ys) — Goal(X, Y) maps each X to Y."""
    xs_val = deref(xs)
    goal_val = deref(goal)
    if not isinstance(xs_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    results = []
    for x in xs_val:
        y = Var()
        sg = StepGenerator(dispatch, this_generator, deref(x), y, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        results.append(deref(y))
    if unify(ys, results, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Filter", 3)
def _include__3(this_generator, parent, goal, lst, included, trail):
    """include(Goal, List, Included) — keep elements where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if found:
            kept.append(deref(elem))
    if unify(included, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Exclude", 3)
def _exclude__3(this_generator, parent, goal, lst, excluded, trail):
    """exclude(Goal, List, Excluded) — keep elements where Goal(Elem) fails."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if not found:
            kept.append(deref(elem))
    if unify(excluded, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("FoldLeft", 4)
def _foldl__4(this_generator, parent, goal, lst, v0, v, trail):
    """foldl(Goal, List, V0, V) — left fold with Goal(Elem, Acc0, Acc1)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    acc = v0
    for elem in lst_val:
        next_acc = Var()
        sg = StepGenerator(dispatch, this_generator, deref(elem), deref(acc), next_acc, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        acc = next_acc
    if unify(v, deref(acc), trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


# ── V3-5: Extended higher-order list predicates ──────────────────────────────


def _is_goal(val):
    """Check if val is a callable goal (closure or predicate with dispatch)."""
    return callable(val) or hasattr(val, '_get_dispatch')


@_trampoline_builtin("TakeWhile", 3)
def _take_while__3(this_generator, parent, goal, lst, prefix, trail):
    """TakeWhile(Goal, List, Prefix) — longest prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    taken = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if not found:
            break
        taken.append(deref(elem))
    if unify(prefix, taken, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("DropWhile", 3)
def _drop_while__3(this_generator, parent, goal, lst, suffix, trail):
    """DropWhile(Goal, List, Suffix) — drop prefix where Goal(Elem) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    i = 0
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if not found:
            break
        i += 1
    if unify(suffix, lst_val[i:], trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Span", 4)
def _span__4(this_generator, parent, goal, lst, yes, no, trail):
    """Span(Goal, List, Yes, No) — TakeWhile + DropWhile in one pass."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    taken = []
    i = 0
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if not found:
            break
        taken.append(deref(elem))
        i += 1
    if unify(yes, taken, trail) and unify(no, lst_val[i:], trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("GroupBy", 3)
def _group_by__3(this_generator, parent, goal, lst, groups, trail):
    """GroupBy(Goal, List, Groups) — group consecutive elements by key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    result: list[list] = []
    prev_key = object()  # sentinel
    for elem in lst_val:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        if k == prev_key and result:
            result[-1].append(deref(elem))
        else:
            result.append([deref(elem)])
            prev_key = k
    if unify(groups, result, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("SortBy", 3)
def _sort_by__3(this_generator, parent, goal, lst, sorted_lst, trail):
    """SortBy(Goal, List, Sorted) — sort List by key projected via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    keyed: list[tuple] = []
    for elem in lst_val:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        keyed.append((k, deref(elem)))
    try:
        keyed.sort(key=lambda pair: pair[0])
    except TypeError:
        keyed.sort(key=lambda pair: (type(pair[0]).__name__, repr(pair[0])))
    result = [e for _, e in keyed]
    if unify(sorted_lst, result, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("MaxBy", 3)
def _max_by__3(this_generator, parent, goal, lst, maximum, trail):
    """MaxBy(Goal, List, Max) — element with largest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not lst_val or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    best_key = None
    best_elem = None
    for elem in lst_val:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        if best_key is None or k > best_key:
            best_key = k
            best_elem = deref(elem)
    if best_elem is not None:
        m = trail.mark()
        if unify(maximum, best_elem, trail):
            yield (parent, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("MinBy", 3)
def _min_by__3(this_generator, parent, goal, lst, minimum, trail):
    """MinBy(Goal, List, Min) — element with smallest projected key via Goal(Elem, Key)."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not lst_val or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    best_key = None
    best_elem = None
    for elem in lst_val:
        key = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), key, trail)
        _st = yield (sg, None)
        if _st is DONE:
            trail.undo(mark)
            trail.undo(outer_mark)
            yield (parent, DONE)
            return
        k = deref(key)
        trail.undo(mark)
        if best_key is None or k < best_key:
            best_key = k
            best_elem = deref(elem)
    if best_elem is not None:
        m = trail.mark()
        if unify(minimum, best_elem, trail):
            yield (parent, None)
        trail.undo(m)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("FilterMap", 3)
def _filter_map__3(this_generator, parent, goal, lst, result, trail):
    """FilterMap(Goal, List, Result) — map+filter: keep mapped value when Goal(Elem, Out) succeeds."""
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not _is_goal(goal_val):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
        out = Var()
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), out, trail)
        _st = yield (sg, None)
        found = _st is not DONE
        if found:
            kept.append(deref(out))
        trail.undo(mark)
    if unify(result, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("Partition", 4)
def _partition__4(this_generator, parent, goal, lst, included, excluded, trail):
    """Partition(Goal, List, Included, Excluded) — split list by Goal.

    Included contains elements where Goal(Elem) succeeds.
    Excluded contains elements where Goal(Elem) fails.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in lst_val:
        mark = trail.mark()
        sg = StepGenerator(dispatch, this_generator, deref(elem), trail)
        _st = yield (sg, None)
        found = _st is not DONE
        trail.undo(mark)
        if found:
            yes.append(deref(elem))
        else:
            no.append(deref(elem))
    if unify(included, yes, trail) and unify(excluded, no, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("TFilter", 3)
def _tfilter__3(this_generator, parent, goal, lst, filtered, trail):
    """TFilter(Goal, List, Filtered) — reified filter.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Keep elements where the first solution binds T to True.

    This is the reified counterpart of Filter/3: instead of testing whether
    Goal(Elem) succeeds or fails, it inspects the truth value that Goal
    binds its last argument to.  Useful with reified predicates like Eq/3
    and DifT/3 that always succeed but bind T to True or False.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    kept = []
    for elem in lst_val:
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
    if unify(filtered, kept, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


@_trampoline_builtin("TPartition", 4)
def _tpartition__4(this_generator, parent, goal, lst, included, excluded, trail):
    """TPartition(Goal, List, Included, Excluded) — reified partition.

    Goal is called as Goal(Elem, T) where T is a fresh variable.
    Elements where first solution gives T=True go into Included,
    T=False into Excluded.

    This is the reified counterpart of Partition/4.
    """
    lst_val = deref(lst)
    goal_val = deref(goal)
    if not isinstance(lst_val, list) or not (callable(goal_val) or hasattr(goal_val, '_get_dispatch')):
        yield (parent, DONE)
        return
    dispatch = _ensure_trampoline_dispatch(goal_val)
    outer_mark = trail.mark()
    yes = []
    no = []
    for elem in lst_val:
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
    if unify(included, yes, trail) and unify(excluded, no, trail):
        yield (parent, None)
    trail.undo(outer_mark)
    yield (parent, DONE)


def _run_goal_once(dispatch, *args_and_trail):
    """Run a trampoline dispatch function and yield for each solution.

    Drives the trampoline mini-loop internally so callers can iterate
    solutions with a plain ``for _ in _run_goal_once(...):`` loop.
    """
    gen = dispatch(None, None, *args_and_trail)
    for _parent, value in gen:
        if value is DONE:
            return
        yield value
