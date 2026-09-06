"""C5 — Hash/eq asymmetries between SegList and SegString.

3 findings (1 bug + 2 design-gap). The Python eq/hash invariant
(`a == b` implies `hash(a) == hash(b)` when both are hashable) is
violated by SegString in the non-ground case, and the two sibling
types have asymmetric __eq__ and __hash__ contracts.

Findings tested here:
- F017 (bug) SegString.__hash__ violates the Python eq/hash invariant
- F019 (design-gap) SegList vs SegString __eq__ asymmetry against str/list
- F025 (design-gap) SegList.__hash__ unconditional vs SegString.__hash__ conditional
"""

import pytest

from clausal.logic.atoms import char_atom, mint


def test_F017_segstring_unhashable():
    """SegString is *unconditionally* unhashable, matching Python's
    ``list`` parallel for SegList.

    Phase 2 Task 13 revision (user-confirmed Liskov contract):
    the previous Task 5 fix made SegString hashable when ground and
    structurally-hashable when non-ground; the new contract reverts
    that — both Seg* types are unhashable always, so the Python
    eq/hash invariant (``a == b ⇒ hash(a) == hash(b)`` when both are
    hashable) is trivially satisfied because no SegString instance is
    ever hashable.

    Callers who need a hashable form for a ground SegString convert
    via ``to_str()`` / ``str(...)`` first.
    """
    from clausal.logic.variables import Var
    from clausal.terms import SegString, VarSeg

    # Non-ground SegString — raises TypeError on hash.
    X = Var()
    ss = SegString(["a", VarSeg(X), "c"])
    with pytest.raises(TypeError, match="unhashable"):
        hash(ss)

    # Ground SegString — also raises TypeError (no special case).
    ground_ss = SegString(["abc"])
    with pytest.raises(TypeError, match="unhashable"):
        hash(ground_ss)

    # User-side workaround: convert via ``to_str()`` first.
    assert hash(ground_ss.to_str()) == hash("abc"), (
        "ground SegString can be hashed via to_str() conversion"
    )


def test_F019_seglist_segstring_eq_asymmetry():
    """SegList and SegString disagree about which container type to accept in __eq__.

    The two sibling types have an asymmetric equality contract:

    - SegList([...]) accepts list in __eq__, rejects str (returns NotImplemented).
    - SegString([...]) accepts str in __eq__, rejects list (returns NotImplemented).

    Under the strings-as-lists contract, these Seg* values are semantically
    interchangeable, so the equality answers should agree. Both should either
    accept both container types, or both reject the foreign container.

    This test asserts the FIX (symmetric behavior): both should agree on both
    container types. Today this assertion fails because the bug is present.
    """
    from clausal.terms import SegList, SegString, ConcreteSeg

    # THE FLIP (spec §6.2): a char is the ATOM ("a",); a list of 1-char
    # ``str`` values is a list of one-element STRINGS, a different term.
    chars = [char_atom(c) for c in "abc"]
    sl = SegList([ConcreteSeg(chars)])
    ss = SegString(["abc"])

    # Under the fix, both should accept both container types (symmetric).
    # Or both reject the foreign container. The key is: they should agree.

    # Expected symmetry: if sl == ["a","b","c"], then ss should also == ["a","b","c"].
    # And if ss == "abc", then sl should also == "abc".
    # Today this fails because of the asymmetry.

    assert (sl == "abc") == (ss == "abc"), (
        f"Symmetric fix: SegList.__eq__ and SegString.__eq__ should agree "
        f"on str containers. (sl == 'abc') is {sl == 'abc'}, "
        f"(ss == 'abc') is {ss == 'abc'}. These should be equal."
    )

    assert (sl == chars) == (ss == chars), (
        f"Symmetric fix: SegList.__eq__ and SegString.__eq__ should agree "
        f"on list containers. (sl == [...]) is {sl == chars}, "
        f"(ss == [...]) is {ss == chars}. These should be equal."
    )


def test_F025_seglist_segstring_hashability_asymmetry():
    """SegList and SegString have asymmetric hashability rules.

    SegList.__hash__ (terms.py:376-378) unconditionally raises TypeError,
    even when the SegList is ground (walks to a plain Python list).

    SegString.__hash__ (terms.py:589-591) is conditionally hashable: returns
    `hash(walked)` when ground, but `id(self)` when non-ground.

    This asymmetry mirrors list (unhashable) vs str (hashable) in Python's
    standard types — which is defensible — but it means ground SegLists
    cannot be used as dict/set keys, despite being conceptually immutable.

    This test asserts the FIX: both sibling types should share a symmetric
    rule. Either both hashable when ground and unhashable when non-ground,
    or both unconditionally unhashable.
    """
    from clausal.logic.variables import Var
    from clausal.terms import SegList, SegString, ConcreteSeg, VarSeg

    # Ground SegList: is_ground() is True.
    sl_ground = SegList([ConcreteSeg([char_atom(c) for c in "abc"])])
    assert sl_ground.is_ground(), (
        f"SegList([ConcreteSeg(['a','b','c'])]) should be ground. "
        f"is_ground() returned {sl_ground.is_ground()}"
    )

    # Ground SegString: is_ground() is True.
    ss_ground = SegString(["abc"])
    assert ss_ground.is_ground(), (
        f"SegString(['abc']) should be ground. "
        f"is_ground() returned {ss_ground.is_ground()}"
    )

    # Under the fix: both ground instances should have the same hashability.
    # Either both raise TypeError, or both succeed.
    sl_can_hash = True
    ss_can_hash = True

    try:
        hash(sl_ground)
        sl_can_hash = True
    except TypeError:
        sl_can_hash = False

    try:
        hash(ss_ground)
        ss_can_hash = True
    except TypeError:
        ss_can_hash = False

    assert sl_can_hash == ss_can_hash, (
        f"Symmetric fix: ground SegList and ground SegString should have the "
        f"same hashability. sl_ground.is_hashable: {sl_can_hash}, "
        f"ss_ground.is_hashable: {ss_can_hash}. These should be equal."
    )

    # Non-ground SegString: should follow same rule as SegList.
    X = Var()
    ss_nonground = SegString(["a", VarSeg(X), "c"])
    assert not ss_nonground.is_ground(), (
        f"SegString(['a', VarSeg(X), 'c']) should not be ground. "
        f"is_ground() returned {ss_nonground.is_ground()}"
    )

    # If the fix is "both unhashable unconditionally", non-ground SegString
    # should also be unhashable. If the fix is "hashable when ground, unhashable
    # when non-ground", non-ground should raise.
    ng_can_hash = True
    try:
        hash(ss_nonground)
        ng_can_hash = True
    except TypeError:
        ng_can_hash = False

    assert ng_can_hash == sl_can_hash, (
        f"Symmetric fix: non-ground SegString should follow the same "
        f"hashability rule as SegList. ng_ss.is_hashable: {ng_can_hash}, "
        f"sl_ground.is_hashable: {sl_can_hash}. These should be equal."
    )
