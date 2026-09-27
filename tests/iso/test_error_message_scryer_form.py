"""A ``LogicException``'s message shows the error term as Scryer prints it.

Ruling R2 of the Compound retirement (2026-09-27): the message is
``Uncaught logic exception: <term>`` where ``<term>`` is what Scryer's toplevel
prints for an uncaught error -- ``writeq`` text with operator syntax, no space
after a comma, ``"..."`` for a string, a distinct ``_N`` per variable -- not the
Python ``repr`` of the object.  So the message reads the same whether the term
is a ``Compound`` or the cell it is becoming.

Two halves, per ``tests/iso/conftest.py``: the ENGINE table runs anywhere; the
ORACLE test feeds the same rows to Scryer and checks that the expected column
is what Scryer really prints.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import (
    LogicException, domain_error, evaluation_error, existence_error,
    instantiation_error, permission_error, type_error,
)
from clausal.logic.variables import Var
from clausal.terms import (
    Add, Compound, ConcreteSeg, FloorDiv, SegList, VarSeg, term_writeq,
)

from .conftest import SCRYER

_X, _Y = Var(), Var()


def _pi(name, arity):
    return ("/", name, arity)


#: (Prolog source of the term as Scryer reads it, the engine term, what
#: Scryer's toplevel prints for ``throw(error(<term>, c))``).
ROWS = [
    ("type_error(evaluable,(+)/2)", ("type_error", "evaluable", _pi("+", 2)),
     "type_error(evaluable,(+)/2)"),
    ("(is)/2", _pi("is", 2), "(is)/2"),
    ("instantiation_error", "instantiation_error", "instantiation_error"),
    ("existence_error(procedure,foo/0)",
     ("existence_error", "procedure", _pi("foo", 0)),
     "existence_error(procedure,foo/0)"),
    ("domain_error(not_less_than_zero,-1)",
     ("domain_error", "not_less_than_zero", -1),
     "domain_error(not_less_than_zero,-1)"),
    ("evaluation_error(zero_divisor)", ("evaluation_error", "zero_divisor"),
     "evaluation_error(zero_divisor)"),
    ("(/)/2", _pi("/", 2), "(/)/2"),
    ("type_error(integer,'hello world')",
     ("type_error", "integer", "hello world"),
     "type_error(integer,'hello world')"),
    ('type_error(integer,"ab")', ("type_error", "integer", chars("ab")),
     'type_error(integer,"ab")'),
    ("f(X,Y,X)", ("f", _X, _Y, _X), "f(_1,_2,_1)"),
    ("[1,2|_]", SegList([ConcreteSeg([1, 2]), VarSeg(Var())]), "[1,2|_1]"),
    ("-(1)", ("-", 1), "- (1)"),
    ("-(1.0)", ("-", 1.0), "- (1.0)"),
    ("-(-(1))", ("-", ("-", 1)), "- - (1)"),
    ("-(-1)", ("-", -1), "- -1"),
    ("a-(-1)", ("-", "a", -1), "a- -1"),
    ("1-(-(1))", ("-", 1, ("-", 1)), "1- - (1)"),
    ("-(-(a))", ("-", ("-", "a")), "- -a"),
    ("\\+a", ("\\+", "a"), "\\+a"),
    ("-(a+b)", ("-", ("+", "a", "b")), "- (a+b)"),
    ("(a:-b,c;d->e)",
     (":-", "a", (";", (",", "b", "c"), ("->", "d", "e"))), "(a:-b,c;d->e)"),
    ("a*(b+c)", ("*", "a", ("+", "b", "c")), "a*(b+c)"),
    ("1-(2-3)", ("-", 1, ("-", 2, 3)), "1-(2-3)"),
    ("(1-2)-3", ("-", ("-", 1, 2), 3), "1-2-3"),
    ("2^3^4", ("^", 2, ("^", 3, 4)), "2^3^4"),
    ("(2^3)^4", ("^", ("^", 2, 3), 4), "(2^3)^4"),
    ("(-(1))^2", ("^", ("-", 1), 2), "(- (1))^2"),
    ("(-1)^2", ("^", -1, 2), "-1^2"),
    ("a=(b=c)", ("=", "a", ("=", "b", "c")), "a=(b=c)"),
    ("(a=b)=c", ("=", ("=", "a", "b"), "c"), "(a=b)=c"),
    ("X is Y", ("is", _X, _Y), "_1 is _2"),
    ("a mod b", ("mod", "a", "b"), "a mod b"),
    ("1 rdiv 2", ("rdiv", 1, 2), "1 rdiv 2"),
    ("2** -1", ("**", 2, -1), "2** -1"),
    ("(:-a)", (":-", "a"), "(:-a)"),
    ("-(mod)", ("-", "mod"), "- (mod)"),
    ("(-)-(-)", ("-", "-", "-"), "(-)-(-)"),
    ("+(1)", ("+", 1), "+1"),
    ("{a,b}", ("{}", (",", "a", "b")), "{a,b}"),
    ("f(',',;,!,[],{},+)", ("f", ",", ";", "!", "[]", "{}", "+"),
     "f(',',;,!,[],{},+)"),
    ("'A b'(x)", ("A b", "x"), "'A b'(x)"),
    ("[a,'B',\"c\"]", ["a", "B", chars("c")], "[a,'B',\"c\"]"),
    ("[a,b]", ["a", "b"], '"ab"'),
    ("'/*'", "/*", "'/*'"),
    ("'don''t'", "don't", "'don\\'t'"),
    ("f('\\n','\\x1\\')", ("f", "\n", "\x01"), "f('\\n','\\x1\\')"),
    ("f(1.0e22,1.5e-7,0.00001,0.0001,1.0e16,100.0)",
     ("f", 1.0e22, 1.5e-7, 0.00001, 0.0001, 1.0e16, 100.0),
     "f(1.0e22,1.5e-7,0.00001,0.0001,1.0e16,100.0)"),
    ("'$VAR'(1)", ("$VAR", 1), "B"),
    ("foo:bar(x)", (":", "foo", ("bar", "x")), "foo:bar(x)"),
]


def _norm_vars(s: str) -> str:
    seen: dict[str, str] = {}
    return re.sub(r"_\d+", lambda m: seen.setdefault(m.group(0), f"_{len(seen) + 1}"), s)


@pytest.mark.parametrize("src,term,expected", ROWS, ids=[r[0] for r in ROWS])
def test_engine_renders_as_scryer(src, term, expected):
    got = term_writeq(("error", term, "c"))
    assert _norm_vars(got) == f"error({expected},c)"


def test_oracle_prints_the_expected_column(scryer):
    """Scryer's toplevel prints every row's expected column."""
    del scryer   # the fixture only asserts the binary is there
    stdin = "".join(f"throw(error({src},c)).\n" for src, _, _ in ROWS)
    out = subprocess.run([SCRYER], input=stdin, capture_output=True,
                         text=True, timeout=60).stdout.splitlines()
    got = [_norm_vars(line.strip().removesuffix(".")) for line in out if line.strip()]
    want = [f"error({exp},c)" for _, _, exp in ROWS]
    assert len(got) == len(want) == len(ROWS) > 0
    assert got == want


# ── the message ──────────────────────────────────────────────────────────────

def _msg(term) -> str:
    return str(LogicException(term)).split("\n", 1)[0]


def test_message_is_the_scryer_text_not_the_repr():
    msg = _msg(type_error("evaluable", Compound("/", (mint("+"), 2)), "is/2"))
    assert msg == ("Uncaught logic exception: "
                   "error(type_error(evaluable,(+)/2),context((is)/2,_))")
    assert "Compound(" not in msg


BUILDERS = [
    lambda: type_error("integer", "x", "arg/3"),
    lambda: instantiation_error("atom_length/2"),
    lambda: existence_error("procedure", Compound("/", (mint("foo"), 0)), "foo/0"),
    lambda: domain_error("not_less_than_zero", -1, "atom_length/2"),
    lambda: evaluation_error("zero_divisor", "(/)/2"),
    lambda: permission_error("modify", "static_procedure", Compound("/", ("p", 1))),
]


def _as_compound(t):
    """The ``Compound`` spelling of a cell-built term, recursively -- what a
    Python caller that still builds ``Compound``s would raise."""
    if type(t) is tuple and t and type(t[0]) is str:
        return Compound(t[0], tuple(_as_compound(a) for a in t[1:]))
    return t


@pytest.mark.parametrize("build", BUILDERS)
def test_compound_and_cell_spellings_give_the_same_message(build):
    cell = build()
    assert type(cell) is tuple      # slice 2: the builders build cells
    term = _as_compound(cell)
    assert isinstance(term, Compound)
    assert _msg(term) == _msg(cell)
    assert _msg(term).startswith("Uncaught logic exception: error(")


def test_operator_node_culprit_uses_its_iso_functor():
    msg = _msg(type_error("number", FloorDiv(left=10000, right=4), "sum_list/2"))
    assert msg == ("Uncaught logic exception: "
                   "error(type_error(number,10000//4),context(sum_list/2,_))")
    assert "a+1" in _msg(("f", Add(left="a", right=1)))


def test_an_unrenderable_term_falls_back_to_repr():
    """Building an exception must never raise on top of the error."""
    class Weird:
        op = "+"
        @property
        def left(self):
            raise RuntimeError("boom")
        right = 1
    msg = _msg(Weird())
    assert msg.startswith("Uncaught logic exception: <")
