"""The quote map: recovering the quote character ``ast`` erases.

``ast.Constant`` carries the *value* of a string literal, never its spelling
— ``'foo'`` and ``"foo"`` are the same node.  The strings program needs the
distinction (single quotes are always an atom; double quotes follow the
module's ``-double_quotes`` mode), so the compiler rebuilds it from the token
stream, keyed by source position.  ``clausal/fmt/emit.py``'s
``_prefer_double_quotes`` is the precedent for tokenize-based quote recovery.

Positions are the join: ``tokenize`` reports CHARACTER columns while
``ast.col_offset`` is a UTF-8 BYTE offset, so the map stores byte columns.
"""

import ast

import pytest

from clausal.templating.quote_map import build_quote_map, quote_of


def _map_and_node(src):
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    node = tree.body[0].value
    return build_quote_map(lines), node


def test_single_and_double():
    qmap, node = _map_and_node("x = 'a'\n"[4:])
    assert quote_of(qmap, node) == "'"
    qmap, node = _map_and_node('"a"\n')
    assert quote_of(qmap, node) == '"'


def test_prefixes_and_triple():
    for src, q in (("r'a'\n", "'"), ('u"a"\n', '"'), ('"""a"""\n', '"'), ("b'x'\n", "'")):
        qmap, node = _map_and_node(src)
        assert quote_of(qmap, node) == q


def test_byte_offsets_after_non_ascii():
    qmap, node = _map_and_node('f("é", "b")\n')
    second = node.args[1]
    assert quote_of(qmap, second) == '"'


def test_implicit_concat_same_style_ok_mixed_raises():
    qmap, node = _map_and_node('"a" "b"\n')
    assert quote_of(qmap, node) == '"'
    qmap, node = _map_and_node('"a" \'b\'\n')
    with pytest.raises(SyntaxError):
        quote_of(qmap, node)


def test_fstrings_are_absent_and_quote_of_says_unknown():
    """An f-string is not a STRING token; it is also not a ``Constant``.

    The map has no entry at its position, and the "unknown" answer is
    ``None`` — never an exception, because every caller treats a missing
    entry as "no opinion" (see the ``source_lines=None`` paths below)."""
    src = 'f"{1}"\n'
    lines = src.splitlines(keepends=True)
    qmap = build_quote_map(lines)
    node = ast.parse(src).body[0].value
    assert isinstance(node, ast.JoinedStr)
    assert quote_of(qmap, node) is None


def test_no_source_lines_degrades_to_empty_map():
    """The REPL/IPython path builds no map; nothing may raise there."""
    assert build_quote_map([]) == {}
    node = ast.parse("'a'\n").body[0].value
    assert quote_of({}, node) is None


def test_synthetic_constant_is_unknown():
    """A programmatically built ``Constant`` has no position in any map."""
    qmap, _node = _map_and_node("'a'\n")
    assert quote_of(qmap, ast.Constant(value="a")) is None


def test_unreadable_source_yields_an_empty_map():
    """A tokenize failure is not this module's error to report — ``ast.parse``
    has already rejected (or will reject) the same text."""
    assert build_quote_map(["'unterminated\n"]) == {}


def test_multiline_triple_quoted_keys_both_ends():
    src = '"""a\nb"""\n'
    lines = src.splitlines(keepends=True)
    node = ast.parse(src).body[0].value
    qmap = build_quote_map(lines)
    assert quote_of(qmap, node) == '"'
