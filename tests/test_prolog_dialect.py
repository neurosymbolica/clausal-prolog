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
        d = Dialect.iso()
        assert d.name == "iso"
        assert d.operator_table.lookup_infix("=") is not None

    def test_swi(self):
        d = Dialect.swi()
        assert d.name == "swi"
        assert d.has_dicts is True
        assert d.clpfd_module == "clpfd"
        assert d.module_system == "swi"
        assert d.string_type == "string"

    def test_scryer(self):
        d = Dialect.scryer()
        assert d.name == "scryer"
        assert d.has_dicts is False
        assert d.clpfd_module == "clpz"
        assert d.module_system == "iso"
        assert d.string_type == "chars"

    def test_swi_library_map(self):
        d = Dialect.swi()
        assert "clausal.logic.clpfd" in d.library_map
        assert d.library_map["clausal.logic.clpfd"] == "library(clpfd)"

    def test_scryer_library_map(self):
        d = Dialect.scryer()
        assert d.library_map["clausal.logic.clpfd"] == "library(clpz)"


class TestPascalToSnake:
    def test_simple(self):
        assert pascal_to_snake("FooBar") == "foo_bar"

    def test_allcaps(self):
        assert pascal_to_snake("CLP") == "clp"

    def test_mixed(self):
        assert pascal_to_snake("AllDifferent") == "all_different"

    def test_dcg(self):
        assert pascal_to_snake("DCGRule") == "dcg_rule"

    def test_copy_term(self):
        assert pascal_to_snake("CopyTerm") == "copy_term"

    def test_io_stream(self):
        assert pascal_to_snake("IOStream") == "io_stream"

    def test_single_word(self):
        assert pascal_to_snake("Append") == "append"

    def test_already_lower(self):
        assert pascal_to_snake("foo") == "foo"

    def test_f_string_thunk(self):
        assert pascal_to_snake("FStringThunk") == "f_string_thunk"


class TestSnakeToPascal:
    def test_simple(self):
        assert snake_to_pascal("foo_bar") == "FooBar"

    def test_copy_term(self):
        assert snake_to_pascal("copy_term") == "CopyTerm"

    def test_all_different(self):
        assert snake_to_pascal("all_different") == "AllDifferent"

    def test_single_word(self):
        assert snake_to_pascal("append") == "Append"

    def test_already_pascal(self):
        assert snake_to_pascal("Foo") == "Foo"


class TestClausalVarToProlog:
    def test_leading_underscore(self):
        assert clausal_var_to_prolog("_x") == "X"

    def test_allcaps(self):
        assert clausal_var_to_prolog("RESULT") == "Result"

    def test_single_letter(self):
        assert clausal_var_to_prolog("X") == "X"

    def test_anon(self):
        assert clausal_var_to_prolog("_") == "_"

    def test_lowercase_leading(self):
        assert clausal_var_to_prolog("_head") == "Head"

    def test_mixed_leading(self):
        assert clausal_var_to_prolog("_foo") == "Foo"

    def test_head_leading(self):
        # _head -> strip underscore -> head -> capitalize -> Head
        assert clausal_var_to_prolog("_head") == "Head"

    def test_single_upper(self):
        assert clausal_var_to_prolog("Y") == "Y"


class TestPrologVarToClausal:
    def test_single_upper(self):
        assert prolog_var_to_clausal("X") == "X"

    def test_titlecase(self):
        assert prolog_var_to_clausal("Foo") == "_foo"

    def test_head(self):
        assert prolog_var_to_clausal("Head") == "_head"

    def test_leading_underscore(self):
        assert prolog_var_to_clausal("_Ignored") == "_ignored"

    def test_anon(self):
        assert prolog_var_to_clausal("_") == "_"

    def test_result(self):
        assert prolog_var_to_clausal("Result") == "_result"


class TestResolveName:
    def test_iso_builtin(self):
        d = Dialect.iso()
        assert resolve_name("FindAll", d) == "findall"

    def test_iso_copy_term(self):
        d = Dialect.iso()
        assert resolve_name("CopyTerm", d) == "copy_term"

    def test_swi_all_different(self):
        d = Dialect.swi()
        assert resolve_name("AllDifferent", d) == "all_different"

    def test_scryer_all_different(self):
        d = Dialect.scryer()
        assert resolve_name("AllDifferent", d) == "all_distinct"

    def test_fallback_pascal_to_snake(self):
        d = Dialect.iso()
        assert resolve_name("MyCustomPred", d) == "my_custom_pred"

    def test_time_goal_swi(self):
        d = Dialect.swi()
        assert resolve_name("TimeGoal", d) == "time"

    def test_time_goal_scryer(self):
        d = Dialect.scryer()
        assert resolve_name("TimeGoal", d) == "time"

    def test_member_iso(self):
        d = Dialect.iso()
        assert resolve_name("Member", d) == "member"

    def test_filter_swi(self):
        d = Dialect.swi()
        assert resolve_name("Filter", d) == "include"

    def test_filter_scryer(self):
        d = Dialect.scryer()
        assert resolve_name("Filter", d) == "include"
