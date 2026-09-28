"""Pair builtins, as Scryer's ``library(pairs)``: pairs_keys_values/3,
pairs_keys/2, pairs_values/2, group_pairs_by_key/2.

A pair is the term ``Key-Value``: the cell ``('-', Key, Value)``.  A pair
written in source as ``k - v`` reaches a builtin as the pythonic ``Sub``
node, which is the same term spelled differently; both are read as a pair.
A pair these builtins BUILD is always the cell.

Scryer's library defines them in plain Prolog and raises no errors: an
argument that is not a list, or an element that is not a pair, makes the
relation fail.  Each builtin here follows the Prolog definition step by
step, so the modes agree too -- a partial list or an unbound argument
enumerates, as the Prolog clauses do::

    pairs_keys_values([], [], []).
    pairs_keys_values([A-B|ABs], [A|As], [B|Bs]) :-
            pairs_keys_values(ABs, As, Bs).
    pairs_keys(Ps, Ks) :- pairs_keys_values(Ps, Ks, _).
    pairs_values(Ps, Vs) :- pairs_keys_values(Ps, _, Vs).

    group_pairs_by_key([], []).
    group_pairs_by_key([K-V|KVs0], [K-[V|Vs]|KVs]) :-
            same_key(K, KVs0, Vs, KVs1),
            group_pairs_by_key(KVs1, KVs).
    same_key(K0, [K1-V|KVs0], [V|Vs], KVs) :-
            K0 == K1, !,
            same_key(K0, KVs0, Vs, KVs).
    same_key(_, KVs, [], KVs).

``group_pairs_by_key/2`` groups ADJACENT pairs whose keys are identical
(``==``); it does not sort.  ``[a-1, b-2, a-3]`` gives
``[a-[1], b-[2], a-[3]]``.  Sort by key first (``msort/2``) to group every
occurrence.
"""

from __future__ import annotations

from itertools import count

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE

from clausal.logic.builtins._registry import _trampoline_builtin

_BAD = object()


def _pair_cell(k, v):
    return ("-", k, v)


def _pair_parts(elem, trail):
    """``(Key, Value)`` of a pair, binding an unbound element to a fresh
    ``K-V`` cell (as a head ``[K-V|_]`` would), else None."""
    d = deref(elem)
    if is_var(d):
        k, v = Var(), Var()
        if not unify(d, _pair_cell(k, v), trail):
            return None
        return k, v
    if type(d) is tuple and len(d) == 3 and d[0] == "-":
        return d[1], d[2]
    from clausal.pythonic_ast.nodes import Sub  # noqa: PLC0415
    if type(d) is Sub:
        return d.left, d.right
    return None


def _unify_pair(target, key, val, trail):
    """Unify *target* with ``Key-Val`` in whichever spelling it already has
    (the cell, or a source ``k - v`` node); an unbound target gets the cell."""
    parts = _pair_parts(target, trail)
    return (parts is not None and unify(parts[0], key, trail)
            and unify(parts[1], val, trail))


def _cursor(x):
    """Split a list argument into ``(prefix_items, open_tail)``.

    ``open_tail`` is None for a proper list, or the unbound variable that
    ends a partial list (an unbound argument is ``([], itself)``).  Anything
    that cannot be a list is ``_BAD``."""
    d = deref(x)
    if is_var(d):
        return [], d
    from clausal.logic.builtins.lists import _as_items  # noqa: PLC0415
    from clausal.terms import ConcreteSeg, SegList, VarSeg  # noqa: PLC0415
    if isinstance(d, SegList):
        w = d._walk_raw()
        if isinstance(w, list):
            return w, None
        if not isinstance(w, SegList):
            return _BAD
        segs = w.segments
        items: list = []
        for seg in segs[:-1]:
            if not isinstance(seg, ConcreteSeg):
                return _BAD             # a hole in the middle: not a list shape
            items.extend(seg.elements)
        last = segs[-1] if segs else None
        if isinstance(last, VarSeg) and is_var(deref(last.var)):
            return items, deref(last.var)
        return _BAD
    items = _as_items(d)
    if items is None:
        return _BAD
    return list(items), None


def _cons(head, tail):
    """The partial list ``[Head|Tail]``."""
    from clausal.terms import ConcreteSeg, SegList, VarSeg  # noqa: PLC0415
    return SegList([ConcreteSeg([head]), VarSeg(tail)])


def _pkv_at(n, cursors, trail):
    """Unify the three lists of ``pairs_keys_values`` at length *n*.

    Walks position by position exactly as the recursive clause does, then
    closes each open tail with the remainder.  A pair it builds holds the
    key and value themselves (dereferenced), never a fresh variable bound to
    them, so the result reads back as plain data."""
    (p_items, p_tail), (k_items, k_tail), (v_items, v_tail) = cursors
    rest_p, rest_k, rest_v = [], [], []
    for i in range(n):
        key = deref(k_items[i]) if i < len(k_items) else Var()
        val = deref(v_items[i]) if i < len(v_items) else Var()
        if i < len(p_items):
            elem = deref(p_items[i])
            if is_var(elem):
                if not unify(elem, _pair_cell(key, val), trail):
                    return False
            else:
                parts = _pair_parts(elem, trail)
                if parts is None:
                    return False
                if not (unify(parts[0], key, trail)
                        and unify(parts[1], val, trail)):
                    return False
                key, val = deref(key), deref(val)
        else:
            rest_p.append(_pair_cell(key, val))
        if i >= len(k_items):
            rest_k.append(key)
        if i >= len(v_items):
            rest_v.append(val)
    for tail, rest in ((p_tail, rest_p), (k_tail, rest_k), (v_tail, rest_v)):
        if tail is not None and not unify(tail, rest, trail):
            return False
    return True


def _pairs_keys_values(pairs, keys, values, trail, _proceed):
    cursors = [_cursor(pairs), _cursor(keys), _cursor(values)]
    if any(c is _BAD for c in cursors):
        return
    closed = {len(items) for items, tail in cursors if tail is None}
    if len(closed) > 1:
        return
    lo = max(len(items) for items, _tail in cursors)
    if closed:
        n = closed.pop()
        if n < lo:
            return
        mark = trail.mark()
        if _pkv_at(n, cursors, trail):
            yield (_proceed, None)
        trail.undo(mark)
        return
    # Every argument is open: the Prolog definition enumerates lengths from
    # the longest prefix up.  Whether length n >= lo succeeds does not
    # depend on n (the extra positions are all fresh), so a failure at lo
    # is a failure everywhere -- stop rather than loop.
    for n in count(lo):
        mark = trail.mark()
        ok = _pkv_at(n, cursors, trail)
        if ok:
            yield (_proceed, None)
        trail.undo(mark)
        if not ok:
            return


@_trampoline_builtin("pairs_keys_values", 3)
def _pairs_keys_values__3(this_generator, _proceed, _fail, _catcher, pairs, keys, values, trail):
    """pairs_keys_values(Pairs, Keys, Values) -- Pairs is a list of Key-Value."""
    yield from _pairs_keys_values(pairs, keys, values, trail, _proceed)
    yield (_fail, DONE)


@_trampoline_builtin("pairs_keys", 2)
def _pairs_keys__2(this_generator, _proceed, _fail, _catcher, pairs, keys, trail):
    """pairs_keys(Pairs, Keys) -- the keys of a list of Key-Value pairs."""
    yield from _pairs_keys_values(pairs, keys, Var(), trail, _proceed)
    yield (_fail, DONE)


@_trampoline_builtin("pairs_values", 2)
def _pairs_values__2(this_generator, _proceed, _fail, _catcher, pairs, values, trail):
    """pairs_values(Pairs, Values) -- the values of a list of Key-Value pairs."""
    yield from _pairs_keys_values(pairs, Var(), values, trail, _proceed)
    yield (_fail, DONE)


def _group_plain(items, trail):
    """``group_pairs_by_key`` over a proper list with Groups unbound: the
    same walk as :func:`_group_pairs`, building ``[K-[V, ...], ...]``
    directly.  None when an element is not a pair."""
    from clausal.logic.builtins.iso_compare import _iso_identical  # noqa: PLC0415
    result: list = []
    last_key = _BAD
    for elem in items:
        parts = _pair_parts(elem, trail)
        if parts is None:
            return None
        key, val = deref(parts[0]), deref(parts[1])
        if result and _iso_identical(last_key, key):
            result[-1][2].append(val)
        else:
            result.append(("-", key, [val]))
            last_key = key
    return result


_DONE = object()


def _group_pairs(items, tail, groups, trail):
    """Run ``group_pairs_by_key`` over a pairs list given as *items* plus an
    open *tail* (None for a proper list).  Returns ``_BAD`` on failure,
    ``_DONE`` on success over a proper list, else the output tail still to
    be closed (and *tail* is then open)."""
    from clausal.logic.builtins.iso_compare import _iso_identical  # noqa: PLC0415
    out = groups
    i, n = 0, len(items)
    while i < n:
        parts = _pair_parts(items[i], trail)
        if parts is None:
            return _BAD
        key, val = parts
        vs, kvs, head = Var(), Var(), Var()
        if not (unify(out, _cons(head, kvs), trail)
                and _unify_pair(head, key, _cons(val, vs), trail)):
            return _BAD
        j = i + 1
        # same_key/4: extend the group while the next pair's key is
        # identical; the first clause's head and guard are undone on failure
        # and the second clause closes the group.  An element past the end of
        # a partial list is a fresh pair whose fresh key is never identical.
        while j < n:
            mark = trail.mark()
            nxt = _pair_parts(items[j], trail)
            vs1 = Var()
            if (nxt is not None and unify(vs, _cons(nxt[1], vs1), trail)
                    and _iso_identical(deref(key), deref(nxt[0]))):
                vs = vs1
                j += 1
                continue
            trail.undo(mark)
            break
        if not unify(vs, [], trail):
            return _BAD
        out = kvs
        i = j
    if tail is None:
        return _DONE if unify(out, [], trail) else _BAD
    return out


@_trampoline_builtin("group_pairs_by_key", 2)
def _group_pairs_by_key__2(this_generator, _proceed, _fail, _catcher, pairs, groups, trail):
    """group_pairs_by_key(Pairs, Groups) -- group ADJACENT Key-Value pairs
    with identical keys: ``[a-1, a-2, b-3]`` gives ``[a-[1, 2], b-[3]]``."""
    cur = _cursor(pairs)
    if cur is _BAD:
        yield (_fail, DONE)
        return
    items, tail = cur
    mark = trail.mark()
    if tail is None and is_var(deref(groups)):
        # The usual mode: build the answer as plain data and bind it once.
        result = _group_plain(items, trail)
        if result is not None and unify(groups, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
        yield (_fail, DONE)
        return
    out = _group_pairs(items, tail, groups, trail)
    if out is _DONE:
        yield (_proceed, None)
    elif out is not _BAD:
        # An open tail: the first clause ends the list here; the second adds
        # one more fresh pair, which is always a group of its own.  Groups
        # bounds the count: a proper list fixes it, a non-list refuses it.
        gcur = _cursor(out)
        if gcur is _BAD:
            counts = ()
        elif gcur[1] is None:
            counts = (len(gcur[0]),)
        else:
            counts = count(len(gcur[0]))
        for n in counts:
            inner = trail.mark()
            fresh = [(Var(), Var()) for _ in range(n)]
            if (unify(tail, [_pair_cell(k, v) for k, v in fresh], trail)
                    and unify(out, [_pair_cell(k, [v]) for k, v in fresh], trail)):
                yield (_proceed, None)
            trail.undo(inner)
    trail.undo(mark)
    yield (_fail, DONE)
