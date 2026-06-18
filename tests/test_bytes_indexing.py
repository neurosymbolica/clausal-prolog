import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.compiler.arg_index import _bytelist_to_bytes_or_none


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


class TestByteListCanonicaliser:
    def test_int_list_to_bytes(self):
        # nv
        assert _bytelist_to_bytes_or_none([97, 98, 99]) == b"abc"

    def test_empty_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none([]) is None

    def test_out_of_range_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none([97, 256]) is None

    def test_non_int_is_none(self):
        # nv
        assert _bytelist_to_bytes_or_none(["a"]) is None


_SRC = """\
Helper(1),

Code(b"red") <- (Helper(1))
Code(b"green") <- (Helper(1))
Code(b"blue") <- (Helper(1))
"""


class TestBytesDispatchBuckets:
    def test_intlist_caller_reaches_bytes_clause(self):
        # nv  — list(b"green") == [103,114,101,101,110]
        mod = _load_inline("bytes_idx_a", _SRC)
        assert sum(1 for _ in call("Code", list(b"green"), module=mod)) == 1

    def test_non_matching_intlist_matches_nothing(self):
        # nv
        mod = _load_inline("bytes_idx_b", _SRC)
        assert sum(1 for _ in call("Code", [1, 2, 3], module=mod)) == 0
