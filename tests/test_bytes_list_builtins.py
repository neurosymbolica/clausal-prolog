"""List-library predicates over bytes (codes model).

Mirrors tests/test_string_list_builtins.py for bytes: elements are int codes,
and sequence results reconstruct as bytes (input-type-wins).
"""
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _mod(name, src=""):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(src or "noop(1),\n")
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


def _first(gen, snap):
    for _ in gen:
        return snap()
    return None


_M = _mod("blb_shared")


class TestMemberBytes:
    def test_member_code_succeeds(self):
        # nv  — in_(98, b"abc") : 98 is the code for 'b'
        assert sum(1 for _ in call("in_", 98, b"abc", module=_M)) == 1

    def test_member_absent_fails(self):
        # nv
        assert sum(1 for _ in call("in_", 200, b"abc", module=_M)) == 0

    def test_member_enumerates_codes(self):
        # nv  — in_(X, b"ab") yields 97 then 98
        got = []
        for _ in call("in_", (X := Var()), b"ab", module=_M):
            got.append(deref(X))
        assert got == [97, 98]


class TestAppendBytes:
    def test_concat_returns_bytes(self):
        # nv  — append(b"he", b"llo", X) → X = b"hello"
        snap = _first(call("append", b"he", b"llo", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"hello", bytes)

    def test_concat_check(self):
        # nv
        assert sum(1 for _ in call("append", b"he", b"llo", b"hello", module=_M)) == 1

    def test_compute_suffix(self):
        # nv  — append(b"he", X, b"hello") → X = b"llo"
        snap = _first(call("append", b"he", (X := Var()), b"hello", module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"llo", bytes)

    def test_enumerate_splits_are_bytes(self):
        # nv  — append(A, B, b"hi") enumerates (b"",b"hi"),(b"h",b"i"),(b"hi",b"")
        A, B = Var(), Var()
        seen = []
        for _ in call("append", A, B, b"hi", module=_M):
            seen.append((deref(A), deref(B)))
        assert (b"h", b"i") in seen
        assert all(type(a) is bytes and type(b) is bytes for a, b in seen)
        assert len(seen) == 3


class TestReverseBytes:
    def test_reverse_returns_bytes(self):
        # nv
        snap = _first(call("reverse", b"abc", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"cba", bytes)


class TestLengthBytes:
    def test_length(self):
        # nv
        snap = _first(call("length", b"abc", (N := Var()), module=_M), lambda: deref(N))
        assert snap == 3


class TestListItemBytes:
    def test_nth0_is_int_code(self):
        # nv  — list_item(1, b"abc", E) → E = 98
        snap = _first(call("list_item", 1, b"abc", (E := Var()), module=_M),
                      lambda: deref(E))
        assert snap == 98


class TestTakeDropSplitBytes:
    def test_take(self):
        # nv
        snap = _first(call("take", 2, b"hello", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"he", bytes)

    def test_drop(self):
        # nv
        snap = _first(call("drop", 2, b"hello", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"llo", bytes)

    def test_split_at(self):
        # nv
        A, B = Var(), Var()
        snap = _first(call("split_at", 2, b"hello", A, B, module=_M),
                      lambda: (deref(A), deref(B), type(deref(A)), type(deref(B))))
        assert snap == (b"he", b"llo", bytes, bytes)


class TestLastBytes:
    def test_last_is_int_code(self):
        # nv  — last(b"abc", E) → E = 99
        snap = _first(call("last", b"abc", (E := Var()), module=_M), lambda: deref(E))
        assert snap == 99


class TestBytesListNoStrCross:
    def test_append_does_not_mix_str_and_bytes(self):
        # nv  — bytes and str do not cross; append(b"a", "b", X) has no clean
        # codes/chars result, must not silently produce a wrong-typed answer.
        # (We assert it does not unify a bytes result against a str caller.)
        assert sum(1 for _ in call("append", b"ab", b"c", chars("abc"), module=_M)) == 0


class TestSecondarySequencePredicatesBytes:
    """Full input-type-wins parity: sort/select/permutation/set-ops/split_with
    reconstruct bytes from a bytes input, just as they reconstruct str."""

    def test_msort(self):
        # nv
        snap = _first(call("msort", b"cba", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"abc", bytes)

    def test_sort_dedup(self):
        # nv  — sort removes duplicates
        snap = _first(call("sort", b"aab", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"ab", bytes)

    def test_select_rest_is_bytes(self):
        # nv  — select(98, b"abc", Rest) → Rest = b"ac"
        snap = _first(call("select", 98, b"abc", (R := Var()), module=_M),
                      lambda: (deref(R), type(deref(R))))
        assert snap == (b"ac", bytes)

    def test_permutation_yields_bytes(self):
        # nv
        seen = []
        for _ in call("permutation", b"ab", (X := Var()), module=_M):
            seen.append(deref(X))
        assert set(seen) == {b"ab", b"ba"}
        assert all(type(s) is bytes for s in seen)

    def test_subtract(self):
        # nv
        snap = _first(call("subtract", b"abc", b"b", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"ac", bytes)

    def test_intersection(self):
        # nv
        snap = _first(call("intersection", b"abc", b"bcd", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"bc", bytes)

    def test_union(self):
        # nv
        snap = _first(call("union", b"ab", b"bc", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"abc", bytes)

    def test_list_to_set(self):
        # nv
        snap = _first(call("list_to_set", b"aab", (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"ab", bytes)

    def test_split_with_parts_are_bytes(self):
        # nv  — split b"a,b" on the comma code (44) → [b"a", b"b"]
        snap = _first(call("split_with", 44, b"a,b", (P := Var()), module=_M),
                      lambda: deref(P))
        assert snap == [b"a", b"b"]


class TestSameLengthBytes:
    """same_length/2 must treat bytes as a sequence (codes model), mirroring
    str. Regression for the inline isinstance(.,(list,str)) that omitted bytes."""

    def test_same_length_bytes_bytes(self):
        # nv  — both length 3
        assert sum(1 for _ in call("same_length", b"abc", b"xyz", module=_M)) == 1

    def test_different_length_bytes(self):
        # nv
        assert sum(1 for _ in call("same_length", b"ab", b"xyz", module=_M)) == 0

    def test_same_length_bytes_list(self):
        # nv  — cross-type: bytes vs int-list, both length 3
        assert sum(1 for _ in call("same_length", b"abc", [1, 2, 3], module=_M)) == 1

    def test_same_length_bytes_var_binds_shape(self):
        # nv  — same_length(b"abc", V) binds V to a 3-element bytes-shaped placeholder
        got = _first(call("same_length", b"abc", (V := Var()), module=_M),
                     lambda: deref(V))
        assert got is not None
        # placeholder has three element-slots (bytes-shaped, mirroring str's SegString)
        from clausal.terms import SegBytes
        assert isinstance(got, SegBytes)
        assert len(got.segments) == 3


class TestSegBytesThroughBuiltins:
    """A ground SegBytes flowing into a list-library predicate must be treated
    as the bytes it walks to — not crash. Regression for the missing
    SegBytes.is_ground() at lists.py:69/:100 (the DCG-builds-SegBytes →
    list-library workflow)."""

    def test_reverse_of_ground_segbytes(self):
        from clausal.terms import SegBytes
        # nv  — reverse(SegBytes([b"ab", b"c"]), X) → X = b"cba"
        snap = _first(call("reverse", SegBytes([b"ab", b"c"]), (X := Var()), module=_M),
                      lambda: (deref(X), type(deref(X))))
        assert snap == (b"cba", bytes)

    def test_length_of_ground_segbytes(self):
        from clausal.terms import SegBytes
        # nv  — length(SegBytes([b"abc"]), N) → N = 3
        snap = _first(call("length", SegBytes([b"abc"]), (N := Var()), module=_M),
                      lambda: deref(N))
        assert snap == 3
