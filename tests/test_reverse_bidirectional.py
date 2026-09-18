"""reverse/2 must work in both directions (todo/reverse-not-bidirectional.md).

Forward (List ground) was always supported. Backward (Rev ground, List an
unbound Var) yielded no solution — a mode-incompleteness vs standard Prolog,
found by the input/output mode-coverage audit. These tests pin both directions,
including the strings-as-lists / bytes-as-codes seq-result contract in reverse
mode.
"""

import os
import tempfile

import pytest

from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.logic.cells import chars


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write("-module(rev_bi, [])\n")
        f.flush()
        m = _load(f.name)
    yield m
    os.unlink(f.name)


def _load(path):
    from clausal.import_hook import _load_module
    return _load_module("rev_bi_mod", path).__dict__["$module"]


def _collect(var, functor, *args, module):
    return [deref(var) for _ in call(functor, *args, module=module)]


class TestReverseBackward:
    def test_list_backward(self, mod):
        """reverse(L, [3,2,1]) binds L = [1,2,3]."""
        L = Var()
        assert _collect(L, "reverse", L, [3, 2, 1], module=mod) == [[1, 2, 3]]

    def test_list_forward_still_works(self, mod):
        R = Var()
        assert _collect(R, "reverse", [1, 2, 3], R, module=mod) == [[3, 2, 1]]

    def test_string_backward_keeps_str(self, mod):
        """Backward reverse of a str result stays a str (input-type-wins)."""
        L = Var()
        assert _collect(L, "reverse", L, chars("olleh"), module=mod) == [chars("hello")]

    def test_bytes_backward_keeps_bytes(self, mod):
        """Backward reverse of a bytes result stays bytes (codes model)."""
        L = Var()
        assert _collect(L, "reverse", L, b"cba", module=mod) == [b"abc"]

    def test_both_ground_verifies(self, mod):
        """Both args ground: succeeds iff they are reverses of each other."""
        assert sum(1 for _ in call("reverse", [1, 2], [2, 1], module=mod)) == 1
        assert sum(1 for _ in call("reverse", [1, 2], [1, 2], module=mod)) == 0

    def test_empty_backward(self, mod):
        L = Var()
        assert _collect(L, "reverse", L, [], module=mod) == [[]]
