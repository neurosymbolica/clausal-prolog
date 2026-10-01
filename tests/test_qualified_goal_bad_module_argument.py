"""Operator ruling 2026-10-01: a CALLED qualified goal whose MODULE argument
is unbound or is not an atom raises Scryer's term, not
``existence_error(module, ...)``.

Measured on scryer-prolog (``f.pl -g Goal -g halt``).  The context is
``call/N`` with N = the goal's arity plus call/N's extras (Scryer names the
call/N it would have run), so ``call(7:foo)`` is ``call/0``:

  call(7:foo)            error(type_error(atom, 7), call/0)
  call(_:foo)            error(instantiation_error, call/0)
  call(7:foo, x)         error(type_error(atom, 7), call/1)
  call(7:foo(a, b))      error(type_error(atom, 7), call/2)
  call(f(x):foo)         error(type_error(atom, f(x)), call/0)
  call("ab":foo)         error(type_error(atom, [a, b]), call/0)
  findall(x, 7:foo, _)   error(type_error(atom, 7), call/0)
  \\+ 7:foo               error(type_error(atom, 7), call/0)
  M = 7, M:foo           error(type_error(atom, 7), call/0)  (see below)
  call(nosuchmod:7:foo)  error(type_error(atom, 7), call/0)
  call(7:(foo, foo))     error(type_error(atom, 7), call/0)
  call(7:(foo, foo), x)  error(type_error(atom, 7), call/3)
  call(7:_)              error(type_error(callable, 7:_), call/1)
  call(7:1)              error(type_error(callable, 7:1), call/1)
  call(7:_, x)           error(instantiation_error, call/2)
  call(7:1, x)           error(type_error(callable, 1), call/2)
  phrase(7:g, [])        error(type_error(callable, 7:g([], [])), call/1)
  phrase(_:g, [])        error(type_error(callable, _:g([], [])), call/1)
  phrase(7:_, [])        error(instantiation_error, call/3)
  phrase(7:1, [])        error(type_error(callable, 7:1), call/1)

Every case raised ``existence_error(module, '7')`` (or the variable's repr)
on 841b6b24, and the native .pl front end REFUSED a body goal ``M:foo`` /
``7:foo`` at load ("the module of a qualified goal must be an atom at
load"); it now lowers it to ``call(M:foo)``.  Every test here fails on
841b6b24 except the ``kept`` pins at the end.
"""
from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var

_PL = """\
:- module(bmapl, [r/2]).
foo.
foo(_).
g(S, S).
r(c7, _) :- call(7:foo).
r(cv, _) :- call(_:foo).
r(c7x, _) :- call(7:foo, x).
r(cvx, _) :- call(_:foo, x).
r(c7ab, _) :- call(7:foo(a,b)).
r(cfx, _) :- call(f(x):foo).
r(cstr, _) :- call("ab":foo).
r(cfl, _) :- call(1.5:foo).
r(c7v, _) :- call(7:_).
r(cvv, _) :- call(_:_).
r(c71, _) :- call(7:1).
r(c7vx, _) :- call(7:_, x).
r(c71x, _) :- call(7:1, x).
r(cn7, _) :- call(bmanosuchmod:7:foo).
r(cnv, _) :- call(bmanosuchmod:_:foo).
r(c7conj, _) :- call(7:(foo(a),foo)).
r(c7conjx, _) :- call(7:(foo,foo), x).
"""

# Body goals: the native front end refused these at load on 841b6b24.
_PL_BODY = """\
:- module(bmabody, [r/2]).
foo.
foo(_).
g(S, S).
r(fa7, _) :- findall(x, 7:foo, _).
r(fav, _) :- findall(x, _:foo, _).
r(n7, _) :- \\+ 7:foo.
r(nv, _) :- \\+ _:foo.
r(ph7, _) :- phrase(7:g, []).
r(phv, _) :- phrase(_:g, []).
r(ph73, _) :- phrase(7:g, [a], [a]).
r(ph7v, _) :- phrase(7:_, []).
r(ph71, _) :- phrase(7:1, []).
r(b7, M) :- M = 7, M:foo.
r(bv, M) :- M:foo.
r(bfx, M) :- M = f(x), M:foo.
r(bq7, M) :- M = 7, M:foo(1).
r(w7, _) :- 7:foo.
"""

_SEAM = """
    -module(bmaseam, [])
    -allow_singletons
    -private([c7, cv, c7x, b7, bv, fa7, n7, x, c7v, p7, pv])
    foo,
    g(S, S),
    s(c7) <- (M is 7, call(':'(M, foo)))
    s(cv) <- call(':'(M, foo))
    s(c7x) <- (M is 7, call(':'(M, foo), x))
    s(b7) <- (M is 7, ':'(M, foo))
    s(bv) <- ':'(M, foo)
    s(fa7) <- (M is 7, findall(x, ':'(M, foo), _))
    s(n7) <- (M is 7, not ':'(M, foo))
    s(c7v) <- (M is 7, call(':'(M, G)))
    s(p7) <- (M is 7, phrase(':'(M, g), []))
    s(pv) <- phrase(':'(M, g), [])
"""


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    d = tmp_path_factory.mktemp("bma")
    (d / "bmapl.pl").write_text(_PL)
    (d / "bmabody.pl").write_text(_PL_BODY)
    (d / "bmaseam.clausal").write_text(textwrap.dedent(_SEAM).lstrip())
    names = ("bmapl", "bmabody", "bmaseam")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CLAUSAL_PL_FRONTEND", "native")
        mp.syspath_prepend(str(d))
        for n in names:
            sys.modules.pop(n, None)
        importlib.invalidate_caches()
        try:
            pl = importlib.import_module("bmapl")
            from clausal import import_hook as ih
            assert type(pl.__loader__) is ih.NativePrologLoader
            seam = importlib.import_module("bmaseam")
            yield pl.__dict__["$module"], seam.__dict__["$module"]
        finally:
            for n in names:
                sys.modules.pop(n, None)


@pytest.fixture(scope="module")
def body(mods):
    """The body-goal file, loaded on its own so that a load refusal there
    does not hide the call/N cases."""
    return importlib.import_module("bmabody").__dict__["$module"]


def _err(formal, n):
    return ("error", formal, ("/", "call", n))


def _atom(culprit, n):
    return _err(("type_error", "atom", culprit), n)


_INST = "instantiation_error"


def _raised(gen):
    with pytest.raises(LogicException) as exc:
        list(gen)
    return exc.value.term


def _is_var(x):
    from clausal.logic.variables import deref, is_var
    return is_var(deref(x))


@pytest.mark.parametrize("tag, term", [
    ("c7", _atom(7, 0)),
    ("cv", _err(_INST, 0)),
    ("c7x", _atom(7, 1)),
    ("cvx", _err(_INST, 1)),
    ("c7ab", _atom(7, 2)),
    ("cfx", _atom(("f", "x"), 0)),
    ("cstr", _atom(["a", "b"], 0)),
    ("cfl", _atom(1.5, 0)),
    ("fa7", _atom(7, 0)),
    ("fav", _err(_INST, 0)),
    ("n7", _atom(7, 0)),
    ("nv", _err(_INST, 0)),
    ("b7", _atom(7, 0)),
    ("bv", _err(_INST, 0)),
    ("bfx", _atom(("f", "x"), 0)),
    ("bq7", _atom(7, 1)),
    ("w7", _atom(7, 0)),
    ("c71", _err(("type_error", "callable", (":", 7, 1)), 1)),
    ("c7vx", _err(_INST, 2)),
    ("c71x", _err(("type_error", "callable", 1), 2)),
    ("cn7", _atom(7, 0)),
    ("cnv", _err(_INST, 0)),
    ("c7conj", _atom(7, 1)),
    ("c7conjx", _atom(7, 3)),
    ("ph7", _err(("type_error", "callable", (":", 7, ("g", [], []))), 1)),
    ("ph73", _err(("type_error", "callable",
                   (":", 7, ("g", ["a"], ["a"]))), 1)),
    ("ph7v", _err(_INST, 3)),
    ("ph71", _err(("type_error", "callable", (":", 7, 1)), 1)),
])
def test_pl_front_end(mods, request, tag, term):
    pl, _seam = mods
    if f"r({tag}," in _PL_BODY:
        pl = request.getfixturevalue("body")
    assert _raised(call("r", tag, Var(), module=pl)) == term


def test_pl_unbound_goal_under_a_non_atom_module(mods):
    """``call(7:_)`` / ``call(_:_)``: Scryer's call/1 refuses the whole
    ``M:G`` -- ``type_error(callable, 7:_)``, context call/1."""
    pl, _seam = mods
    for tag, module_is_var in (("c7v", False), ("cvv", True)):
        term = _raised(call("r", tag, Var(), module=pl))
        assert term[0] == "error" and term[2] == ("/", "call", 1)
        kind, typ, culprit = term[1]
        assert (kind, typ, culprit[0]) == ("type_error", "callable", ":")
        assert (culprit[1] == 7) if not module_is_var else _is_var(culprit[1])
        assert _is_var(culprit[2])


def test_pl_phrase_with_an_unbound_module(body):
    term = _raised(call("r", "phv", Var(), module=body))
    assert term[2] == ("/", "call", 1)
    kind, typ, culprit = term[1]
    assert (kind, typ) == ("type_error", "callable")
    assert _is_var(culprit[1]) and culprit[2] == ("g", [], [])


@pytest.mark.parametrize("tag, term", [
    ("c7", _atom(7, 0)),
    ("cv", _err(_INST, 0)),
    ("c7x", _atom(7, 1)),
    ("b7", _atom(7, 0)),
    ("bv", _err(_INST, 0)),
    ("fa7", _atom(7, 0)),
    ("n7", _atom(7, 0)),
    ("p7", _err(("type_error", "callable", (":", 7, ("g", [], []))), 1)),
])
def test_seam_colon(mods, tag, term):
    _pl, seam = mods
    assert _raised(call("s", tag, module=seam)) == term


def test_seam_unbound_goal_under_a_non_atom_module(mods):
    _pl, seam = mods
    term = _raised(call("s", "c7v", module=seam))
    assert term[2] == ("/", "call", 1)
    assert term[1][:2] == ("type_error", "callable")
    assert term[1][2][1] == 7 and _is_var(term[1][2][2])


@pytest.mark.parametrize("goal, term", [
    ((":", 7, "foo"), _atom(7, 0)),
    ((":", 7, ("foo", 1)), _atom(7, 1)),
    ((":", ("f", "x"), "foo"), _atom(("f", "x"), 0)),
])
def test_solve(mods, goal, term):
    pl, _seam = mods
    assert _raised(solve(goal, pl)) == term


def test_solve_unbound_module(mods):
    pl, _seam = mods
    assert _raised(solve((":", Var(), "foo"), pl)) == _err(_INST, 0)


# ── kept ────────────────────────────────────────────────────────────────────

def test_kept_a_module_object_designator_still_answers(mods):
    """A non-atom designator that RESOLVES (a Module) is no error."""
    pl, _seam = mods
    assert len(list(solve((":", pl, "foo"), pl))) == 1


def test_kept_a_missing_outer_atom_module_is_the_module_error(mods):
    """``nosuchmod:bmapl:foo``: ruled to keep the module error."""
    pl, _seam = mods
    term = _raised(call("call", (":", "bmanosuchmod", (":", "bmapl", "foo")),
                        module=pl))
    assert term[1][:2] == ("existence_error", "module")


def test_kept_assert_into_a_non_atom_module(mods):
    """Not a call: asserting into ``7:`` keeps its own error."""
    pl, _seam = mods
    term = _raised(call("assertz", (":", 7, "foo"), module=pl))
    assert term[1][:2] == ("existence_error", "module")
