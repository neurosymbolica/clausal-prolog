"""C8 — Partial-term short-circuits.

6 findings (4 bug + 1 design-gap + 1 smell). Code paths that meet a
non-ground SegList/SegString either crash with bare TypeError or return
False/NotImplemented on logically-satisfiable goals — silent
incompleteness or untyped exceptions.

Findings tested here:
- F021 (bug) SegList sequence-protocol crashes on non-ground
- F022 (design-gap) SegList.__contains__ silent False on partial
- F023 (bug) SegString.__unify__(list) silent fail on non-ground
- F024 (smell) walk crashes on malformed SegString segments
- F038 (bug) _in_iter raises TypeError on ground SegString
- F039 (bug) _in_iter raises TypeError on non-ground SegList/SegString
"""

import pytest

from clausal.logic.atoms import char_atom
from clausal.logic.cells import chars


def test_F021_seglist_sequence_protocol_no_bare_typeerror():
    """`len(sl)`, `list(sl)`, and `sl[0]` on a non-ground SegList must
    not raise a bare TypeError.

    `SegList.__len__`, `__iter__`, and `__getitem__` (terms.py:334-351)
    all delegate to `self.to_list()`, which raises
    `TypeError("SegList is not ground: ...")` whenever the SegList has
    any unbound `VarSeg`. A duck-typed sequence caller gets a crash
    rather than a logically-meaningful answer or a typed clausal
    exception.

    Expected: either a defined partial answer (the ConcreteSeg prefix /
    known indices) or a typed clausal exception. The bare `TypeError`
    is a crash regardless of how informative its message is.
    """
    from clausal.logic.variables import Var
    from clausal.terms import SegList, VarSeg, ConcreteSeg

    X = Var()
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(X)])
    # Precondition: SegList must be non-ground (else the bug doesn't fire).
    assert not sl.is_ground(), (
        f"precondition: SegList([ConcreteSeg([1,2]), VarSeg(X)]) should "
        f"be non-ground; got is_ground={sl.is_ground()}"
    )

    # len(sl)
    try:
        n = len(sl)
    except TypeError as e:
        pytest.fail(
            f"len(non-ground SegList) raised bare TypeError: {e}. "
            f"Expected a partial answer (>= 2, the ConcreteSeg prefix) "
            f"or a typed clausal exception, not a sequence-protocol crash."
        )
    assert n >= 2, (
        f"len(sl) returned {n}; expected >= 2 (the ConcreteSeg prefix "
        f"contributes 2 known elements)."
    )

    # list(sl)
    try:
        items = list(sl)
    except TypeError as e:
        pytest.fail(
            f"list(non-ground SegList) raised bare TypeError: {e}. "
            f"Expected the concrete-prefix items [1, 2] or a typed "
            f"clausal exception."
        )
    assert items[:2] == [1, 2], (
        f"list(sl) returned {items!r}; expected the concrete prefix "
        f"[1, 2] at the front."
    )

    # sl[0]
    try:
        item = sl[0]
    except TypeError as e:
        pytest.fail(
            f"non-ground SegList[0] raised bare TypeError: {e}. "
            f"Expected the first ConcreteSeg element (1) or a typed "
            f"clausal exception."
        )
    assert item == 1, (
        f"sl[0] returned {item!r}; expected 1 (the first ConcreteSeg "
        f"element is knowable without resolving any VarSeg)."
    )


def test_F022_seglist_contains_silent_false_on_partial():
    """`elem in sl` for a partial SegList must not silently return False
    when `elem` could legitimately live in an unbound VarSeg.

    `SegList.__contains__` (terms.py:340-348) walks the segments and
    only checks `ConcreteSeg.elements`; it never considers whether a
    VarSeg's bound value contains the item. So
    ``3 in SegList([ConcreteSeg([1,2]), VarSeg(X), ConcreteSeg([4])])``
    returns `False` even though X could be bound to a list containing 3.

    Expected: either `True` (satisfiable membership), `None`
    (unknown), or a typed clausal exception. A definite `False` is a
    wrong answer in the partial-container case.
    """
    from clausal.logic.variables import Var
    from clausal.terms import SegList, VarSeg, ConcreteSeg

    X = Var()
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(X), ConcreteSeg([4])])
    # Precondition: non-ground.
    assert not sl.is_ground(), (
        f"precondition: SegList with VarSeg(X) should be non-ground; "
        f"got is_ground={sl.is_ground()}"
    )

    # Sanity-check the ConcreteSeg hits work (control).
    assert 1 in sl, (
        f"control: 1 should be reported as `in sl` via the first "
        f"ConcreteSeg; got {1 in sl}"
    )

    # The bug: 3 could be inside X, but __contains__ silently says False.
    result = 3 in sl
    assert result is not False, (
        f"`3 in sl` returned definite False on a partial container "
        f"where 3 could legitimately be inside the unbound VarSeg(X). "
        f"Expected True (satisfiable), None (unknown), or a typed "
        f"clausal exception — not silent False, which is a wrong answer."
    )


def test_F023_segstring_unify_list_non_ground():
    """`unify(SegString(["a", *X, "c"]), ["a","b","c"], t)` must not
    silently return False — the goal is logically satisfiable with
    X = ['b'] (or "b").

    `SegString.__unify__` (terms.py:551 onward) handles `list` only when
    the SegString is fully ground (walks to a `str`, then re-unifies
    that `str` against the list). When the SegString has any unbound
    VarSeg, the method returns `NotImplemented`, and the C top-level
    unify reads that as "no protocol match → False". The companion
    `SegList.__unify__(str)` *does* handle the non-ground case via
    `_seglist_unify_gen`; the SegString side has no twin path.

    Expected: `True` (route through a generator that splits the list and
    binds X to the inner slice). Silent `False` on a satisfiable goal
    is the C8 worst case.
    """
    from clausal.logic.variables import Var, unify, Trail
    from clausal.terms import SegString, VarSeg

    X = Var()
    ss = SegString(["a", VarSeg(X), "c"])
    # Precondition: non-ground (so we exercise the gap, not the ground branch).
    assert not ss.is_ground(), (
        f"precondition: SegString(['a', VarSeg(X), 'c']) should be "
        f"non-ground; got is_ground={ss.is_ground()}"
    )

    t = Trail()
    # THE FLIP (spec §6.2): a char list holds CHAR ATOMS.
    result = unify(ss, [char_atom(c) for c in "abc"], t)
    assert result is True, (
        f"unify(SegString(['a', VarSeg(X), 'c']), ['a','b','c']) "
        f"returned {result!r}; expected True (the goal is satisfiable "
        f"with X='b' or ['b']). SegString.__unify__(list) returns "
        f"NotImplemented in the non-ground case and the top-level "
        f"unify silently converts that to False — the symmetric "
        f"SegList<->str path (via _seglist_unify_gen) does handle this."
    )


def test_F024_segstring_walk_typed_exception_on_non_str_list_binding():
    """`SegString.__walk__()` on a SegString whose VarSeg is bound to a
    non-str list (e.g. ints) must raise a typed clausal exception, not
    a raw TypeError from inside `str.join`.

    `SegString.__walk__` (terms.py:475 onward, list-binding branch)
    joins the VarSeg's bound list via ``"".join(v)``. If a VarSeg's
    var was unified with `[1, 2, 3]`, the join raises bare
    `TypeError("sequence item 0: expected str instance, int found")`
    from deep inside CPython, propagating out of every method that
    touches `__walk__` (eq, hash, repr, unify, is_ground).

    Expected: a typed clausal exception ("SegString VarSeg bound to
    non-char-list") so callers can recover or surface a useful
    diagnostic. The bare TypeError from `str.join` leaks the
    implementation detail and is the C8 "malformed-segment" edge.
    """
    from clausal.logic.variables import Var, unify, Trail
    from clausal.terms import SegString, VarSeg

    Z = Var()
    t = Trail()
    unify(Z, [1, 2, 3], t)
    ss = SegString(["x", VarSeg(Z), "z"])

    try:
        walked = ss.__walk__()
    except TypeError as e:
        # The bare TypeError from str.join is exactly the smell we are
        # flagging. The xfail-strict marker means this branch *is* the
        # current behaviour — fix should replace with a typed clausal
        # exception.
        pytest.fail(
            f"SegString.__walk__() raised bare TypeError from str.join: "
            f"{e}. Expected a typed clausal exception identifying the "
            f"malformed VarSeg binding (non-char-list), not a leaked "
            f"CPython str.join error."
        )
    except Exception as e:
        # Any other exception is acceptable as long as it is not the
        # bare TypeError. If a typed clausal exception lands, this
        # branch is the post-fix happy path.
        # Sanity-check it has a clausal-ish identity.
        modname = type(e).__module__
        assert modname.startswith("clausal"), (
            f"SegString.__walk__() raised {type(e).__name__} from "
            f"module {modname}; expected a clausal-typed exception."
        )
        return

    # If it returned without raising, the result must at least not be
    # garbage — the malformed segment should not silently round-trip.
    pytest.fail(
        f"SegString.__walk__() on a non-char-list VarSeg binding "
        f"returned {walked!r}; expected a typed clausal exception "
        f"identifying the malformed segment (the binding [1,2,3] "
        f"violates the char-list contract)."
    )


def test_F038_in_iter_ground_segstring_no_bare_typeerror():
    """`_in_iter(SegString(["abc"]), pair_mode=False)` must not raise a
    bare TypeError — a ground SegString walks to a plain str and
    should iterate as chars (parallel to the ground SegList path).

    `_in_iter` (body_star_unify.py:208-217) returns `iter(collection)`
    for the non-DictTerm branch. `SegString` does not define
    `__iter__` and is not a `str` subclass (see F008), so even a
    trivially-ground `SegString(["abc"])` raises `TypeError:
    'SegString' object is not iterable` when used in a body-position
    `elem in coll` goal. The exception propagates out of the compiled
    body code.

    Expected: `['a', 'b', 'c']` (parallel to ground SegList, which
    defines `__iter__` → `to_list()`).
    """
    from clausal.logic.runtime.body_star_unify import _in_iter
    from clausal.terms import SegString

    ss = SegString(["abc"])
    # Precondition: ground SegString walks to plain str "abc".
    assert ss.is_ground() and ss.__walk__() == chars("abc"), (
        f"precondition: SegString(['abc']) ground+walks-to-'abc'; "
        f"got is_ground={ss.is_ground()}, walk={ss.__walk__()!r}"
    )

    try:
        items = list(_in_iter(ss, pair_mode=False))
    except TypeError as e:
        pytest.fail(
            f"_in_iter(ground SegString(['abc']), pair_mode=False) "
            f"raised bare TypeError: {e}. Expected ['a', 'b', 'c'] "
            f"(parallel to the ground SegList branch, which defines "
            f"__iter__ -> to_list()). SegString defines no __iter__ "
            f"and is not a str subclass, so iter(ss) fails."
        )

    # THE FLIP: iterating a string yields its CHAR ATOMS (Task 7
    # carry-forward: ``X in "abc"`` binds ``("a",)``).
    assert items == [char_atom(c) for c in "abc"], (
        f"_in_iter(ground SegString(['abc'])) yielded {items!r}; "
        f"expected the char ATOMS of 'abc'."
    )


def test_F039_in_iter_non_ground_no_bare_typeerror():
    """`_in_iter` on a non-ground SegList or SegString must not raise a
    bare TypeError — the concrete prefix is knowable and the goal is
    satisfiable for any prefix element without committing on the
    VarSeg holes.

    `_in_iter` (body_star_unify.py:208-217) calls `iter(collection)`
    unconditionally. For a non-ground SegList this dispatches through
    `SegList.__iter__` -> `to_list()` and raises `TypeError("SegList
    is not ground: ...")` (see F021). For a SegString it raises
    regardless of ground state (see F038). The body-position
    `elem in coll` goal has no way to defer or partially enumerate.

    Expected: enumerate the concrete prefix (1, 2, 5 for the SegList;
    'a', 'c' for the SegString) — or a typed clausal exception the
    caller can recover from. The bare TypeError is a crash.
    """
    from clausal.logic.variables import Var
    from clausal.logic.runtime.body_star_unify import _in_iter
    from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg

    # --- non-ground SegList ---
    sl = SegList([ConcreteSeg([1, 2]), VarSeg(Var()), ConcreteSeg([5])])
    assert not sl.is_ground(), (
        f"precondition: SegList with VarSeg should be non-ground; "
        f"got is_ground={sl.is_ground()}"
    )

    try:
        sl_items = list(_in_iter(sl, pair_mode=False))
    except TypeError as e:
        pytest.fail(
            f"_in_iter(non-ground SegList, pair_mode=False) raised "
            f"bare TypeError: {e}. Expected enumeration of the "
            f"concrete prefix [1, 2, ..., 5] (the VarSeg hole is "
            f"opaque but the surrounding ConcreteSeg elements are "
            f"knowable), or a typed clausal exception."
        )

    # Sanity-check we got at least the three knowable concrete elements.
    concrete = [x for x in sl_items if x in (1, 2, 5)]
    assert {1, 2, 5}.issubset(set(concrete)), (
        f"_in_iter(non-ground SegList) yielded {sl_items!r}; expected "
        f"the concrete prefix elements 1, 2, and 5 to be present."
    )

    # --- non-ground SegString ---
    ss = SegString(["a", VarSeg(Var()), "c"])
    assert not ss.is_ground(), (
        f"precondition: SegString with VarSeg should be non-ground; "
        f"got is_ground={ss.is_ground()}"
    )

    try:
        ss_items = list(_in_iter(ss, pair_mode=False))
    except TypeError as e:
        pytest.fail(
            f"_in_iter(non-ground SegString, pair_mode=False) raised "
            f"bare TypeError: {e}. Expected enumeration of the "
            f"concrete prefix ['a', ..., 'c'] (the VarSeg hole is "
            f"opaque but the surrounding chars are knowable), or a "
            f"typed clausal exception."
        )

    wanted = {char_atom("a"), char_atom("c")}
    concrete_chars = [c for c in ss_items if c in wanted]
    assert wanted.issubset(set(concrete_chars)), (
        f"_in_iter(non-ground SegString) yielded {ss_items!r}; "
        f"expected the concrete char ATOMS ('a',) and ('c',) to be present."
    )
