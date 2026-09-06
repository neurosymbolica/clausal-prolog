"""Adversarial unhappy-path coverage for bytes-as-lists.

Captures the edge cases probed during the post-implementation audit. Every
behaviour here was verified correct against the current implementation; the
file exists so these unhappy paths cannot silently regress. Mirrors the spirit
of the strings-as-lists adversarial suite (docs/superpowers/audits/
2026-05-25-string-implementation), applied to the codes model.
"""
from clausal.logic.atoms import mint
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Var, Trail, unify, deref
from clausal.terms import SegBytes, SegString, VarSeg, PartialTermError
import pytest


def _collect(name, arity, *args, snap):
    disp = get_builtin_dispatch(name, arity, None)
    return solutions(
        StepGenerator(disp, None, None, None, *args, Trail()), snapshot=snap
    )


class TestBytesElementDomainEdges:
    def test_negative_int_fails(self):
        # nv
        assert unify(b"a", [-1], Trail()) is False

    def test_out_of_range_256_fails(self):
        # nv
        assert unify(b"a", [256], Trail()) is False

    def test_overflow_int_fails(self):
        # nv  — a huge int can never equal a byte; fail, not crash
        assert unify(b"a", [10**100], Trail()) is False

    def test_nested_list_element_fails(self):
        # nv
        assert unify(b"a", [[97]], Trail()) is False

    def test_float_equal_to_code_matches_engine_consistent(self):
        # nv  — NOT a bytes quirk: the engine unifies 97 == 97.0 for plain
        # scalars/lists too (`unify(97, 97.0)` is True). A byte IS the int,
        # so a float numerically equal to the code unifies, consistently.
        assert unify(b"abc", [97.0, 98.0, 99.0], Trail()) is True
        assert unify([97], [97.0], Trail()) is True  # the general behaviour

    def test_bool_equal_to_code_matches_engine_consistent(self):
        # nv  — likewise: True == 1 for the engine's scalar unify.
        assert unify(b"\x01", [True], Trail()) is True
        assert unify([1], [True], Trail()) is True  # the general behaviour


class TestBytesOutOfScopeGuards:
    def test_bytearray_does_not_unify(self):
        # nv  — only immutable bytes is in scope; bytearray is not a term
        assert unify(bytearray(b"abc"), [97, 98, 99], Trail()) is False

    def test_memoryview_does_not_unify(self):
        # nv
        assert unify(memoryview(b"abc"), [97, 98, 99], Trail()) is False

    def test_tuple_is_not_a_list_for_bytes(self):
        # nv  — the contract fires on list, not tuple
        assert unify(b"abc", (97, 98, 99), Trail()) is False

    def test_str_does_not_cross_with_bytes(self):
        # nv
        assert unify("abc", b"abc", Trail()) is False

    def test_charlist_does_not_cross_with_bytes(self):
        # nv
        assert unify(["a", "b", "c"], b"abc", Trail()) is False


class TestBytesCyclicSafety:
    def test_self_referential_list_with_bytes_no_crash(self):
        # nv  — bytes is a ground scalar; a cyclic list binding must not crash
        v = Var()
        assert unify(v, [b"x", v], Trail()) is True


class TestBytesTermInspectionBuiltins:
    """C14 (term inspection) for bytes: =.. / functor/3 / arg/3 follow the
    codes-model cons-cell (int head, bytes tail), consistent with str's
    char-cons-cell."""

    def test_unpack_cons_cell(self):
        # nv  — b"abc" =.. ['.', 97, b'bc']
        L = Var()
        assert _collect("unpack", 2, b"abc", L, snap=lambda L=L: deref(L)) == [
            [mint("."), 97, b"bc"]
        ]

    def test_unpack_empty_is_nil(self):
        # nv
        L = Var()
        assert _collect("unpack", 2, b"", L, snap=lambda L=L: deref(L)) == [[mint("[]")]]

    def test_functor_nonempty(self):
        # nv
        F, A = Var(), Var()
        assert _collect(
            "functor", 3, b"abc", F, A, snap=lambda F=F, A=A: (deref(F), deref(A))
        ) == [(mint("."), 2)]

    def test_functor_empty_is_nil(self):
        # nv
        F, A = Var(), Var()
        assert _collect(
            "functor", 3, b"", F, A, snap=lambda F=F, A=A: (deref(F), deref(A))
        ) == [(mint("[]"), 0)]

    def test_arg_head_is_int(self):
        # nv  — codes model: head is an int, not a 1-byte bytes
        X = Var()
        assert _collect("arg", 3, 1, b"abc", X, snap=lambda X=X: deref(X)) == [97]

    def test_arg_tail_is_bytes(self):
        # nv
        X = Var()
        assert _collect("arg", 3, 2, b"abc", X, snap=lambda X=X: deref(X)) == [b"bc"]

    def test_functor_agrees_bytes_and_intlist(self):
        # nv  — b"abc" and [97,98,99] unify, so functor/3 must agree on shape
        Fb, Ab = Var(), Var()
        s_bytes = _collect(
            "functor", 3, b"abc", Fb, Ab,
            snap=lambda F=Fb, A=Ab: (deref(F), deref(A)),
        )
        Fl, Al = Var(), Var()
        s_list = _collect(
            "functor", 3, [97, 98, 99], Fl, Al,
            snap=lambda F=Fl, A=Al: (deref(F), deref(A)),
        )
        assert s_bytes == s_list == [(mint("."), 2)]


class TestSegBytesCrossDomainAndEdges:
    def test_segbytes_not_equal_segstring(self):
        # nv  — distinct domains
        assert (SegBytes([b"a"]) == SegString(["a"])) is False

    def test_segbytes_not_equal_str(self):
        # nv
        assert (SegBytes([b"a"]) == "a") is False

    def test_segbytes_not_equal_charlist(self):
        # nv  — a char-list is not the codes view
        assert (SegBytes([b"a"]) == ["a"]) is False

    def test_segbytes_equal_codes_list(self):
        # nv
        assert (SegBytes([b"a"]) == [97]) is True

    def test_segbytes_construct_rejects_str_segment(self):
        # nv
        with pytest.raises(PartialTermError):
            SegBytes(["a"])

    def test_segbytes_walk_rejects_out_of_range_code_list_binding(self):
        # nv  — VarSeg bound to a list with a non-byte element → PartialTermError
        X = Var()
        unify(X, [300], Trail())
        with pytest.raises(PartialTermError):
            SegBytes([b"a", VarSeg(X)]).__walk__()

    def test_segbytes_contains_out_of_range_int_no_crash(self):
        # nv  — 256 in b"abc" would raise ValueError natively; must be guarded
        assert (256 in SegBytes([b"abc"])) is False

    def test_segbytes_varseg_wrong_type_raises_partial_term_error(self):
        # nv  — REVERSED by A01-F009: a VarSeg bound to a bare non-bytes
        # (str/int) used to be kept as a silent "hole", leaving the term
        # non-ground forever with every unify quietly failing. The A01 audit
        # re-decided this is a contract violation — consistent with the
        # list-with-bad-elements case above and the F024 char-list guard — so
        # __walk__ now raises PartialTermError instead of returning limbo.
        X = Var()
        unify(X, "abc", Trail())  # str into a bytes hole
        with pytest.raises(PartialTermError):
            SegBytes([VarSeg(X)]).__walk__()


class TestBytesPromiscuityRoundTrip:
    def test_plain_intlist_binding_stays_list(self):
        # nv  — no bytes source present anywhere → never becomes bytes
        V = Var()
        unify(V, [10, 20, 30], Trail())
        assert type(deref(V)) is list
