from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input_py, _head_list_unify_output_py,
)
from clausal.logic.runtime.body_star_unify import (
    _body_star_unify, _build_star_list, _body_multi_star_unify,
)
from clausal.terms import SegBytes, VarSeg, ConcreteSeg


class TestBytesInputPy:
    def test_destructure_bytes_head_tail(self):
        # nv  — [H, *T] against b"abc": H=97 (int), T=b"bc" (bytes)
        trail = Trail()
        H, T = Var(), Var()
        ok = _head_list_unify_input_py(b"abc", [H], T, [], trail)
        assert ok is True
        assert deref(H) == 97
        assert deref(T) == b"bc"


class TestBytesOutputPy:
    def test_star_bound_to_bytes_rebuilds_bytes(self):
        # nv  — building [*S] with S=b"abc" yields b"abc"
        trail = Trail()
        target = Var()
        S = Var()
        unify(S, b"abc", trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == b"abc"
        assert type(deref(target)) is bytes

    def test_plain_intlist_star_not_promoted(self):
        # nv  — building [*S] with S=[1,2,3] stays an int-list (no bytes)
        trail = Trail()
        target = Var()
        S = Var()
        unify(S, [1, 2, 3], trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == [1, 2, 3]
        assert type(deref(target)) is list


class TestCExtensionActive:
    def test_c_extension_loaded(self):
        # nv  — confirm we are testing the C path, not the Python fallback
        from clausal.logic.runtime import list_unify
        from clausal.logic.runtime import _list_unify  # noqa: F401
        assert list_unify._head_list_unify_input.__module__ != "clausal.logic.runtime.list_unify"

    def test_c_star_bound_to_bytes_rebuilds_bytes(self):
        # nv  — exercise the C output path directly
        from clausal.logic.runtime._list_unify import _head_list_unify_output
        trail = Trail()
        target, S = Var(), Var()
        unify(S, b"abc", trail)
        assert _head_list_unify_output(target, [], S, [], trail) is True
        assert deref(target) == b"abc"
        assert type(deref(target)) is bytes


class TestBodyStarBytes:
    def test_deconstruct_bytes(self):
        # nv  — [H, *T] is b"abc": H=97, T=b"bc"
        trail = Trail()
        H, T = Var(), Var()
        assert _body_star_unify(b"abc", [H], T, [], trail)
        assert deref(H) == 97 and deref(T) == b"bc"

    def test_build_star_list_bytes(self):
        # nv  — *S with S=b"bc", before=[97] → b"abc"
        result = _build_star_list([97], b"bc", [])
        assert result == b"abc"
        assert type(result) is bytes

    def test_multi_star_over_bytes(self):
        # nv  — [*A, 99, *B] is b"abcdc" enumerates splits, A/B bind to bytes
        trail = Trail()
        A, B = Var(), Var()
        sols = []
        for _ in _body_multi_star_unify(
            b"abcdc", [("star", A), ("fixed", [99]), ("star", B)], trail
        ):
            sols.append((deref(A), deref(B)))
        assert (b"ab", b"dc") in sols
        assert all(type(a) is bytes and type(b) is bytes for a, b in sols)
