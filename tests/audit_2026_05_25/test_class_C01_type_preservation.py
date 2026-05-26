"""C1 — Type preservation across the str<->list boundary.

5 design-gap findings. Each test asserts the strings-as-lists contract:
an operation that consumes a `str` should return a `str` (or vice versa)
when the contract demands it — not a `list`.

Findings tested here:
- F018 SegList.__walk__ expands VarSeg-bound str into char list
- F020 SegList.__add__ / __radd__ rejects str
- F033 _head_list_unify_output always builds a list, never a str
       (lock-in test exists in tests/test_seglist_creation.py)
- F042 _body_multi_star_unify unbound-target branch always builds SegList
       (lock-in test exists in tests/test_seglist_creation.py)
- F043 _build_star_list / _build_multi_star_list lose str type for
       list-of-chars and non-ground SegString stars

All tests are xfail(strict=True): a passing test means the fix landed
(remove the marker) or the test is wrong (re-check the ledger entry).
"""

import pytest


@pytest.mark.xfail(
    strict=True,
    reason="ledger F018: SegList.__walk__ expands VarSeg-bound str into char list",
)
def test_F018_seglist_walk_preserves_str_binding():
    """SegList.__walk__ should preserve the str-ness of a VarSeg binding.

    Under the strings-as-lists "input-type wins" contract, walking a
    SegList that contains a VarSeg bound to "abc" should not silently
    expand the string into individual characters and inline them into
    the surrounding ConcreteSegs. The reproducer below currently yields
    ``[1, 'a', 'b', 'c', 2]`` — the str 'abc' has been atomized.
    """
    from clausal.logic.variables import Var, unify, Trail
    from clausal.terms import SegList, VarSeg, ConcreteSeg

    X = Var()
    unify(X, "abc", Trail())
    sl = SegList([ConcreteSeg([1]), VarSeg(X), ConcreteSeg([2])])
    walked = sl.__walk__()

    # Expected: the str 'abc' survives as a single element rather than
    # being expanded inline to chars.
    assert "abc" in walked, (
        f"expected the str 'abc' to survive in the walked SegList "
        f"(no inline char expansion), got {walked!r} "
        f"(type={type(walked).__name__})"
    )
    assert walked != [1, "a", "b", "c", 2], (
        f"walked SegList should not have inline-expanded 'abc' into "
        f"chars; got {walked!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="ledger F020: SegList.__add__ / __radd__ rejects str",
)
def test_F020_seglist_add_accepts_str():
    """SegList + str and str + SegList should both succeed.

    Under the strings-as-lists contract a str is interchangeable with a
    list-of-1-char-strs as a SegList tail. Currently both
    ``SegList(['a','b']) + 'cd'`` and ``'cd' + SegList(['a','b'])`` raise
    TypeError because __add__ NotImplements on str and __radd__ only
    handles list.
    """
    from clausal.terms import SegList, ConcreteSeg

    sl = SegList([ConcreteSeg(["a", "b"])])

    # Control: SegList + list works today.
    assert sl + ["c", "d"] == ["a", "b", "c", "d"]

    # Contract: SegList + str should also work.
    try:
        forward = sl + "cd"
    except TypeError as e:
        pytest.fail(
            f"SegList + str raised TypeError ({e!r}); expected it to "
            f"succeed under the strings-as-lists contract"
        )
    try:
        backward = "cd" + sl
    except TypeError as e:
        pytest.fail(
            f"str + SegList raised TypeError ({e!r}); expected it to "
            f"succeed under the strings-as-lists contract"
        )

    # Both directions should yield the concatenation in the natural order.
    assert forward == ["a", "b", "c", "d"], (
        f"SegList + 'cd' expected to equal ['a','b','c','d'], got {forward!r}"
    )
    assert backward == ["c", "d", "a", "b"], (
        f"'cd' + SegList expected to equal ['c','d','a','b'], got {backward!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ledger F033: _head_list_unify_output always builds a list, never "
        "a str (lock-in test exists in tests/test_seglist_creation.py)"
    ),
)
def test_F033_head_list_unify_output_preserves_str():
    """When all bindings are str-typed, output-mode reconstruction should
    yield a str, not a list.

    A clause ``foo([H, *T])`` whose body proves ``H='h'`` and
    ``T='ello'`` should reconstruct the target to ``'hello'`` (a str),
    not to ``['h', 'ello']`` (a list). The output-mode helper currently
    unconditionally allocates a list because the deferred-output target's
    original logical type is not recorded.
    """
    from clausal.logic.variables import Var, unify, Trail, deref
    from clausal.logic.runtime.list_unify import _head_list_unify_output

    target = Var()
    H, T = Var(), Var()
    unify(H, "h", Trail())
    unify(T, "ello", Trail())  # str-typed tail
    _head_list_unify_output(target, [H], T, [], Trail())

    bound = deref(target)
    assert bound == "hello", (
        f"expected target bound to str 'hello' (str-preserving output "
        f"mode), got {bound!r} (type={type(bound).__name__})"
    )
    assert isinstance(bound, str), (
        f"expected target type str, got {type(bound).__name__}: {bound!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ledger F042: _body_multi_star_unify unbound-target branch always "
        "builds SegList (lock-in test exists in tests/test_seglist_creation.py)"
    ),
)
def test_F042_body_multi_star_unify_builds_segstring_for_str_context():
    """For an unbound target in a str-typed context, the multi-star body
    helper should build a SegString, not a SegList.

    Currently the unbound-target branch unconditionally constructs a
    SegList of [VarSeg | ConcreteSeg] segments regardless of the
    surrounding logical context. Under the "input type wins" contract a
    str-typed context should produce a SegString.

    Inspect the binding *during* the yield — the generator's trail.undo
    unbinds after each yield, so consuming the full generator would lose
    the binding.
    """
    from clausal.logic.variables import Var, Trail, deref
    from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
    from clausal.terms import SegList, SegString

    target = Var()
    H, S, R = Var(), Var(), Var()
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]

    bound = None
    for _ in _body_multi_star_unify(target, segments, Trail()):
        bound = deref(target)
        break

    assert bound is not None, "expected at least one yield from _body_multi_star_unify"
    assert isinstance(bound, SegString), (
        f"expected target bound to a SegString (str-typed context), got "
        f"{type(bound).__name__}: {bound!r}"
    )
    assert not isinstance(bound, SegList) or isinstance(bound, SegString), (
        f"expected non-SegList shape; got SegList: {bound!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ledger F043: _build_star_list / _build_multi_star_list lose str "
        "type for list-of-chars and non-ground SegString stars"
    ),
)
def test_F043_build_star_list_preserves_str_for_list_of_chars():
    """_build_star_list and _build_multi_star_list should re-promote a
    list-of-1-char-strs star to a str, and preserve SegString container
    identity for non-ground SegString stars.

    Currently both helpers only preserve str when the deref'd star is
    itself a str (or a ground SegString that walks to a str). A star
    bound to ``['e','l','l','o']`` — semantically equivalent to ``'ello'``
    under the strings-as-lists contract — falls into the list branch and
    is never re-promoted. A non-ground SegString star is demoted to a
    SegList, losing both the SegString container and the str-typing for
    the known concrete-string segments.
    """
    from clausal.logic.variables import Var, unify, Trail
    from clausal.logic.runtime.body_star_unify import (
        _build_star_list,
        _build_multi_star_list,
    )
    from clausal.terms import SegString, VarSeg

    # _build_star_list with star bound to a list-of-1-char-strs.
    X = Var()
    unify(X, ["e", "l", "l", "o"], Trail())
    r1 = _build_star_list(["h"], X, [])
    assert r1 == "hello", (
        f"_build_star_list with list-of-chars star: expected str 'hello', "
        f"got {r1!r} (type={type(r1).__name__})"
    )
    assert isinstance(r1, str), (
        f"_build_star_list with list-of-chars star: expected type str, "
        f"got {type(r1).__name__}: {r1!r}"
    )

    # _build_multi_star_list with star bound to a list-of-1-char-strs.
    Z = Var()
    unify(Z, ["e", "l", "l", "o"], Trail())
    r2 = _build_multi_star_list([("fixed", ["h"]), ("star", Z)])
    assert r2 == "hello", (
        f"_build_multi_star_list with list-of-chars star: expected str "
        f"'hello', got {r2!r} (type={type(r2).__name__})"
    )
    assert isinstance(r2, str), (
        f"_build_multi_star_list with list-of-chars star: expected type "
        f"str, got {type(r2).__name__}: {r2!r}"
    )

    # _build_multi_star_list with star bound to a non-ground SegString —
    # should rebuild as a SegString, not demote to SegList.
    W = Var()
    Inner = Var()
    unify(W, SegString(["el", VarSeg(Inner), "o"]), Trail())
    r3 = _build_multi_star_list([("fixed", ["h"]), ("star", W)])
    assert isinstance(r3, SegString), (
        f"_build_multi_star_list with non-ground SegString star: expected "
        f"a SegString container (prefix 'hel', var hole, suffix 'o'), got "
        f"{type(r3).__name__}: {r3!r}"
    )
