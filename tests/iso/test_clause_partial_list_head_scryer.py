"""clause/2 and retract/1 on clauses whose HEAD holds a partial list, row by
row against Scryer, on every surface.

A head list pattern ``[H|T]`` is stored as the compiler's pattern
``[H, StarUnpack(T)]``.  ``clause_ops.clause_terms`` (shared by clause/2 and
retract/1) handed that pattern back as the Head, a Python list holding an
AST node, which unifies with no term: ``clause(p([a,b], X), B)`` on a
dynamic ``p([H|T], H-T)`` found nothing, and ``clause(p(L, X), true)``
bound ``L`` to ``[_, StarUnpack(_)]``.  The Head is now the list term the
pattern spells (the engine's partial list), sharing its tail with the body.

Each row is one clause body run under Clausal (``.pl`` native, ``.pl``
translator, ``.clausal``) and under Scryer, from the same text; both must
write the expected column.  The retract rows change the database, so each
engine row loads its own module.
"""
from __future__ import annotations

import os
import re
from itertools import count

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.import_hook import _load_module
from clausal.logic.solve import solve

from tests._oracles import run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]

_PROGRAM = """\
:- dynamic(p/2).
:- dynamic(n/1).
:- dynamic(q/1).
:- dynamic(rt/1).
:- dynamic(rb/1).
:- dynamic(sq/1).
:- dynamic(ss/1).
p([H|T], H-T).
p([a|_], x).
p([a,b|T], T).
n([a,[b|T]|T]).
n(f([_|Y], Y)).
n([g([_|Y])|Y]).
q([H|T]) :- r([H|T]), w([x|T]).
rt([_|_]).
rt([zz]).
rb([H|T]) :- w([H|T]).
sq([a|T]) :- w("ab"), w([x|T]).
ss([x|"ab"]).
ss([y,z|T]) :- w(T).
r(_).
w(_).
"""

# (row name, a body binding R, what both engines write for R)
ROWS = [
    # the reported case: a bound list selects the [H|T] clause
    ("bound_list_selects", "findall(X-B, clause(p([a,b], X), B), R)",
     "[a-[b]-true,x-true,[]-true]"),
    # an unbound head reads back as the partial list, tail shared with X
    ("head_reads_back", "findall(L-X, clause(p(L, X), true), R)",
     "[[_|_]-(_-_),[a|_]-x,[a,b|_]-_]"),
    ("tail_is_shared",
     "clause(p(L, X), true), L = [1|T], X == 1-T, R = yes", "yes"),
    ("closed_list_meets_partial",
     "findall(Q-1, clause(p([Q], x), true), R)", "[a-1]"),
    # nested partial lists, one tail shared at two depths
    ("nested_shared_tail",
     "findall(B, clause(n([a,[b,c],c]), B), R)", "[true]"),
    ("nested_unbound_reads_back",
     "clause(n([a,L|T]), true), L = [b|U], U == T, R = yes", "yes"),
    # a partial list inside a compound argument (hoisted) and inside a
    # compound inside a list
    ("inside_compound", "clause(n(f([1,2], Z)), true), R = Z", "[2]"),
    ("compound_in_list", "findall(yes, clause(n([g([1,2]),2]), true), R)", "[yes]"),
    # a rule: the head and the body share the tail
    ("rule_body", "clause(q([1,2]), B), R = B", "r([1,2]),w([x,2])"),
    ("rule_unbound_head",
     "clause(q(L), (r(L2), w([x|T]))), L == L2, L = [_|T2], T == T2, R = yes",
     "yes"),
    # strings (double_quotes chars: lists of one-char atoms) in heads and
    # bodies
    ("string_in_body", "clause(sq([a,b]), B), R = B", 'w([a,b]),w([x,b])'),
    ("string_tail_head", "findall(L, clause(ss(L), true), R)", '[[x,a,b]]'),
    ("string_meets_partial",
     "findall(T, clause(ss([y,z,c,d]), w(T)), R)", '[[c,d]]'),
    # retract/1 reads clauses the same way
    ("retract_fact",
     "retract(rt([1,2])), findall(L, clause(rt(L), true), R)", "[[zz]]"),
    ("retract_rule", "retract((rb([1,2]) :- B)), R = B", "w([1,2])"),
]

_ROWS_TEXT = "".join(f"row_{n}(R) :- {b}.\n" for n, b, _ in ROWS) + "".join(
    f"show_{n} :- row_{n}(R), writeq(R), nl.\n" for n, _b, _ in ROWS)

_VARNAME = re.compile(r"\b_[A-Za-z0-9_]*\b")


def _normalise(text: str) -> str:
    return _VARNAME.sub("_", text.strip())


_COUNTER = count()

#: Rows the legacy ``.pl`` translator answers in the seam's spelling: it
#: hands a rule's conjunction back as the plain tuple
#: ``(('r', [1, 2]), ('w', ['x', 2]))``, for every rule, partial lists or
#: not (todo/pl-translator-clause-2-rule-body-is-the-seam-tuple-2026-11-04.md).
_TRANSLATOR_CONJUNCTION_ROWS = {"rule_body", "string_in_body"}

#: ``.pl`` through the native front end (the default) and the translator,
#: and ``.clausal``.
SURFACES = [(PL, "native"), (PL, "translator"), (CLAUSAL, "native")]
SURFACE_IDS = ["pl", "pl-translator", "clausal"]


@pytest.fixture(params=SURFACES, ids=SURFACE_IDS)
def surface(request, monkeypatch):
    suffix, frontend = request.param
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    return suffix


def test_clause_partial_list_head_engine(tmp_path, surface, capsys):
    """Every row on one surface; all failures named together.  The row
    writes its answer with the program's own writeq/1, as the Scryer row
    does."""
    failures = []
    translator = os.environ.get("CLAUSAL_PL_FRONTEND") == "translator"
    for name, _body, expected in ROWS:
        if translator and name in _TRANSLATOR_CONJUNCTION_ROWS:
            continue
        stem = f"_clause_partial_head_{next(_COUNTER)}"
        path = tmp_path / f"{stem}{surface}"
        path.write_text(_PROGRAM + _ROWS_TEXT, encoding="utf-8")
        capsys.readouterr()
        try:
            mod = _load_module(stem, str(path))
            for _ in solve(f"show_{name}", mod):
                pass
        except Exception as e:  # noqa: BLE001 -- named below
            failures.append(f"{name}: {type(e).__name__}: {e}")
            continue
        got = [_normalise(a) for a in capsys.readouterr().out.splitlines()
               if a.strip()]
        if got != [expected]:
            failures.append(f"{name}: {got!r}, expected [{expected!r}]")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("name,_body,expected", ROWS, ids=[r[0] for r in ROWS])
def test_clause_partial_list_head_scryer(scryer, tmp_path, name, _body, expected):
    del scryer
    path = tmp_path / "rows.pl"
    path.write_text(_PROGRAM + _ROWS_TEXT, encoding="utf-8")
    proc = run_scryer(str(path), [f"row_{name}(R), writeq(R), nl, halt."],
                      timeout=60)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert lines, (name, proc.stdout, proc.stderr[-500:])
    assert _normalise(lines[-1]) == expected
