"""The output shape of ``clause_ops.clause_terms(clause, home_db)``.

clause/2 and retract/1 read clauses through it, and so do tools outside the
engine (explanation and provenance over a loaded program), so its contract
is pinned here (see the function's docstring):

- it returns ``(Head, Body, None)`` or ``(None, None, why)``;
- Head and Body are terms in the engine's runtime representation: no AST
  node of the stored head survives, and a partial list ``[H|T]`` is the
  engine's partial list (a ``SegList`` with an unbound tail), the term the
  compiled clause binds an argument to -- it was the head pattern
  ``[H, StarUnpack(T)]``, which unifies with nothing;
- Head and Body share their variables, and each call renames afresh.

Each source surface stores heads its own way, so each is checked: ``.pl``
through the native front end and the translator, ``.clausal``, and the
seam.
"""
from __future__ import annotations

from itertools import count

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES, PROLOG_SUFFIX, SEAM_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.builtins.clause_ops import clause_terms
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.pythonic_ast import nodes
from clausal.terms import SegList, term_writeq

_ISO = """\
:- dynamic(p/2).
:- dynamic(n/1).
:- dynamic(q/1).
:- dynamic(g/1).
p([H|T], pr(H, T)).
p([a,b|T], T).
p([a,b], c).
n([a,[b|T]|T]).
n(f([_|Y], Y)).
n([g([_|Y])|Y]).
q([H|T]) :- r([H|T]), w([x|T]).
g(X) :- w(X).
r(_).
w(_).
"""

_SEAM = """\
-module(_MOD_, [])
-dynamic(p/2)
-dynamic(n/1)
-dynamic(q/1)
-dynamic(g/1)
-private([a, b, c, x, f(A, B), g(A), pr(A, B), r, w])
p([H, *T], pr(H, T)),
p([a, b, *T], T),
p([a, b], c),
n([a, [b, *T], *T]),
n(f([_, *Y], Y)),
n([g([_, *Y]), *Y]),
q([H, *T]) <- (r([H, *T]), w([x, *T]))
g(X) <- w(X)
r(_),
w(_),
"""

SURFACES = [
    (PROLOG_SUFFIX, "native", _ISO),
    (PROLOG_SUFFIX, "translator", _ISO),
    (CLAUSAL_PROLOG_SUFFIXES[0], "native", _ISO),
    (SEAM_SUFFIX, "native", _SEAM),
]
SURFACE_IDS = ["pl", "pl-translator", "clausal", "seam"]

_COUNTER = count()


@pytest.fixture(params=SURFACES, ids=SURFACE_IDS)
def mod(request, tmp_path, monkeypatch):
    suffix, frontend, text = request.param
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    stem = f"_clause_terms_shape_{next(_COUNTER)}"
    path = tmp_path / f"{stem}{suffix}"
    path.write_text(text.replace("_MOD_", stem), encoding="utf-8")
    return _load_module(stem, str(path))


def _row(mod, name, arity):
    from clausal.logic.builtins.io import _indicator_row  # noqa: PLC0415
    db = mod.__dict__["$module"].db
    row = _indicator_row(db, name, arity, None)
    assert row is not None, (name, arity)
    return row


def _terms(mod, name, arity):
    row = _row(mod, name, arity)
    out = []
    for clause in row.clauses:
        h, b, why = clause_terms(clause, row.db)
        assert why is None, why
        out.append((h, b))
    return out


#: The compiler's head PATTERN nodes.  (A seam term may hold the seam's
#: operator nodes -- ``H - T`` is ``Sub`` -- which are terms there.)
_PATTERN_NODES = (nodes.StarUnpack, nodes.StarTarget, nodes.PatternList)


def _nodes_in(t, seen=None):
    """Every pattern node reachable from *t*, through bindings and
    SegLists."""
    from clausal.terms import ConcreteSeg  # noqa: PLC0415
    found, stack, seen = [], [t], set()
    while stack:
        x = deref(stack.pop())
        if id(x) in seen:
            continue
        seen.add(id(x))
        if isinstance(x, _PATTERN_NODES):
            found.append(x)
        elif isinstance(x, nodes.Node):
            stack.extend(getattr(x, f) for f in ("left", "right", "operand",
                                                 "value", "args")
                         if hasattr(x, f))
        elif isinstance(x, SegList):
            for seg in x.segments:
                stack.extend(seg.elements if isinstance(seg, ConcreteSeg)
                             else [seg.var])
        elif type(x) in (list, tuple):
            stack.extend(x)
    return found


def _vars_in(t):
    return {id(v) for v in _walk_vars(t)}


def _walk_vars(t):
    from clausal.terms import ConcreteSeg  # noqa: PLC0415
    stack, out = [t], []
    while stack:
        x = deref(stack.pop())
        if is_var(x):
            out.append(x)
        elif isinstance(x, SegList):
            for seg in x.segments:
                stack.extend(seg.elements if isinstance(seg, ConcreteSeg)
                             else [seg.var])
        elif type(x) in (list, tuple):
            stack.extend(x)
    return out


def test_no_pattern_node_in_any_head_or_body(mod):
    failures = []
    for name, arity in (("p", 2), ("n", 1), ("q", 1), ("g", 1)):
        for i, (h, b) in enumerate(_terms(mod, name, arity)):
            for what, t in (("head", h), ("body", b)):
                found = _nodes_in(t)
                if found:
                    failures.append(f"{name}/{arity} #{i} {what}: {found!r}")
    assert not failures, "\n".join(failures)


def test_a_partial_list_head_is_the_engines_partial_list(mod):
    (h, b), (h2, _), (h3, _) = _terms(mod, "p", 2)
    assert b is True
    lst = h[1]
    assert isinstance(lst, SegList), lst
    assert "|" in term_writeq(lst), term_writeq(lst)
    # the partial list's tail is the variable in the second argument
    pair = h[2]
    tail = pair[2]
    assert is_var(tail)
    assert id(deref(tail)) in _vars_in(lst)
    # a closed list head stays a proper list
    assert h3[1] == ["a", "b"] and h3[2] == "c"
    # [a,b|T] reads back with its prefix
    assert isinstance(h2[1], SegList)


def test_the_head_unifies_as_the_clause_does(mod):
    """``[H|T]`` meets ``[a,b]`` with H = a, T = [b]."""
    (h, _b), *_ = _terms(mod, "p", 2)
    trail = Trail()
    x = Var()
    assert unify(h, ("p", ["a", "b"], x), trail)
    assert term_writeq(x) in ("pr(a,[b])", 'pr(a,"b")')


def test_nested_partial_lists_share_their_tail(mod):
    (h, _), (hf, _), (hg, _) = _terms(mod, "n", 1)
    trail = Trail()
    assert unify(h, ("n", ["a", ["b", "c"], "c"]), trail)
    assert not unify(h, ("n", ["a", ["b", "c"], "d"]), Trail())
    assert unify(hf, ("n", ("f", [1, 2], [2])), Trail())
    assert not unify(hf, ("n", ("f", [1, 2], [3])), Trail())
    assert unify(hg, ("n", [("g", [1, 2]), 2]), Trail())


def test_a_rule_head_and_body_share_the_tail(mod):
    (h, b), = _terms(mod, "q", 1)
    assert not _nodes_in(b)
    assert _vars_in(h) and _vars_in(h) <= _vars_in(b)


def test_each_call_renames_afresh(mod):
    (h1, _), *_ = _terms(mod, "p", 2)
    (h2, _), *_ = _terms(mod, "p", 2)
    assert not (_vars_in(h1) & _vars_in(h2))


def test_a_head_without_a_pattern_is_unchanged(mod):
    (h, b), = _terms(mod, "g", 1)
    assert type(h) is tuple and h[0] == "g" and is_var(h[1])
    assert id(deref(h[1])) in _vars_in(b)
