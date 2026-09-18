"""C2 — Non-deterministic SegList/SegString unification collapsed to first split.

2 bug findings. Each test asserts the unification entry point exposes
ALL valid splits (not just the first), so backtracking can find them.

Findings tested here:
- F015 SegList.__unify__ returns only the first valid split
- F016 SegString.__unify__ returns only the first valid split
"""

def test_F015_seglist_unify_enumerates_all_splits():
    """`SegList([*A, *B]) = [1, 2, 3]` should expose all four splits via the
    unify entry point, not just the first.

    The underlying generator `_seglist_unify_gen` already enumerates all
    splits correctly (control assertion below). The bug is in the
    `SegList.__unify__` consumer: it uses `for _ in gen: return True`,
    committing to the first split and providing no protocol hook for
    backtracking to the others.

    Adversarial assertion: re-driving `unify` after `trail.undo(mark)`
    should be able to surface the other splits. Today every re-drive lands
    on the same first split because the entry point exposes no choice
    point — so only 1 distinct (A, B) pair is reachable instead of 4.
    """
    from clausal.logic.variables import Var, unify, Trail, deref
    from clausal.terms import SegList, VarSeg, _seglist_unify_gen

    # Control: the generator itself enumerates all 4 splits — proving the
    # underlying logic is correct and the bug is purely in the consumer.
    A_ctl, B_ctl = Var(), Var()
    sl_ctl = SegList([VarSeg(A_ctl), VarSeg(B_ctl)])
    t_ctl = Trail()
    gen_split_count = sum(
        1 for _ in _seglist_unify_gen(sl_ctl, [1, 2, 3], t_ctl)
    )
    assert gen_split_count == 4, (
        f"control: _seglist_unify_gen should yield 4 splits for "
        f"[*A,*B] = [1,2,3]; got {gen_split_count}. If this fails, the "
        f"bug is not where F015 claims — re-check the ledger entry."
    )

    # Adversarial: drive the unify entry point repeatedly. A correct
    # non-det protocol would expose all 4 splits; today every drive lands
    # on the same first split.
    A, B = Var(), Var()
    sl = SegList([VarSeg(A), VarSeg(B)])
    t = Trail()
    splits_seen = set()
    for _ in range(4):
        mark = t.mark()
        if unify(sl, [1, 2, 3], t):
            a_val = deref(A)
            b_val = deref(B)
            # Lists aren't hashable; canonicalise to tuples for set membership.
            splits_seen.add((tuple(a_val), tuple(b_val)))
        t.undo(mark)

    expected = {
        ((), (1, 2, 3)),
        ((1,), (2, 3)),
        ((1, 2), (3,)),
        ((1, 2, 3), ()),
    }
    assert splits_seen == expected, (
        f"SegList.__unify__ should expose all 4 splits of "
        f"[*A,*B] = [1,2,3] via the protocol, got {len(splits_seen)} "
        f"distinct split(s): {sorted(splits_seen)!r}. The generator "
        f"yields {gen_split_count} splits internally; the bug is that "
        f"__unify__'s `for _ in gen: return True` collapses them to one."
    )


def test_F016_segstring_unify_enumerates_all_splits():
    """`SegString([*A, *B]) = "abc"` should expose all four splits via the
    unify entry point, not just the first.

    Mirror of F015 for SegString. The underlying generator
    `_segstring_unify_gen` enumerates all 4 splits correctly (control
    assertion below); `SegString.__unify__` uses the same
    `for _ in gen: return True` pattern and surfaces only the first
    (A="", B="abc"), with no protocol hook for the other three.
    """
    from clausal.logic.variables import Var, unify, Trail, deref
    from clausal.terms import SegString, VarSeg, _segstring_unify_gen
    from clausal.logic.cells import chars

    # Control: the generator itself enumerates all 4 splits.
    A_ctl, B_ctl = Var(), Var()
    ss_ctl = SegString([VarSeg(A_ctl), VarSeg(B_ctl)])
    t_ctl = Trail()
    gen_split_count = sum(
        1 for _ in _segstring_unify_gen(ss_ctl, "abc", t_ctl)
    )
    assert gen_split_count == 4, (
        f"control: _segstring_unify_gen should yield 4 splits for "
        f"[*A,*B] = 'abc'; got {gen_split_count}. If this fails, the "
        f"bug is not where F016 claims — re-check the ledger entry."
    )

    # Adversarial: drive the unify entry point repeatedly. A correct
    # non-det protocol would expose all 4 splits; today every drive lands
    # on the same first split (A="", B="abc").
    A, B = Var(), Var()
    ss = SegString([VarSeg(A), VarSeg(B)])
    t = Trail()
    splits_seen = set()
    for _ in range(4):
        mark = t.mark()
        if unify(ss, chars("abc"), t):
            splits_seen.add((deref(A), deref(B)))
        t.undo(mark)

    expected = {
        (chars(""), chars("abc")),
        (chars("a"), chars("bc")),
        (chars("ab"), chars("c")),
        (chars("abc"), chars("")),
    }
    assert splits_seen == expected, (
        f"SegString.__unify__ should expose all 4 splits of "
        f"[*A,*B] = 'abc' via the protocol, got {len(splits_seen)} "
        f"distinct split(s): {sorted(splits_seen)!r}. The generator "
        f"yields {gen_split_count} splits internally; the bug is that "
        f"__unify__'s `for _ in gen: return True` collapses them to one."
    )
