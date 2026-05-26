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


def test_F017_segstring_hash_invariant_violation():
    """Two structurally-equal non-ground SegStrings must have equal hashes.

    The Python data-model contract: if `a == b`, then `hash(a) == hash(b)`
    (when both are hashable). This invariant is violated by SegString in
    the non-ground case.

    SegString.__eq__ (terms.py:581-587) compares `_segments` lists
    structurally, so two non-ground SegStrings built from the same
    segments (same Var objects, same string literals) will compare equal.

    SegString.__hash__ (terms.py:589-591) returns `hash(walked)` when
    ground but `id(self)` when non-ground. For non-ground SegStrings,
    each instance gets its own id-based hash — distinct hashes for equal
    values, breaking the invariant.

    Concrete effect: identical non-ground SegStrings become distinct keys
    in a dict or set, silently duplicating values in memoisation and
    tabling contexts.
    """
    from clausal.logic.variables import Var
    from clausal.terms import SegString, VarSeg

    X = Var()
    ss1 = SegString(["a", VarSeg(X), "c"])
    ss2 = SegString(["a", VarSeg(X), "c"])

    # The two SegStrings are structurally equal.
    assert ss1 == ss2, (
        f"ss1 and ss2 have identical _segments; __eq__ should return True. "
        f"ss1 == ss2: {ss1 == ss2}"
    )

    # For equal values, hash must be equal (Python invariant).
    h1, h2 = hash(ss1), hash(ss2)
    assert h1 == h2, (
        f"ss1 == ss2, therefore hash(ss1) must equal hash(ss2). "
        f"Got hash(ss1)={h1}, hash(ss2)={h2}. "
        f"This breaks the Python eq/hash invariant."
    )

    # Consequence: both can be used as dict keys without duplication.
    d = {ss1: 1, ss2: 2}
    assert len(d) == 1, (
        f"Equal SegStrings must produce the same dict key. "
        f"Got len({{ss1: 1, ss2: 2}}) = {len(d)}, expected 1. "
        f"The duplicate key indicates hash(ss1) != hash(ss2) despite ss1 == ss2."
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

    sl = SegList([ConcreteSeg(["a", "b", "c"])])
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

    assert (sl == ["a", "b", "c"]) == (ss == ["a", "b", "c"]), (
        f"Symmetric fix: SegList.__eq__ and SegString.__eq__ should agree "
        f"on list containers. (sl == [...]) is {sl == ['a','b','c']}, "
        f"(ss == [...]) is {ss == ['a','b','c']}. These should be equal."
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
    sl_ground = SegList([ConcreteSeg(["a", "b", "c"])])
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
