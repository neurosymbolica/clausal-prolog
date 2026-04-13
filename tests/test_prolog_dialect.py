"""Tests for Prolog dialect configuration and naming conventions."""
import pytest
from clausal.tools.prolog_dialect import (
    Dialect,
    pascal_to_snake, snake_to_pascal,
    clausal_var_to_prolog, prolog_var_to_clausal,
    resolve_name, BUILTIN_NAME_MAP,
)


class TestDialectFactory:
    def test_iso(self):
        # nv
        d = Dialect.iso()
        assert d.name == "iso"
        assert d.operator_table.lookup_infix("=") is not None

    def test_swi(self):
        # nv
        d = Dialect.swi()
        assert d.name == "swi"
        assert d.has_dicts is True
        assert d.clpfd_module == "clpfd"
        assert d.module_system == "swi"
        assert d.string_type == "string"

    def test_scryer(self):
        # nv
        d = Dialect.scryer()
        assert d.name == "scryer"
        assert d.has_dicts is False
        assert d.clpfd_module == "clpz"
        assert d.module_system == "iso"
        assert d.string_type == "chars"

    def test_swi_library_map(self):
        # nv
        d = Dialect.swi()
        assert "clausal.logic.clpfd" in d.library_map
        assert d.library_map["clausal.logic.clpfd"] == "library(clpfd)"

    def test_scryer_library_map(self):
        # nv
        d = Dialect.scryer()
        assert d.library_map["clausal.logic.clpfd"] == "library(clpz)"


class TestPascalToSnake:
    def test_simple(self):
        # nv
        assert pascal_to_snake("FooBar") == "foo_bar"

    def test_allcaps(self):
        # nv
        assert pascal_to_snake("CLP") == "clp"

    def test_mixed(self):
        # nv
        assert pascal_to_snake("all_different") == "all_different"

    def test_dcg(self):
        # nv
        assert pascal_to_snake("DCGRule") == "dcg_rule"

    def test_copy_term(self):
        # nv
        assert pascal_to_snake("copy_term") == "copy_term"

    def test_io_stream(self):
        # nv
        assert pascal_to_snake("IOStream") == "io_stream"

    def test_single_word(self):
        # nv
        assert pascal_to_snake("append") == "append"

    def test_already_lower(self):
        # nv
        assert pascal_to_snake("foo") == "foo"

    def test_f_string_thunk(self):
        # nv
        assert pascal_to_snake("FStringThunk") == "f_string_thunk"


class TestSnakeToPascal:
    def test_simple(self):
        # nv
        assert snake_to_pascal("foo_bar") == "FooBar"

    def test_copy_term(self):
        # nv
        assert snake_to_pascal("copy_term") == "CopyTerm"

    def test_all_different(self):
        # nv
        assert snake_to_pascal("all_different") == "AllDifferent"

    def test_single_word(self):
        # nv
        assert snake_to_pascal("append") == "Append"

    def test_already_pascal(self):
        # nv
        assert snake_to_pascal("Foo") == "Foo"


class TestClausalVarToProlog:
    def test_leading_underscore(self):
        # nv
        assert clausal_var_to_prolog("_x") == "X"

    def test_allcaps(self):
        # nv
        assert clausal_var_to_prolog("RESULT") == "Result"

    def test_single_letter(self):
        # nv
        assert clausal_var_to_prolog("X") == "X"

    def test_anon(self):
        # nv
        assert clausal_var_to_prolog("_") == "_"

    def test_lowercase_leading(self):
        # nv
        assert clausal_var_to_prolog("_head") == "Head"

    def test_mixed_leading(self):
        # nv
        assert clausal_var_to_prolog("_foo") == "Foo"

    def test_head_leading(self):
        # _head -> strip underscore -> head -> capitalize -> Head
        # nv
        assert clausal_var_to_prolog("_head") == "Head"

    def test_single_upper(self):
        # nv
        assert clausal_var_to_prolog("Y") == "Y"


class TestPrologVarToClausal:
    def test_single_upper(self):
        # nv
        assert prolog_var_to_clausal("X") == "X"

    def test_titlecase(self):
        # nv
        assert prolog_var_to_clausal("Foo") == "_foo"

    def test_head(self):
        # nv
        assert prolog_var_to_clausal("Head") == "_head"

    def test_leading_underscore(self):
        # nv
        assert prolog_var_to_clausal("_Ignored") == "_ignored"

    def test_anon(self):
        # nv
        assert prolog_var_to_clausal("_") == "_"

    def test_result(self):
        # nv
        assert prolog_var_to_clausal("Result") == "_result"


class TestResolveName:
    def test_iso_builtin(self):
        # nv
        d = Dialect.iso()
        assert resolve_name("findall", d) == "findall"

    def test_iso_copy_term(self):
        # nv
        d = Dialect.iso()
        assert resolve_name("copy_term", d) == "copy_term"

    def test_swi_all_different(self):
        # nv
        d = Dialect.swi()
        assert resolve_name("all_different", d) == "all_different"

    def test_scryer_all_different(self):
        # nv
        d = Dialect.scryer()
        assert resolve_name("all_different", d) == "all_distinct"

    def test_fallback_pascal_to_snake(self):
        # nv
        d = Dialect.iso()
        assert resolve_name("MyCustomPred", d) == "my_custom_pred"

    def test_time_goal_swi(self):
        # nv
        d = Dialect.swi()
        assert resolve_name("time_goal", d) == "time"

    def test_time_goal_scryer(self):
        # nv
        d = Dialect.scryer()
        assert resolve_name("time_goal", d) == "time"

    def test_member_iso(self):
        # nv
        d = Dialect.iso()
        assert resolve_name("Member", d) == "member"

    def test_filter_swi(self):
        # nv
        d = Dialect.swi()
        assert resolve_name("include", d) == "include"

    def test_filter_scryer(self):
        # nv
        d = Dialect.scryer()
        assert resolve_name("include", d) == "include"
