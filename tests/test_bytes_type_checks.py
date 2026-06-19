"""Type-check predicate semantics for bytes (codes model).

is_list/1  → bytes is list-shaped (like str)  → succeeds
is_codes/1 → new: a code sequence (bytes, or a list of ints in [0,255]) → succeeds
is_str/1   → a bytes is NOT a str → fails
is_chars/1 → a bytes is a CODE sequence, not a CHAR sequence → fails
"""
import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _mod(name, src=""):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(src or "noop(1),\n")
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


def _ok(pred, arg, mod):
    return sum(1 for _ in call(pred, arg, module=mod)) >= 1


class TestIsListBytes:
    def test_is_list_accepts_bytes(self):
        # nv  — bytes is list-shaped under the codes model
        assert _ok("is_list", b"abc", _mod("tc_il"))

    def test_is_list_still_accepts_str_and_list(self):
        # nv  — regression
        mod = _mod("tc_il2")
        assert _ok("is_list", "abc", mod)
        assert _ok("is_list", [1, 2, 3], mod)


class TestIsCodes:
    def test_is_codes_accepts_bytes(self):
        # nv
        assert _ok("is_codes", b"abc", _mod("tc_ic"))

    def test_is_codes_accepts_int_list(self):
        # nv  — a list of ints in [0,255]
        assert _ok("is_codes", [97, 98, 99], _mod("tc_ic2"))

    def test_is_codes_rejects_out_of_range_list(self):
        # nv
        assert not _ok("is_codes", [97, 256], _mod("tc_ic3"))

    def test_is_codes_rejects_char_list(self):
        # nv  — a char list is the chars model, not codes
        assert not _ok("is_codes", ["a", "b"], _mod("tc_ic4"))

    def test_is_codes_rejects_str(self):
        # nv
        assert not _ok("is_codes", "abc", _mod("tc_ic5"))

    def test_is_codes_accepts_empty_list(self):
        # nv  — empty is trivially a code sequence
        assert _ok("is_codes", [], _mod("tc_ic6"))


class TestNonGroundSegBytesGuard:
    """A SegBytes that still holds an unbound VarSeg is NOT ground, so the
    groundness guard in is_list/1, is_codes/1 and ground/1 must reject it.
    Regression for _is_ground not knowing about SegBytes (F083 for bytes)."""

    def _nonground(self):
        from clausal.terms import SegBytes, VarSeg
        from clausal.logic.variables import Var
        return SegBytes([b"GET", VarSeg(Var())])

    def test_is_list_rejects_nonground_segbytes(self):
        # nv
        assert not _ok("is_list", self._nonground(), _mod("tc_ngsb1"))

    def test_is_codes_rejects_nonground_segbytes(self):
        # nv
        assert not _ok("is_codes", self._nonground(), _mod("tc_ngsb2"))

    def test_ground_rejects_nonground_segbytes(self):
        # nv
        assert not _ok("ground", self._nonground(), _mod("tc_ngsb3"))


class TestBytesStaysNotStrNotChars:
    def test_is_str_rejects_bytes(self):
        # nv  — a bytes is not a str
        assert not _ok("is_str", b"abc", _mod("tc_str"))

    def test_string_rejects_bytes(self):
        # nv
        assert not _ok("string", b"abc", _mod("tc_string"))

    def test_is_chars_rejects_bytes(self):
        # nv  — bytes is a CODE sequence, not a CHAR sequence
        assert not _ok("is_chars", b"abc", _mod("tc_chars"))
