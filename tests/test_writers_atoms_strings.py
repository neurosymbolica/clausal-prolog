"""Spec §6.7: display of atoms (arity-0 cells), strings and chars.

Builtin goals are cell-shaped tuples, and ``solve/1`` (module=None) refuses
an unqualified cell goal outright, so the write-family probes run against a
throwaway loaded module — the same convention ``tests/test_atoms_as_cells.py``
and ``tests/test_double_quotes_directive.py`` use.
"""
import contextlib
import io
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.terms import (
    atom_needs_quotes,
    quote_atom,
    term_html,
    term_pformat,
    term_str,
)
from clausal.logic.solve import solve


@pytest.fixture
def mod():
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write("z0,\n")
        path = f.name
    try:
        return _load_module("_writers_atoms_strings_probe", path).__dict__["$module"]
    finally:
        os.unlink(path)


@pytest.mark.parametrize("s,bare", [
    ("foo", True), ("fooBar_1", True), ("Foo", False), ("foo bar", False),
    ("", False), ("[]", True), ("{}", True), ("!", True), (";", True), (",", False),
    ("+", True), ("=..", True), ("hello-world", False), ("_x", False), ("1a", False),
])
def test_atom_needs_quotes(s, bare):
    assert atom_needs_quotes(s) is (not bare)


def test_quote_atom_escapes():
    assert quote_atom("it's") == r"'it\'s'"
    assert quote_atom("a\\b") == r"'a\\b'"
    assert quote_atom("a\nb") == r"'a\nb'"


def test_term_str_arity0_cell_is_bare_spelling():
    assert term_str(("flag",)) == "flag"
    assert term_str(("foo bar",)) == "'foo bar'"
    assert term_str(("foo", ("bar",), 1)) == "foo(bar, 1)"


def test_term_pformat_and_html_arity0():
    assert term_pformat(("flag",)) == "flag"
    assert "flag" in term_html(("flag",)) and "flag()" not in term_html(("flag",))


def test_write_family_prints_cell_atom_bare(mod):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("write", ("flag",)), mod))
        list(solve(("write", ("foo", ("foo bar",))), mod))
    assert buf.getvalue() == "flagfoo(foo bar)"


def test_writeq_quotes_and_write_canonical_is_cons_form(mod):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        list(solve(("writeq", ("foo bar",)), mod))
        list(solve(("write_canonical", ("foo", ("foo bar",), 1)), mod))
        list(solve(("write_canonical", [1, 2]), mod))
        list(solve(("write_canonical", []), mod))
    assert buf.getvalue() == "'foo bar'foo('foo bar',1)'.'(1,'.'(2,[]))[]"


def test_term_canonical_partial_list_and_nesting():
    from clausal.terms import term_canonical, ConcreteSeg, SegList, VarSeg
    from clausal.logic.variables import Var
    assert term_canonical(("f", [("a",), ("b c",)])) == "f('.'(a,'.'('b c',[])))"
    # A PARTIAL list is a SegList (spec §5.4: a Python list is always a
    # PROPER list), so ``[1 | T]`` -- not ``[1, X]`` -- is what renders with
    # the hole in the tail position: ``'.'(1,_N)``.
    t = term_canonical(SegList([ConcreteSeg([1]), VarSeg(Var())]))
    assert t.startswith("'.'(1,_") and t.endswith(")")
    # ...while the proper 2-element list keeps its ``[]`` terminator.
    assert term_canonical([1, Var()]) == "'.'(1,'.'(_,[]))"


def test_term_canonical_partial_string_walks_to_chars():
    """A ``SegString`` is walked first and prints as the cons chain of its
    chars with the hole as the tail (spec §6.7)."""
    from clausal.terms import term_canonical, SegString, VarSeg
    from clausal.logic.variables import Var
    assert term_canonical(SegString(["he", VarSeg(Var())])) == "'.'(h,'.'(e,_))"


def test_term_str_hidden_atom_display_unchanged():
    assert term_str(("m\x1fbar",)) == "m.bar"
