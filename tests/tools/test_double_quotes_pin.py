"""Unit tests for tools/double_quotes_pin.py -- the classifier the docs
pass and the flip migration relied on (flip review, jobs 247/248)."""
import importlib.util
import os
import textwrap

import pytest

_TOOL = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "double_quotes_pin.py")
_spec = importlib.util.spec_from_file_location("double_quotes_pin", _TOOL)
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)


def _lits(src):
    """The classified literals in SOURCE order (the walk itself is a stack)."""
    found = d._dq_literals(src, "t.clausal")
    return [(n.value, dcg, tn) for n, dcg, tn in
            sorted(found, key=lambda t: (t[0].lineno, t[0].col_offset))]


class TestInsertionLine:
    def test_after_the_leading_comment_block(self):
        lines = ["# a\n", "# b\n", "\n", "p(1),\n"]
        assert d._insertion_line(lines) == 3

    def test_never_past_a_snippet_marker(self):
        lines = ["# Doc snippet fixtures\n", "\n", "# --8<-- [start:x]\n", "p(1),\n"]
        assert d._insertion_line(lines) == 2


class TestModeSensitiveLiteral:
    def test_a_double_quoted_string_token(self):
        assert d._has_mode_sensitive_literal('p("x"),\n')

    def test_not_a_bytes_literal(self):
        assert not d._has_mode_sensitive_literal('g >> (sequence(b"GET "))\n')

    def test_not_a_quote_in_a_comment(self):
        assert not d._has_mode_sensitive_literal("p('x'),  # say \"hi\"\n")


class TestRespell:
    @pytest.mark.parametrize("raw, want", [
        ('"x"', "'x'"),
        ('"a\'b"', "'a\\'b'"),
        ('"x\\"y"', "'x\"y'"),
        ('"a\\\\\'b"', "'a\\\\\\'b'"),       # backslash, apostrophe: both kept
    ])
    def test_simple_literals(self, raw, want):
        assert d._respell(raw) == want

    @pytest.mark.parametrize("raw", ['r"\\d"', '"""t"""', '"a" "b"', 'b"x"'])
    def test_shapes_it_leaves_alone(self, raw):
        assert d._respell(raw) is None


class TestLiteralClassification:
    def test_a_test_name_is_kept_and_its_body_converted(self):
        lits = _lits('test("n") <- p("a")\n')
        assert lits == [("n", False, True), ("a", False, False)]

    def test_a_python_escape_is_not_a_literal(self):
        assert _lits('p(X) <- (X is ++"py")\n') == []

    def test_a_python_escape_chain_is_python_throughout(self):
        assert _lits('p(T) <- (T is ++"Hello, " ++ NAME ++ "!")\n') == []

    def test_dcg_bare_terminal_is_kept_list_elements_follow_the_mode(self):
        lits = _lits('g >> ("abc", ["hello", X, f("b")], word("hi"), {Y == "z"})\n')
        assert lits == [("abc", True, False), ("hello", False, False),
                        ("b", False, False), ("hi", False, False), ("z", False, False)]

    def test_dcg_bare_terminal_under_or_and_not(self):
        lits = _lits('g >> ("a" or "b", not "c")\n')
        assert lits == [("a", True, False), ("b", True, False), ("c", True, False)]


class TestConvertFile:
    def test_a_file_that_does_not_parse_is_reported_not_raised(self, tmp_path, capsys):
        p = tmp_path / "bad.clausal"
        p.write_text('p("x") <- (\n')
        assert d.convert_file(str(p), check=True) == (0, 0)
        assert "does not parse" in capsys.readouterr().out
