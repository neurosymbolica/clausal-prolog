from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input_py, _head_list_unify_output_py,
)


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
