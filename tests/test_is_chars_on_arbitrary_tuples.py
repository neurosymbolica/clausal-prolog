"""is_chars answers False for any tuple that is not a chars carrier.

It compared slot 0 with ``==`` before checking its type, so a 2-tuple whose
slot 0 is an array (elementwise ``==``, no truth value) raised ValueError,
and to_python with it: a pair of arrays could not cross the boundary.
"""
from __future__ import annotations

import pytest

from clausal import to_python
from clausal.logic.cells import chars, is_chars

np = pytest.importorskip("numpy")


def test_a_pair_of_arrays_is_not_a_carrier():
    assert is_chars((np.array(["$chars", "x"]), np.array([1, 2]))) is False
    assert is_chars((np.array([1, 2]), "ab")) is False


def test_a_pair_of_arrays_crosses_to_python():
    a, b = np.array(["$chars", "x"]), np.array([1, 2])
    out = to_python((a, b))
    assert type(out) is tuple and out[0] is a and out[1] is b


def test_a_carrier_is_still_a_carrier():
    assert is_chars(chars("ab")) and is_chars(chars(""))
    assert not is_chars(("$chars", b"ab")) and not is_chars(("$chars", "a", "b"))
