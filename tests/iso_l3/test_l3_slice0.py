"""Slice 0 remainder (plan native-iso-reader-step2 §4): P1 fails closed.

* The reader's operator table is Scryer's, not SWI's (D2(b); "ISO first, then
  Scryer, never SWI"): ``read_iso`` reads with ``Dialect.scryer_reader()``'s
  table, and ``PrologReader``'s own fallback is ``scryer_builtin_default``.
* A reader ``SyntaxIssue`` is a refusal that names the ``.pl`` line.
* The dead ``_is_atom`` branch is gone, and no message claims strings are
  handled when they are not.
"""
from __future__ import annotations

import pytest

from clausal.tools import iso_l3 as L3
from clausal.tools.prolog_reader import PrologReader, read_module


def _kinds(items):
    return [type(i).__name__ for i in items]


def test_read_iso_uses_the_scryer_table_so_prefix_dynamic_is_a_syntax_error():
    # Scryer: `:- dynamic d/1.` is syntax_error(incomplete_reduction) --
    # `dynamic` is no prefix operator there.  SWI's table read it.
    assert _kinds(L3.read_iso(":- dynamic d/1.\n")) == ["SyntaxIssue"]
    assert _kinds(L3.read_iso(":- dynamic(d/1).\n")) == ["Directive"]


def test_read_iso_has_scryer_builtin_ops_and_no_swi_ones():
    # `rdiv` yfx 400 is a Scryer builtin op; `*->` is SWI-only.
    [item] = L3.read_iso("f(X) :- X is 1 rdiv 2.\n")
    assert type(item).__name__ == "Clause"
    assert _kinds(L3.read_iso("f :- (a *-> b ; c).\n")) == ["SyntaxIssue"]


def test_read_iso_gets_a_fresh_table_each_call():
    # op/3 in one file must not leak into the next file's reading.
    L3.read_iso(":- op(700, xfx, ===>).\nf(a ===> b).\n")
    assert _kinds(L3.read_iso("g(a ===> b).\n")) == ["SyntaxIssue"]


def test_prolog_reader_fallback_table_is_scryer_not_swi():
    from clausal.tools.prolog_operators import OperatorTable
    fallback = PrologReader().op_table
    scryer = OperatorTable.scryer_builtin_default()
    assert fallback.lookup_prefix("dynamic") is None
    assert fallback.lookup_infix("*->") is None
    assert fallback.lookup_infix("rdiv") == scryer.lookup_infix("rdiv")
    assert _kinds(read_module(":- dynamic d/1.\n")) == ["SyntaxIssue"]


def test_a_syntax_issue_is_refused_with_its_pl_line():
    src = "f(1).\n\ng(.\nh(2).\n"
    items = L3.read_iso(src)
    assert "SyntaxIssue" in _kinds(items)
    with pytest.raises(L3.LoweringRefused, match=r"m\.pl:3: .*syntax error"):
        L3.lower_items(items, source=src, filename="m.pl")


def test_a_refused_directive_names_its_pl_line():
    src = "f(1).\n:- dynamic(d/1).\n"
    with pytest.raises(L3.LoweringRefused, match=r"m\.pl:2: Directive"):
        L3.lower_items(L3.read_iso(src), source=src, filename="m.pl")


def test_the_dead_is_atom_branch_is_gone():
    assert not hasattr(L3, "_is_atom")


def test_no_message_claims_strings_are_handled_when_they_are_refused():
    import inspect
    assert "atoms, integers, strings and lists" not in inspect.getsource(L3)
