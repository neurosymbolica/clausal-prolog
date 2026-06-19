"""List-library predicates over bytes (codes model).

Mirrors tests/test_string_list_builtins.py for bytes: elements are int codes,
and sequence results reconstruct as bytes (input-type-wins).
"""
import os
import tempfile

from clausal.import_hook import _load_module
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
        assert sum(1 for _ in call("append", b"ab", b"c", "abc", module=_M)) == 0
