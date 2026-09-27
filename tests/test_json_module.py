"""Tests for clausal.modules.py.json — JSON predicates."""

from __future__ import annotations

import os

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars, chars_text
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_context_text
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.json import (
    parse, generate, pretty_generate, get, read_file, write_file,
    _parse_2, _parse_3, _generate_2, _pretty_generate_2,
    _get_3, _read_file_2, _write_file_2,
    _python_to_clausal, _clausal_to_python,
)
from clausal.terms import DictTerm
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── Converter unit tests ────────────────────────────────────────────────


class TestConverters:
    def test_python_to_clausal_dict(self):
        # nv
        result = _python_to_clausal({"a": 1, "b": 2})
        assert isinstance(result, DictTerm)
        # JSON object keys are minted as ATOMS (spec §9.2).
        assert result.data == {mint("a"): 1, mint("b"): 2}

    def test_python_to_clausal_nested(self):
        # nv
        result = _python_to_clausal({"a": {"b": 1}})
        assert isinstance(result, DictTerm)
        inner = result.data[mint("a")]
        assert isinstance(inner, DictTerm)
        assert inner.data == {mint("b"): 1}

    def test_python_to_clausal_list(self):
        # nv
        result = _python_to_clausal([1, {"a": 2}])
        assert isinstance(result, list)
        assert result[0] == 1
        assert isinstance(result[1], DictTerm)

    def test_python_to_clausal_scalars(self):
        # nv
        assert _python_to_clausal("hello") == chars("hello")
        assert _python_to_clausal(42) == 42
        assert _python_to_clausal(3.14) == 3.14
        assert _python_to_clausal(True) is True
        assert _python_to_clausal(None) is None

    def test_clausal_to_python_dict_term(self):
        # nv
        dt = DictTerm({"x": 1, "y": 2})
        result = _clausal_to_python(dt)
        assert result == {"x": 1, "y": 2}

    def test_clausal_to_python_nested(self):
        # nv
        dt = DictTerm({"a": DictTerm({"b": 1})})
        result = _clausal_to_python(dt)
        assert result == {"a": {"b": 1}}

    def test_clausal_to_python_list(self):
        # nv
        result = _clausal_to_python([1, DictTerm({"a": 2})])
        assert result == [1, {"a": 2}]

    def test_clausal_to_python_unbound_var_raises(self):
        # nv
        with pytest.raises(TypeError, match="unbound variable"):
            _clausal_to_python(Var())


# ── parse/2 ─────────────────────────────────────────────────────────────


class TestParse:
    def test_simple_object(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, chars('{"a": 1, "b": 2}'), t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data[mint("a")] == 1
        assert result.data[mint("b")] == 2

    def test_nested_object(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, chars('{"a": {"b": 3}}'), t)
        assert len(sols) == 1
        result = deref(t)
        inner = result.data[mint("a")]
        assert isinstance(inner, DictTerm)
        assert inner.data[mint("b")] == 3

    def test_array(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, chars('[1, 2, 3]'), t)
        assert len(sols) == 1
        assert deref(t) == [1, 2, 3]

    def test_string_scalar(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('"hello"'), t)
        assert len(sols) == 1
        assert deref(t) == chars("hello")

    def test_number_int(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('42'), t)
        assert len(sols) == 1
        assert deref(t) == 42

    def test_number_float(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('3.14'), t)
        assert len(sols) == 1
        assert deref(t) == 3.14

    def test_bool(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('true'), t)
        assert len(sols) == 1
        assert deref(t) is True

    def test_null(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('null'), t)
        assert len(sols) == 1
        assert deref(t) is None

    def test_empty_object(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('{}'), t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data == {}

    def test_empty_array(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, chars('[]'), t)
        assert len(sols) == 1
        assert deref(t) == []

    def test_unbound_string_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_2, Var(), Var())
        assert len(sols) == 0

    def test_invalid_json_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_2, chars('{bad json}'), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        t = Var()
        sols, trail = trampoline_solutions(parse, chars('{"x": 1}'), t)
        assert len(sols) == 1
        assert isinstance(deref(t), DictTerm)


# ── generate/2 ──────────────────────────────────────────────────────────


class TestGenerate:
    def test_dict_term(self):
        # nv
        s = Var()
        dt = DictTerm({"a": 1})
        sols, trail = simple_solutions(_generate_2, dt, s)
        assert len(sols) == 1
        import json
        assert json.loads(chars_text(deref(s))) == {"a": 1}

    def test_nested(self):
        # nv
        s = Var()
        dt = DictTerm({"a": DictTerm({"b": 2})})
        sols, trail = simple_solutions(_generate_2, dt, s)
        assert len(sols) == 1
        import json
        assert json.loads(chars_text(deref(s))) == {"a": {"b": 2}}

    def test_list(self):
        # nv
        s = Var()
        sols, trail = simple_solutions(_generate_2, [1, 2, 3], s)
        assert len(sols) == 1
        assert deref(s) == chars("[1, 2, 3]")

    def test_scalars(self):
        # nv
        s = Var()
        sols, _ = simple_solutions(_generate_2, chars("hello"), s)
        assert len(sols) == 1
        assert deref(s) == chars('"hello"')

    def test_unbound_var_fails(self):
        """Unbound term fails (can't serialize)."""
        # nv
        sols, _ = simple_solutions(_generate_2, Var(), Var())
        assert len(sols) == 0

    def test_round_trip(self):
        """parse then generate yields equivalent JSON."""
        # nv
        import json
        original = '{"name": "alice", "scores": [1, 2, 3]}'
        t = Var()
        simple_solutions(_parse_2, chars(original), t)
        s = Var()
        simple_solutions(_generate_2, deref(t), s)
        assert json.loads(chars_text(deref(s))) == json.loads(original)


# ── pretty_generate/2 ───────────────────────────────────────────────────


class TestPrettyGenerate:
    def test_indented(self):
        # nv
        s = Var()
        dt = DictTerm({"a": 1})
        sols, trail = simple_solutions(_pretty_generate_2, dt, s)
        assert len(sols) == 1
        result = chars_text(deref(s))
        assert "\n" in result
        assert "  " in result


# ── get/3 ──────────────────────────────────────────────────────────────


class TestGet:
    def test_key_bound(self):
        # nv
        v = Var()
        dt = DictTerm({"name": "alice", "age": 30})
        sols, trail = simple_solutions(_get_3, dt, "name", v)
        assert len(sols) == 1
        assert deref(v) == "alice"

    def test_key_not_found_fails(self):
        # nv
        sols, _ = simple_solutions(_get_3, DictTerm({"a": 1}), "z", Var())
        assert len(sols) == 0

    def test_key_unbound_enumerates(self):
        # nv
        dt = DictTerm({"x": 1, "y": 2, "z": 3})
        pairs = []
        trail = Trail()
        for _ in _get_3(dt, Var(), Var(), trail, None):
            # We need fresh vars each iteration to collect properly
            pass
        # Better: collect via separate calls
        keys_found = set()
        for key in ["x", "y", "z"]:
            k, v = Var(), Var()
            t = Trail()
            sols = list(_get_3(dt, k, v, t, None))
            # k is unbound at start — but we passed a fresh Var here,
            # let's test with bound keys instead for simplicity
        # Test enumeration properly with unbound key
        k, v = Var(), Var()
        trail = Trail()
        count = 0
        for _ in _get_3(dt, k, v, trail, None):
            count += 1
        assert count == 3

    def test_not_dict_term_fails(self):
        # nv
        sols, _ = simple_solutions(_get_3, "not a dict", "key", Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        v = Var()
        dt = DictTerm({"a": 42})
        sols, trail = trampoline_solutions(get, dt, "a", v)
        assert len(sols) == 1
        assert deref(v) == 42


# ── read_file/2 & write_file/2 ───────────────────────────────────────────


class TestFileIO:
    def test_round_trip(self, tmp_path):
        # nv
        path = str(tmp_path / "test.json")
        dt = DictTerm({"hello": "world", "n": 42})
        sols, _ = simple_solutions(_write_file_2, chars(path), dt)
        assert len(sols) == 1

        t = Var()
        sols, trail = simple_solutions(_read_file_2, chars(path), t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data[mint("hello")] == chars("world")
        assert result.data[mint("n")] == 42

    def test_read_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, chars("/nonexistent/file.json"), Var())
        assert len(sols) == 0

    def test_write_unbound_term_fails(self):
        # nv
        sols, _ = simple_solutions(_write_file_2, chars("/tmp/test.json"), Var())
        assert len(sols) == 0

    def test_read_unbound_path_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, Var(), Var())
        assert len(sols) == 0


# ── parse/3 (spec §9.2: the atoms(Spellings) vocabulary hook) ────────────


class TestParse3AtomsOption:
    # NOTE on what these do and do not pin. Under Plan 0 an atom IS its
    # spelling (``mint("red") == "red"``, and ``==`` is the semantics), so
    # the "is it an atom or a string?" half of every assertion below is
    # VACUOUS today: `d[mint("k")] == mint("red")` and `... == "red"` are the
    # same claim. What they pin today is the ROUTE — that parse/3 exists,
    # that the option is parsed and honoured, that the vocabulary reaches
    # nested values, and that an unknown option is a domain_error. They
    # start biting on the atom/string distinction at Stage B, when
    # ``mint("red")`` becomes ``("red",)`` and stops comparing equal to the
    # string; no rewrite is needed then, they simply become load-bearing.

    def test_json_parse_3_atoms_option_mints_listed_strings(self):
        t = Var()
        sols, _ = simple_solutions(
            _parse_3, chars('{"k": "red", "j": "text"}'), t, [("atoms", ["red"])]
        )
        assert len(sols) == 1
        d = deref(t)
        assert d[mint("k")] == mint("red") and d[mint("j")] == chars("text")

    def test_parse_3_empty_options_matches_parse_2(self):
        t2, t3 = Var(), Var()
        simple_solutions(_parse_2, chars('{"k": "red"}'), t2)
        sols, _ = simple_solutions(_parse_3, chars('{"k": "red"}'), t3, [])
        assert len(sols) == 1
        assert deref(t3).data == deref(t2).data

    def test_parse_3_atoms_option_reaches_nested_values(self):
        t = Var()
        sols, _ = simple_solutions(
            _parse_3, chars('{"a": {"b": "red"}, "c": ["red", "blue"]}'), t,
            [("atoms", ["red"])],
        )
        assert len(sols) == 1
        d = deref(t)
        assert d[mint("a")][mint("b")] == mint("red")
        assert d[mint("c")] == [mint("red"), chars("blue")]

    def test_parse_3_rejects_an_unknown_option(self):
        with pytest.raises(LogicException) as exc:
            list(simple_solutions(
                _parse_3, chars('{"k": 1}'), Var(), [("colours", ["red"])],
            ))
        assert cell_functor(cell_args(exc.value.term)[0]) == "domain_error"
        assert cell_args(cell_args(exc.value.term)[0])[0] == mint("json_option")

    def test_parse_3_is_reachable_through_the_module_predicate(self):
        t = Var()
        sols, _ = trampoline_solutions(
            parse, chars('{"k": "red"}'), t, [("atoms", ["red"])]
        )
        assert len(sols) == 1
        assert deref(t)[mint("k")] == mint("red")

    def test_parse_3_spellings_accepts_atoms_and_strings_alike(self):
        # An element of Spellings may be an atom or a string, and both name
        # the same text.  At Stage B, ``atoms(["red"])`` written in source is
        # a list of STRINGS — demanding atoms there would make the option
        # unwritable in the notation it exists to serve.
        for element in (chars("red"), "red"):
            t = Var()
            sols, _ = simple_solutions(
                _parse_3, chars('{"k": "red"}'), t, [("atoms", [element])]
            )
            assert len(sols) == 1
            assert deref(t)[mint("k")] == mint("red")

    def test_parse_3_rejects_a_non_text_spelling(self):
        with pytest.raises(LogicException) as exc:
            list(simple_solutions(
                _parse_3, chars('{"k": 1}'), Var(), [("atoms", [42])],
            ))
        assert cell_args(cell_args(exc.value.term)[0])[0] == mint("json_option")


# ── generate/2 on a cell (spec §9.2: type_error, not a stdlib TypeError) ─


class TestGenerateRejectsCells:
    def test_generate_of_a_compound_cell_is_a_type_error(self):
        with pytest.raises(LogicException) as exc:
            _clausal_to_python(("point", 1, 2))
        assert cell_functor(cell_args(exc.value.term)[0]) == "type_error"
        assert cell_args(cell_args(exc.value.term)[0])[0] == mint("json_term")

    def test_generate_of_an_atom_cell_is_its_spelling(self):
        assert _clausal_to_python(mint("red")) == "red"

    def test_generate_of_a_dict_with_atom_keys(self):
        assert _clausal_to_python(DictTerm({mint("k"): mint("v")})) == {"k": "v"}

    def test_a_compound_cell_KEY_is_a_type_error_not_a_silent_failure(self):
        # The key arm must go through the same converter as the value arm:
        # routing keys through ``to_python`` would hand json.dumps a tuple
        # key, whose stdlib TypeError the wrapper swallows into a plain
        # failure with no note.
        with pytest.raises(LogicException) as exc:
            _clausal_to_python(DictTerm({("point", 1, 2): 1}))
        assert cell_functor(cell_args(exc.value.term)[0]) == "type_error"
        assert cell_args(cell_args(exc.value.term)[0])[0] == mint("json_term")

    def test_a_tuple_tag_data_cell_serialises_as_an_array(self):
        # Only a str-functor cell of arity >= 1 is a json_term type_error.
        # Tuple DATA is content, not a compound, and keeps its array reading.
        from clausal.logic.cells import TUPLE_TAG, make_tuple_cell
        cell = make_tuple_cell(1, mint("red"))
        assert cell[0] is TUPLE_TAG
        assert _clausal_to_python(cell) == [1, "red"]

    def test_a_plain_non_cell_tuple_serialises_as_an_array(self):
        assert _clausal_to_python((1, 2)) == [1, 2]
        assert _clausal_to_python(()) == []

    def test_generate_2_emits_arrays_for_the_non_cell_tuple_shapes(self):
        # End-to-end through the predicate, not just the converter.
        from clausal.logic.cells import make_tuple_cell
        s = Var()
        sols, _ = simple_solutions(_generate_2, make_tuple_cell(1, 2), s)
        assert len(sols) == 1
        assert deref(s) == chars("[1, 2]")

    def test_the_type_error_context_names_the_calling_predicate(self):
        # One converter serves generate/2, pretty_generate/2, write_file/2
        # and py.http.json_post/3; the error must say which one failed.
        # The context reads back as writeq writes the indicator, so a
        # dotted name is quoted.
        for context, written in (
                ("py.json.generate/2", "'py.json.generate'/2"),
                ("py.json.pretty_generate/2", "'py.json.pretty_generate'/2"),
                ("py.json.write_file/2", "'py.json.write_file'/2"),
                ("py.http.json_post/3", "'py.http.json_post'/3")):
            with pytest.raises(LogicException) as exc:
                _clausal_to_python(("point", 1, 2), context)
            assert error_context_text(exc.value.term) == written

    def test_pretty_generate_and_write_file_carry_their_own_context(self, tmp_path):
        with pytest.raises(LogicException) as exc:
            list(_pretty_generate_2(("point", 1, 2), Var(), Trail(), None))
        assert error_context_text(exc.value.term) == "'py.json.pretty_generate'/2"

        path = str(tmp_path / "out.json")
        with pytest.raises(LogicException) as exc:
            list(_write_file_2(chars(path), ("point", 1, 2), Trail(), None))
        assert error_context_text(exc.value.term) == "'py.json.write_file'/2"
