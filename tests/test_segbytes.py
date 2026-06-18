import pytest

from clausal.terms import SegBytes, VarSeg, PartialTermError
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
