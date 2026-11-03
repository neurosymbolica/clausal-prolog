"""A clause head qualified with the file's OWN module defines the predicate.

``m:foo(1).`` in a file whose module/2 names ``m`` is a clause of ``foo/1``
in ``m``, as in Scryer; the native front end used to load it as a clause of
``(:)/2`` (todo/a-module-qualified-clause-head-defines-colon-2-2026-10-24.md).

Scryer (the oracle build, 2026-11-03), file ``a.pl``::

    :- module(a, [t/1]).
    t(X) :- a:baz(X).
    a:baz(7).

    ?- t(X).          X = 7.
    ?- a:baz(X).      X = 7.

The directives taking predicate indicators read ``m:p/N`` the same way:
Scryer accepts ``:- dynamic(dm:d/1).`` and ``:- discontiguous(dm:e/1).`` in
module ``dm``.  (Its ``table/1`` refuses any qualified indicator,
``domain_error(directive, (table)/1)``; it is accepted here, consistently
with the heads.)  ``m:p/N`` reads as ``(m:p)/N``; ``m:(p/N)`` is accepted
too.

And a grammar rule ``c:g --> [a].`` in module ``c`` defines ``g//0``
(``phrase(c:g, [a])`` succeeds).

A head qualified with ANOTHER module (``b:qux(8).`` in ``a``, or ``m:foo``
in a file with no module/2) is not settled here: Scryer adds the clause to
that module, and what Clausal should do with it is an open question in the
todo file.
"""
from __future__ import annotations

import sys
import textwrap
import warnings

import pytest

from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

_BODY = """\
:- dynamic(NAME:d/1).
:- discontiguous((edge/2, NAME:dis/1)).
:- table([NAME:(path/2)]).
NAME:foo(1).
foo(2).
NAME:foo(3).
NAME:NAME:deep(4).
NAME:bar(X) :- foo(X), X > 1.
t(X) :- NAME:bar(X).
q(X) :- deep(X).
NAME:greeting --> [hello], NAME:name.
name --> [world].
greets(L) :- phrase(greeting, L).
dis(1).
add(X) :- assertz(d(X)).
dis(2).
edge(1, 2).
edge(2, 1).
path(X, Y) :- path(X, Z), edge(Z, Y).
path(X, Y) :- edge(X, Y).
"""


def _load(tmp_path, monkeypatch, name, suffix, text):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}{suffix}"
    path.write_text(textwrap.dedent(text).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _load_module(name, str(path))


@pytest.fixture(params=[".pl", ".clausal"])
def mod(request, tmp_path, monkeypatch):
    suffix = request.param
    name = f"mqh_{suffix[1:]}"
    text = (f":- module({name}, [foo/1, bar/1, t/1, q/1, greets/1, add/1, d/1, dis/1, path/2]).\n"
            + _BODY.replace("NAME", name))
    if suffix == ".clausal":
        text += f":- end_module({name}).\n"
    m = _load(tmp_path, monkeypatch, name, suffix, text)
    try:
        yield m.__dict__["$module"]
    finally:
        sys.modules.pop(name, None)


def _answers(db, name, n):
    args = tuple(Var() for _ in range(n))
    return [tuple(_deref_walk(a) for a in args)
            for _ in solve((name, *args), db)]


def test_own_qualified_facts_join_the_unqualified_clauses(mod):
    assert _answers(mod, "foo", 1) == [(1,), (2,), (3,)]


def test_own_qualified_rule_head(mod):
    assert _answers(mod, "bar", 1) == [(2,), (3,)]
    assert _answers(mod, "t", 1) == [(2,), (3,)]


def test_doubly_qualified_head(mod):
    assert _answers(mod, "q", 1) == [(4,)]


def test_no_colon_2_is_defined(mod):
    assert ":" not in mod.db._clauses and (":", 2) not in mod.db._clauses


def test_own_qualified_grammar_rule_head(mod):
    assert _answers(mod, "greets", 1) == [(["hello", "world"],)]



def test_own_qualified_dynamic_directive(mod):
    assert _answers(mod, "d", 1) == []
    assert len(list(solve(("add", 5), mod))) == 1
    assert _answers(mod, "d", 1) == [(5,)]


def test_own_qualified_discontiguous_directive(mod):
    assert mod.db.is_discontiguous("dis", 1)
    assert mod.db.is_discontiguous("edge", 2)
    assert _answers(mod, "dis", 1) == [(1,), (2,)]


def test_own_qualified_dynamic_and_table_marks(mod):
    assert mod.db.is_dynamic("d", 1)
    assert mod.db.is_tabled("path", 2)


def test_own_qualified_table_directive(mod):
    # Left recursion over a cycle terminates only if path/2 is tabled.
    assert sorted(_answers(mod, "path", 2)) == [(1, 1), (1, 2), (2, 1),
                                                (2, 2)]


def test_own_qualified_constants_table_indicator(tmp_path, monkeypatch):
    name = "mqh_ct"
    m = _load(tmp_path, monkeypatch, name, ".pl", f"""\
        :- module({name}, [bands/3]).
        :- use_module(european_union, [euro]).
        :- constants_number_units({name}:bands/3, [[low, 1, 10]],
                                  euro, number_at(3)).
        """)
    try:
        db = m.__dict__["$module"]
        [(band, n, _q)] = _answers(db, "bands", 3)
        assert (band, n) == ("low", 1)
    finally:
        sys.modules.pop(name, None)
