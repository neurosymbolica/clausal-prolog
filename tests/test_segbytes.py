import pytest

from clausal.terms import SegBytes, VarSeg, PartialTermError, _segbytes_unify_gen
from clausal.logic.variables import Var, Trail, unify, deref


class TestSegBytesConstruction:
    def test_accepts_bytes_and_varseg(self):
        # nv
        SegBytes([b"GET", VarSeg(Var())])

    def test_rejects_str_segment(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes(["GET", VarSeg(Var())])

    def test_rejects_int_segment(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes([71, VarSeg(Var())])


class TestSegBytesWalk:
    def test_ground_returns_bytes(self):
        # nv
        assert SegBytes([b"hello"]).__walk__() == b"hello"

    def test_ground_returns_bytes_type(self):
        # nv
        assert type(SegBytes([b"hello"]).__walk__()) is bytes

    def test_adjacent_bytes_merge(self):
        # nv
        assert SegBytes([b"hel", b"lo"]).__walk__() == b"hello"

    def test_empty_returns_empty_bytes(self):
        # nv
        assert SegBytes([]).__walk__() == b""

    def test_bound_varseg_to_bytes_collapses(self):
        # nv
        trail = Trail()
        X = Var()
        unify(X, b"lo wor", trail)
        ss = SegBytes([b"hel", VarSeg(X), b"ld"])
        assert ss.__walk__() == b"hello world"

    def test_bound_varseg_to_intlist_joins_to_bytes(self):
        # nv  — VarSeg bound to int-codes joins back to bytes
        trail = Trail()
        X = Var()
        unify(X, [108, 111], trail)  # b"lo"
        ss = SegBytes([b"hel", VarSeg(X)])
        assert ss.__walk__() == b"hello"

    def test_varseg_bound_to_out_of_range_int_raises(self):
        # nv
        trail = Trail()
        X = Var()
        unify(X, [256], trail)
        with pytest.raises(PartialTermError):
            SegBytes([b"a", VarSeg(X)]).__walk__()

    def test_non_ground_returns_segbytes(self):
        # nv
        ss = SegBytes([b"hel", VarSeg(Var())])
        w = ss.__walk__()
        assert isinstance(w, SegBytes)


class TestSegBytesConcretePrefix:
    def test_ground(self):
        # nv
        prefix, has_var = SegBytes([b"abc"])._concrete_prefix()
        assert prefix == b"abc" and has_var is False

    def test_non_ground(self):
        # nv
        prefix, has_var = SegBytes([b"ab", VarSeg(Var()), b"cd"])._concrete_prefix()
        assert prefix == b"abcd" and has_var is True


class TestSegBytesUnifyAgainstBytes:
    def test_ground_equal(self):
        # nv
        assert SegBytes([b"hello"]).__unify__(b"hello", Trail()) is True

    def test_ground_unequal(self):
        # nv
        assert SegBytes([b"hello"]).__unify__(b"world", Trail()) is False

    def test_prefix_peel(self):
        # nv  — SegBytes([b"GET", VarSeg(Rest)]) vs b"GET /" binds Rest=b" /"
        trail = Trail()
        Rest = Var()
        ss = SegBytes([b"GET", VarSeg(Rest)])
        assert ss.__unify__(b"GET /", trail) is True
        assert deref(Rest) == b" /"

    def test_varseg_binds_to_bytes_not_intlist(self):
        # nv  — the bound value must be a bytes object, not an int-list
        trail = Trail()
        Rest = Var()
        SegBytes([b"GET", VarSeg(Rest)]).__unify__(b"GET /", trail)
        assert type(deref(Rest)) is bytes

    def test_two_varseg_multiple_splits(self):
        # nv
        trail = Trail()
        A, B = Var(), Var()
        ss = SegBytes([VarSeg(A), b",", VarSeg(B)])
        walked = ss.__walk__()
        solutions = []
        for _ in _segbytes_unify_gen(walked, b"a,b,c", trail):
            solutions.append((deref(A), deref(B)))
        assert (b"a", b"b,c") in solutions
        assert (b"a,b", b"c") in solutions
        assert len(solutions) == 2

    def test_too_short_fails(self):
        # nv
        assert SegBytes([b"hello", VarSeg(Var())]).__unify__(b"hi", Trail()) is False


class TestSegBytesUnifyAgainstList:
    def test_non_ground_against_intlist(self):
        # nv  — SegBytes([b"ab", VarSeg(Rest)]) vs [97,98,99] binds Rest=[99]
        trail = Trail()
        Rest = Var()
        ss = SegBytes([b"ab", VarSeg(Rest)])
        assert ss.__unify__([97, 98, 99], trail) is True
        assert deref(Rest) == [99]

    def test_against_segbytes_notimplemented(self):
        # nv
        ss = SegBytes([b"a", VarSeg(Var())])
        assert ss.__unify__(SegBytes([b"a"]), Trail()) is NotImplemented


class TestSegBytesEqHash:
    def test_eq_structural(self):
        # nv
        assert SegBytes([b"a"]) == SegBytes([b"a"])

    def test_eq_ground_bytes(self):
        # nv
        assert SegBytes([b"ab", b"c"]) == b"abc"

    def test_eq_intlist(self):
        # nv  — codes-model: SegBytes(b"abc") == [97,98,99]
        assert SegBytes([b"abc"]) == [97, 98, 99]

    def test_neq_out_of_range_intlist(self):
        # nv
        assert SegBytes([b"abc"]) != [97, 98, 999]

    def test_unhashable(self):
        # nv
        with pytest.raises(TypeError):
            hash(SegBytes([b"a"]))


class TestSegBytesSequence:
    def test_iter_yields_ints(self):
        # nv  — list(SegBytes(b"abc")) == [97,98,99], honouring list(b"abc")
        assert list(SegBytes([b"abc"])) == [97, 98, 99]

    def test_len_ground(self):
        # nv
        assert len(SegBytes([b"abc"])) == 3

    def test_len_concrete_prefix(self):
        # nv
        assert len(SegBytes([b"ab", VarSeg(Var())])) == 2

    def test_contains_int(self):
        # nv
        assert 97 in SegBytes([b"abc"])

    def test_getitem_ground_is_int(self):
        # nv
        assert SegBytes([b"abc"])[0] == 97

    def test_getitem_past_prefix_raises(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes([b"ab", VarSeg(Var())])[5]


from clausal.logic.runtime._seg_helpers import (
    maybe_promote_to_bytes, normalize_seg_input,
)


class TestMaybePromoteToBytes:
    def test_promotes_int_list(self):
        # nv
        assert maybe_promote_to_bytes([97, 98, 99]) == b"abc"
        assert type(maybe_promote_to_bytes([97, 98, 99])) is bytes

    def test_leaves_out_of_range(self):
        # nv
        assert maybe_promote_to_bytes([97, 256]) == [97, 256]

    def test_leaves_non_int(self):
        # nv
        assert maybe_promote_to_bytes(["a", "b"]) == ["a", "b"]

    def test_leaves_empty(self):
        # nv
        assert maybe_promote_to_bytes([]) == []

    def test_leaves_bool(self):
        # nv  — bools must not become bytes
        assert maybe_promote_to_bytes([True, False]) == [True, False]


class TestNormalizeSegBytes:
    def test_walks_ground_segbytes_to_bytes(self):
        # nv
        assert normalize_seg_input(SegBytes([b"abc"])) == b"abc"


class TestSegBytesGroundAgainstList:
    # The deferred Task 2 integration test: now that core bytes<->list exists.
    def test_ground_segbytes_unifies_with_intlist(self):
        # nv
        trail = Trail()
        assert SegBytes([b"ab", b"c"]).__unify__([97, 98, 99], trail) is True
