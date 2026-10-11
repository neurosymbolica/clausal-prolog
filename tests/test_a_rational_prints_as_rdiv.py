"""A rational prints as Scryer prints it, ``N rdiv D``, in every writer.

It used to print as Python's ``Fraction(1, 2)`` everywhere but a bare
``writeq/1`` (2026-10-11).  ``1 rdiv 2`` reads back as the same rational;
inside a tighter operator it is bracketed (``2*(1 rdiv 2)``), where Scryer
writes ``2*1 rdiv 2``, which reads back as ``(2*1) rdiv 2``.
"""

from fractions import Fraction as F

import pytest

from clausal.logic.builtins.io import _format_term_iso, _term_canonical
from clausal.terms import term_str, term_writeq


@pytest.mark.parametrize("term, writeq, canonical", [
    (F(1, 2), "1 rdiv 2", "rdiv(1,2)"),
    (F(-3, 2), "-3 rdiv 2", "rdiv(-3,2)"),
    (("-", F(1, 2), 1), "1 rdiv 2-1", "-(rdiv(1,2),1)"),
    (("*", 2, F(1, 2)), "2*(1 rdiv 2)", "*(2,rdiv(1,2))"),
    (("-", 1, F(-3, 2)), "1- -3 rdiv 2", "-(1,rdiv(-3,2))"),
    (("f", F(1, 3)), "f(1 rdiv 3)", "f(rdiv(1,3))"),
    ([F(1, 2)], "[1 rdiv 2]", "'.'(rdiv(1,2),[])"),
])
def test_every_writer(term, writeq, canonical):
    assert term_writeq(term) == writeq
    assert _format_term_iso(term, quoted=True) == writeq
    assert _format_term_iso(term, quoted=False) == writeq
    assert _term_canonical(term) == canonical
    assert "Fraction" not in term_str(term)
