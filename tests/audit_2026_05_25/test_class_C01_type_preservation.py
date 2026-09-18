"""C1 — Type preservation across the str<->list boundary.

5 design-gap findings. Each test asserts the user-confirmed
strings-as-lists Liskov rule: a list is the default output type;
``str`` is produced only when the result is *provably* a list of
all 1-char strs (i.e. ``maybe_promote_to_str`` semantics in
``_seg_helpers.py``). The promotion is purely a property of the
result elements — no upstream type-source plumbing is required.

Findings tested here:
- F018 SegList.__walk__ promotes all-1-char-str list to str
- F020 SegList.__add__ / __radd__ accepts str (Liskov substitution)
- F033 _head_list_unify_output promotes list-of-1-char-strs to str
- F042 _body_multi_star_unify promotes to str when provable
- F043 _build_star_list / _build_multi_star_list promote list-of-chars
       to str, preserve SegString for non-ground SegString stars
"""

import pytest

from clausal.logic.atoms import char_atom
from clausal.logic.cells import chars, is_chars


def test_F018_seglist_walk_promotes_all_char_str_to_str():
    """Under the user-confirmed Liskov "strings-as-lists" rule,
    SegList.__walk__ should promote a fully-ground walked list to a
    plain ``str`` when every element is a 1-char ``str`` — and keep the
    default list shape otherwise.

    VarSeg's splat semantics still expand a bound ``str`` into chars
    (str ⊂ list-of-chars), but at the end of the walk the helper
    applies ``maybe_promote_to_str``: a list of all 1-char strs becomes
    the equivalent str; a mixed list (or any non-char element) stays
    as a list.

    F018 fix: walking ``SegList([ConcreteSeg(['h']), VarSeg(X→'ello')])``
    used to yield ``['h','e','l','l','o']`` (list) and now yields
    ``'hello'`` (str) — the elements are *provably* all 1-char strs so
    the promote rule fires. A list containing non-char elements (e.g.
    ints) stays as a list because the rule cannot prove a str upgrade.
    """
    from clausal.logic.variables import Var, unify, Trail
    from clausal.terms import SegList, VarSeg, ConcreteSeg

    # Case A: walk yields all-1-char-str list → promote to str.
    X = Var()
    unify(X, chars("ello"), Trail())
    sl = SegList([ConcreteSeg([char_atom("h")]), VarSeg(X)])
    walked = sl.__walk__()
    assert walked == chars("hello"), (
        f"all-1-char-str walked list should promote to str 'hello', "
        f"got {walked!r} (type={type(walked).__name__})"
    )
    assert is_chars(walked), (
        f"expected str, got {type(walked).__name__}: {walked!r}"
    )

    # Case B: walk yields mixed list (ints + strs) → stays as list.
    Y = Var()
    unify(Y, chars("abc"), Trail())
    sl2 = SegList([ConcreteSeg([1]), VarSeg(Y), ConcreteSeg([2])])
    walked2 = sl2.__walk__()
    assert isinstance(walked2, list), (
        f"mixed-type walked list should stay as list (no provable "
        f"str promotion), got {type(walked2).__name__}: {walked2!r}"
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

    sl = SegList([ConcreteSeg([char_atom("a"), char_atom("b")])])

    # Control: SegList + list works today.
    abcd = [char_atom(c) for c in "abcd"]
    assert sl + [char_atom("c"), char_atom("d")] == abcd

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
    assert forward == abcd, (
        f"SegList + 'cd' expected to equal the char-atom list of 'abcd', "
        f"got {forward!r}"
    )
    assert backward == [char_atom(c) for c in "cdab"], (
        f"'cd' + SegList expected to equal the char-atom list of 'cdab', "
        f"got {backward!r}"
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
    unify(H, char_atom("h"), Trail())
    unify(T, chars("ello"), Trail())  # str-typed tail
    _head_list_unify_output(target, [H], T, [], Trail())

    bound = deref(target)
    assert bound == chars("hello"), (
        f"expected target bound to str 'hello' (str-preserving output "
        f"mode), got {bound!r} (type={type(bound).__name__})"
    )
    assert is_chars(bound), (
        f"expected target type str, got {type(bound).__name__}: {bound!r}"
    )


def test_F042_body_multi_star_unify_promotes_str_when_provable():
    """Under the user-confirmed Liskov "strings-as-lists" rule, the
    multi-star body helper default-builds a SegList for an unbound
    target, and promotes to a plain ``str`` (or rebuilds as a SegString
    for non-ground bindings) only when the result is *provably*
    str-compatible — every fixed element is a 1-char str and every
    star derefs to a str / SegString / list-of-1-char-strs.

    Default is list. Upgrade to str only when provable from result
    elements; no type-source plumbing required.
    """
    from clausal.logic.variables import Var, Trail, deref, unify
    from clausal.logic.runtime.body_star_unify import _body_multi_star_unify
    from clausal.terms import SegList, SegString

    # Case 1: all fixed elements bound to 1-char strs, star bound to a
    # str — result should be a plain str (provable from elements).
    target = Var()
    H, S, R = Var(), Var(), Var()
    trail = Trail()
    unify(H, char_atom("h"), trail)
    unify(S, chars("ell"), trail)
    unify(R, char_atom("o"), trail)
    segments = [("fixed", [H]), ("star", S), ("fixed", [R])]

    bound = None
    for _ in _body_multi_star_unify(target, segments, trail):
        bound = deref(target)
        break
    assert bound is not None, "expected at least one yield"
    assert bound == chars("hello"), (
        f"expected target bound to str 'hello' (all elements provably "
        f"1-char-strs / str), got {bound!r} (type={type(bound).__name__})"
    )
    assert is_chars(bound), (
        f"expected type str (provable promote), got {type(bound).__name__}"
    )

    # Case 2: vars unbound — default is SegList (no promotion possible
    # because we cannot prove the result will be all 1-char strs).
    target2 = Var()
    H2, S2, R2 = Var(), Var(), Var()
    segments2 = [("fixed", [H2]), ("star", S2), ("fixed", [R2])]
    bound2 = None
    for _ in _body_multi_star_unify(target2, segments2, Trail()):
        bound2 = deref(target2)
        break
    assert bound2 is not None, "expected at least one yield from case 2"
    assert isinstance(bound2, SegList), (
        f"unbound-var multi-star: default output is SegList (no provable "
        f"promotion), got {type(bound2).__name__}: {bound2!r}"
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
    unify(X, [char_atom(c) for c in "ello"], Trail())
    r1 = _build_star_list([char_atom("h")], X, [])
    assert r1 == chars("hello"), (
        f"_build_star_list with list-of-chars star: expected str 'hello', "
        f"got {r1!r} (type={type(r1).__name__})"
    )
    assert is_chars(r1), (
        f"_build_star_list with list-of-chars star: expected type str, "
        f"got {type(r1).__name__}: {r1!r}"
    )

    # _build_multi_star_list with star bound to a list-of-1-char-strs.
    Z = Var()
    unify(Z, [char_atom(c) for c in "ello"], Trail())
    r2 = _build_multi_star_list([("fixed", [char_atom("h")]), ("star", Z)])
    assert r2 == chars("hello"), (
        f"_build_multi_star_list with list-of-chars star: expected str "
        f"'hello', got {r2!r} (type={type(r2).__name__})"
    )
    assert is_chars(r2), (
        f"_build_multi_star_list with list-of-chars star: expected type "
        f"str, got {type(r2).__name__}: {r2!r}"
    )

    # _build_multi_star_list with star bound to a non-ground SegString —
    # should rebuild as a SegString, not demote to SegList.
    W = Var()
    Inner = Var()
    unify(W, SegString(["el", VarSeg(Inner), "o"]), Trail())
    r3 = _build_multi_star_list([("fixed", [char_atom("h")]), ("star", W)])
    assert isinstance(r3, SegString), (
        f"_build_multi_star_list with non-ground SegString star: expected "
        f"a SegString container (prefix 'hel', var hole, suffix 'o'), got "
        f"{type(r3).__name__}: {r3!r}"
    )
