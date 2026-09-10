import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load_inline(name, source):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


_SRC = """\
helper(1),

quux(b"abc") <- (helper(1))
"""


def test_bytes_head_matched_by_bytes():
    # nv
    mod = _load_inline("bytes_head_a", _SRC)
    assert sum(1 for _ in call("quux", b"abc", module=mod)) == 1


def test_bytes_head_matched_by_intlist():
    # nv
    mod = _load_inline("bytes_head_b", _SRC)
    assert sum(1 for _ in call("quux", [97, 98, 99], module=mod)) == 1


def test_bytes_head_not_matched_by_wrong_intlist():
    # nv
    mod = _load_inline("bytes_head_c", _SRC)
    assert sum(1 for _ in call("quux", [1, 2, 3], module=mod)) == 0
