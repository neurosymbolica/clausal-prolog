import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.compiler.arg_index import (
    _bytelist_to_bytes_or_none,
    _build_first_arg_index,
)
from clausal.logic.database import Clause
from tests._suffix import SEAM


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w", delete=False) as f:
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


# Four+ clauses so the first-arg index actually builds (_INDEX_THRESHOLD == 4).
_SRC = """\
-double_quotes(atom)
helper(1),

code(b"red") <- (helper(1))
code(b"green") <- (helper(1))
code(b"blue") <- (helper(1))
code(b"cyan") <- (helper(1))
"""


class TestBytesIndexBuckets:
    """Prove spec criterion 5 at the INDEX-STRUCTURE level: a table of
    bytes-literal heads (>= threshold) actually builds an index whose buckets
    are keyed by the bytes literals — not just that a linear scan finds a
    solution."""

    def _clauses(self):
        return [
            Clause(head=("code", b"red"), body=[True]),
            Clause(head=("code", b"green"), body=[True]),
            Clause(head=("code", b"blue"), body=[True]),
            Clause(head=("code", b"cyan"), body=[True]),
        ]

    def test_index_builds_with_bytes_literal_buckets(self):
        # nv  — the index exists and buckets each bytes-literal head
        index = _build_first_arg_index(self._clauses(), 1)
        assert index is not None
        assert {b"red", b"green", b"blue", b"cyan"} <= set(index["buckets"].keys())

    def test_intlist_head_canonicalises_into_bytes_bucket(self):
        # nv  — an int-list-literal head buckets under the same key as bytes
        clauses = self._clauses() + [
            Clause(head=("code", [97, 97]), body=[True])  # == b"aa"
        ]
        index = _build_first_arg_index(clauses, 1)
        assert b"aa" in index["buckets"]


class TestBytesDispatchBuckets:
    def test_intlist_caller_reaches_bytes_clause(self):
        # nv  — list(b"green") == [103,114,101,101,110]; >=4 clauses so the
        # index is built and the int-list caller must land in the b"green" bucket
        mod = _load_inline("bytes_idx_a", _SRC)
        assert sum(1 for _ in call("code", list(b"green"), module=mod)) == 1

    def test_non_matching_intlist_matches_nothing(self):
        # nv
        mod = _load_inline("bytes_idx_b", _SRC)
        assert sum(1 for _ in call("code", [1, 2, 3], module=mod)) == 0
