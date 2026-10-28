"""The tooling's operator tables against Scryer's own.

``tests/fixtures/scryer_operators.json`` is ``current_op/3`` from
scryer-prolog v0.10.0-137-ge80dbcf1 (2026-10-28): ``bare`` with no library
loaded, ``clpz`` after ``:- use_module(library(clpz))``.  Scryer is the
reference dialect (operator ruling 2026-10-28), so the ``scryer`` tables
are exactly these, except Scryer's internal ``non_counted_backtracking``
(700 fx), which is left out: ``scryer_builtin_default`` is also the
engine's writeq table, and that operator is not part of any library a
program uses.  The ISO table has ``div`` (400 yfx, ISO Cor.2).
"""
import json
from pathlib import Path

import pytest

from clausal.tools.prolog_operators import OperatorTable

_SCRYER = json.loads(
    (Path(__file__).parent / "fixtures" / "scryer_operators.json").read_text())
_INTERNAL = {(700, "fx", "non_counted_backtracking")}


def _ops(table):
    return {(e.precedence, e.specifier, e.name) for e in table.entries()}


def _scryer(which):
    return {tuple(e) for e in _SCRYER[which]} - _INTERNAL


@pytest.mark.parametrize("table, which", [
    (OperatorTable.scryer_builtin_default, "bare"),
    (OperatorTable.scryer_default, "clpz"),
])
def test_scryer_tables_are_scryers(table, which):
    ours, theirs = _ops(table()), _scryer(which)
    assert (sorted(theirs - ours), sorted(ours - theirs)) == ([], [])


def test_iso_has_div():
    assert (400, "yfx", "div") in _ops(OperatorTable.iso_default())


def test_iso_is_within_scryer_without_libraries():
    assert _ops(OperatorTable.iso_default()) <= _scryer("bare")


def test_a_scryer_dialect_file_reads_clpz_operators():
    from clausal.tools.prolog_dialect import Dialect
    t = Dialect.scryer().operator_table
    for name, spec in [("in", "xfx"), ("ins", "xfx"), ("..", "xfx"),
                       ("#<==>", "yfx"), ("#\\", "fy"), ("div", "yfx")]:
        found = (t.lookup_prefix(name) if spec[0] == "f"
                 else t.lookup_infix(name))
        assert found is not None and found.specifier == spec, name


def test_the_scryer_dialect_writes_with_the_builtin_table_only():
    # A file holding in(a, b) as data that does not load library(clpz)
    # must read back, in Scryer and in Trealla: a library's operators are
    # canonical on output; div, rdiv and prefix + (built into both) are not.
    from clausal.tools.prolog_dialect import Dialect
    from clausal.tools.clausal_to_prolog import emit_term
    from clausal.tools.prolog_ast import PCompound, PAtom, PVar
    d = Dialect.scryer()
    assert _ops(d.writer_table()) == _scryer("bare")
    w = d.writer_table()
    assert emit_term(PCompound("in", (PAtom("mother"), PAtom("p"))), w) \
        == "in(mother, p)"
    assert emit_term(PCompound("div", (PVar("A"), PVar("B"))), w) == "A div B"


def test_other_dialects_write_with_their_read_table():
    from clausal.tools.prolog_dialect import Dialect
    d = Dialect.iso()
    assert d.writer_table() is d.operator_table
