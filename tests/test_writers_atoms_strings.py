"""Spec §6.7: display of atoms (arity-0 cells), strings and chars.

Builtin goals are cell-shaped tuples, and ``solve/1`` (module=None) refuses
an unqualified cell goal outright, so the write-family probes run against a
throwaway loaded module — the same convention ``tests/test_atoms_as_cells.py``
and ``tests/test_double_quotes_directive.py`` use.
"""
import contextlib
import io
import re
import os
import tempfile

import pytest

from clausal.logic.atoms import char_atom, mint
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
    # A lone `.` is the end token -- quoted, though longer graphic runs
    # containing a dot (`=..` above) stay bare.
    (".", False),
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
    # ...while the proper 2-element list keeps its ``[]`` terminator.  The
    # variable's number is its engine identity, so it is matched, not pinned.
    assert re.fullmatch(r"'\.'\(1,'\.'\(_\d+,\[\]\)\)", term_canonical([1, Var()]))


def test_term_canonical_partial_string_walks_to_chars():
    """A ``SegString`` is walked first and prints as the cons chain of its
    chars with the hole as the tail (spec §6.7)."""
    from clausal.terms import term_canonical, SegString, VarSeg
    from clausal.logic.variables import Var
    out = term_canonical(SegString(["he", VarSeg(Var())]))
    assert re.fullmatch(r"'\.'\(h,'\.'\(e,_\d+\)\)", out), out


def test_term_str_hidden_atom_display_unchanged():
    assert term_str(("m\x1fbar",)) == "m.bar"


def test_term_canonical_has_no_operator_forms():
    """§6.7: canonical output has no operator syntax and no spaces — an
    operator node prints as the ``op(...)`` term it is.  Node fields are
    ``position, left, right``, so the operands must be passed by keyword."""
    from clausal.terms import Add, Div, Mod, Mult, Negate, term_canonical
    assert term_canonical(Div(left=("foo",), right=2)) == "/(foo,2)"
    assert term_canonical(Add(left=1, right=Mult(left=2, right=3))) == "+(1,*(2,3))"
    # ISO spells `%` as mod/2 (9.1.3); a unary operator prints as `-(3)`.
    assert term_canonical(Mod(left=7, right=2)) == "mod(7,2)"
    assert term_canonical(Negate(operand=3)) == "-(3)"


@pytest.mark.parametrize("node_name,functor", [
    ("Lt", "<"),
    ("Gt", ">"),
    ("LtE", "=<"),          # ISO spells `<=` as `=<`
    ("GtE", ">="),
    ("StructuralEq", "=="),      # Prolog ==/2
    ("StructuralNeq", "\\=="),   # Prolog \==/2
    ("ArithEq", "=:="),          # Prolog =:=/2
    ("ArithNeq", "=\\="),        # Prolog =\=/2
])
def test_term_canonical_comparison_functors(node_name, functor):
    """Every comparison node prints as the ISO functor it denotes — the four
    whose Python surface spelling differs (`<=`, `==`, `!=` twice over) and
    the four that pass straight through."""
    from clausal.pythonic_ast import nodes as simple_ast
    from clausal.terms import term_canonical
    node = getattr(simple_ast, node_name)(left=1, right=2)
    assert term_canonical(node) == functor + "(1,2)"


def test_term_canonical_numbers_variables_are_distinct():
    """§6.7: distinct variables print distinctly (``f(X,X,Y)`` is not
    ``f(_,_,_)``), which ISO/Scryer spell ``_N``."""
    from clausal.terms import term_canonical
    from clausal.logic.variables import Var
    X, Y = Var(), Var()
    out = term_canonical(("f", X, X, Y))
    args = out[len("f("):-1].split(",")
    assert args[0] == args[1] != args[2]
    assert all(a.startswith("_") for a in args)


def test_term_canonical_never_colours():
    """Canonical output exists to be compared byte for byte, so it carries
    no ANSI even when a colouring style is current."""
    from clausal.terms import ANSI_COLORS, TermStyle, get_style, set_style, term_canonical
    from clausal.logic.variables import Var
    previous = get_style()
    try:
        set_style(TermStyle(colors=ANSI_COLORS))
        assert "\x1b" not in term_canonical(("f", 1))
        assert term_canonical(("f", 1)) == "f(1)"
        assert "\x1b" not in term_canonical(("f", Var(), [1, ("a",)]))
    finally:
        set_style(previous)


def test_lone_dot_atom_is_quoted():
    """The end-token hazard: a lone ``.`` atom must re-read as an atom."""
    from clausal.terms import term_canonical
    assert quote_atom(".") == "'.'"
    assert term_str((".",)) == "'.'"
    assert term_canonical((".",)) == "'.'"
    # ...and a cell whose functor is spelled `.` is just that cell (§5.4).
    assert term_canonical((".", 1, 2)) == "'.'(1,2)"


def test_writer_helpers_are_exported():
    import clausal.terms as terms_mod
    for name in ("term_canonical", "atom_needs_quotes", "quote_atom", "quote_string"):
        assert name in terms_mod.__all__
