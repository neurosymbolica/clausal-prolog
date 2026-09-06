from clausal.logic.atoms import char_atom, mint
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input_py, _head_list_unify_output_py,
)
from clausal.logic.runtime.body_star_unify import (
    _body_star_unify, _build_star_list, _body_multi_star_unify,
)
from clausal.terms import SegBytes, SegList, VarSeg, ConcreteSeg


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

    def test_multi_star_pure_intlist_stays_list(self):
        # nv  — no bytes/SegBytes source present → must NOT become bytes
        from clausal.logic.runtime.body_star_unify import _build_multi_star_list
        assert _build_multi_star_list([("fixed", [10, 20, 30])]) == [10, 20, 30]
        assert type(_build_multi_star_list([("fixed", [10, 20, 30])])) is list

    def test_multi_star_intlist_star_stays_list(self):
        # nv  — a star bound to a plain int-list is not a bytes source
        from clausal.logic.runtime.body_star_unify import _build_multi_star_list
        Ys = Var()
        unify(Ys, [20, 30], Trail())
        out = _build_multi_star_list([("fixed", [10]), ("star", Ys)])
        assert out == [10, 20, 30] and type(out) is list

    def test_multi_star_with_bytes_source_promotes(self):
        # nv  — a bytes star IS a source → promotes to bytes
        from clausal.logic.runtime.body_star_unify import _build_multi_star_list
        Ys = Var()
        unify(Ys, b"\x14\x1e", Trail())
        out = _build_multi_star_list([("fixed", [10]), ("star", Ys)])
        assert out == b"\n\x14\x1e" and type(out) is bytes


class TestGroundSegListOfCharsOutputPy:
    """Review fix (Task 5 fix round 1): SegList.__walk__ (terms.py)
    applies maybe_promote_to_str to a fully-ground result, so a ground
    SegList whose elements are all 1-char strs walks to a STR, not a
    list. _head_list_unify_output_py's SegList-star branch used to only
    handle ``isinstance(walked, list)`` and otherwise assumed
    ``walked.segments`` (the non-ground-SegList shape) — a str has no
    ``.segments``, so this raised AttributeError. The C twin
    (_list_unify.c, ``PyList_Check(walked) || PyUnicode_Check(walked)``)
    already handled both shapes; the Python fallback is now fixed to
    match it exactly (twin agreement, not independent judgment).
    """

    def test_ground_seglist_of_chars_star_promotes_via_python_fallback(self):
        # nv — repro: SegList([ConcreteSeg(['a','b'])]) as a star source,
        # driven through the _py-suffixed function directly (bypasses the
        # C extension, forcing the Python fallback path per the
        # established pattern in this file).
        trail = Trail()
        target = Var()
        S = Var()
        sl = SegList([ConcreteSeg([char_atom("a"), char_atom("b")])])
        unify(S, sl, trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == "ab"
        assert type(deref(target)) is str

    def test_ground_seglist_of_chars_matches_c_twin(self):
        # nv — same input through the C-accelerated function: the Python
        # fallback and the C twin must agree exactly.
        from clausal.logic.runtime._list_unify import _head_list_unify_output

        trail_py = Trail()
        target_py = Var()
        S_py = Var()
        unify(S_py, SegList([ConcreteSeg([char_atom("a"), char_atom("b")])]), trail_py)
        ok_py = _head_list_unify_output_py(target_py, [], S_py, [], trail_py)

        trail_c = Trail()
        target_c = Var()
        S_c = Var()
        unify(S_c, SegList([ConcreteSeg([char_atom("a"), char_atom("b")])]), trail_c)
        ok_c = _head_list_unify_output(target_c, [], S_c, [], trail_c)

        assert ok_py == ok_c is True
        assert deref(target_py) == deref(target_c) == "ab"
        assert type(deref(target_py)) is type(deref(target_c)) is str

    def test_ground_seglist_of_non_chars_stays_list_via_python_fallback(self):
        # nv — control: a ground SegList with non-1-char elements does
        # NOT promote (maybe_promote_to_str declines), and must still
        # hit the ``isinstance(walked, (list, str))`` branch as a list —
        # unaffected by the fix, still a regression guard against
        # re-narrowing the isinstance check.
        trail = Trail()
        target = Var()
        S = Var()
        sl = SegList([ConcreteSeg([1, 2, 3])])
        unify(S, sl, trail)
        ok = _head_list_unify_output_py(target, [], S, [], trail)
        assert ok is True
        assert deref(target) == [1, 2, 3]
        assert type(deref(target)) is list
