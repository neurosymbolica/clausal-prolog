from clausal.logic.builtins._helpers import (
    _functor_name_py, _arity_py, _nth_arg_py, _args_list_py,
)
import pytest


class TestBytesFallbackFunctorName:
    def test_nonempty(self):
        # nv
        assert _functor_name_py(b"abc") == "."

    def test_empty(self):
        # nv
        assert _functor_name_py(b"") == "[]"


class TestBytesFallbackArity:
    def test_nonempty(self):
        # nv
        assert _arity_py(b"abc") == 2

    def test_empty(self):
        # nv
        assert _arity_py(b"") == 0


class TestBytesFallbackNthArg:
    def test_head_is_int(self):
        # nv  — codes model: head is an int
        assert _nth_arg_py(b"abc", 1) == 97

    def test_tail_is_bytes(self):
        # nv
        assert _nth_arg_py(b"abc", 2) == b"bc"
        assert type(_nth_arg_py(b"abc", 2)) is bytes

    def test_out_of_range(self):
        # nv
        with pytest.raises(IndexError):
            _nth_arg_py(b"abc", 3)


class TestBytesFallbackArgsList:
    def test_nonempty(self):
        # nv
        assert _args_list_py(b"abc") == [97, b"bc"]

    def test_empty(self):
        # nv
        assert _args_list_py(b"") == []
