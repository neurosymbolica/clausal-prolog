"""Ruling R12 (2026-09-29): a bare BUILTIN name in a data/argument position
is the ATOM, as in every Prolog; only a goal position resolves the predicate.

Before: ``must_be(integer, 3)`` raised ``type_error(atom, <builtin
integer/1>)`` (the name loaded the builtin's dispatch object), ``X is
assertz`` bound a syntax-node class, and ``call(in_, X, [1])`` leaked a
Python ``TypeError`` (the class was called as a constructor).

A meta-argument (call/N, maplist's closure, findall's goal, a
``-meta_predicate`` argument) is a goal position whose VALUE is a callable
term: it receives the atom and resolves it by name when called.
"""
from __future__ import annotations

import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call, solve
from clausal.logic.variables import Var
from tests._suffix import SEAM


SRC = """\
-private([a, b, f(_)])
-dynamic(fact/1)
-meta_predicate(app1(1, '?'))
kind(integer),
kind(assertz),
kind(f(in_)),
app1(G, X) <- call(G, X)
must_integer() <- must_be(integer, 3)
is_assertz(X) <- (X is assertz)
is_integer(X) <- (X is integer)
call_in(X) <- call(in_, X, [1])
call_integer() <- call(integer, 3)
maplist_integer() <- maplist(integer, [1, 2])
maplist_succ(L) <- maplist(succ, [1, 2], L)
include_integer(L) <- include(integer, [1, a, 2], L)
foldl_plus(S) <- foldl(plus, [1, 2, 3], 0, S)
var_closure(X) <- (G is integer, call(G, 3), X is G)
assert_via(G) <- call(G, fact(7))
assert_closure(X) <- (assert_via(assertz), fact(X))
meta_arg() <- app1(integer, 3)
findall_between(L) <- findall(X, call(between, 1, 3, X), L)
functor_name(T) <- functor(T, integer, 1)
must_be_error(E) <- catch(must_be(integer, a), error(E, _), true)
list_of_names(L) <- (L is [integer, atom, in_, length])
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("r12") / f"r12_builtin_atoms{SEAM}"
    path.write_text(SRC)
    return _load_module("r12_builtin_atoms", str(path))


def _answers(mod, name, arity):
    vs = [Var() for _ in range(arity)]
    return [[_deref_walk(v) for v in vs]
            for _ in call(name, *vs, module=mod.__dict__["$module"])]


def test_must_be_gets_the_type_atom(mod):
    assert _answers(mod, "must_integer", 0) == [[]]


def test_must_be_error_names_the_type_atom(mod):
    assert _answers(mod, "must_be_error", 1) == [[("type_error", "integer", "a")]]


@pytest.mark.parametrize("pred, atom", [
    ("is_assertz", "assertz"),     # was a syntax-node class
    ("is_integer", "integer"),     # was the builtin's dispatch object
])
def test_builtin_name_binds_the_atom(mod, pred, atom):
    assert _answers(mod, pred, 1) == [[atom]]


def test_names_inside_a_list_are_atoms(mod):
    assert _answers(mod, "list_of_names", 1) == [[
        ["integer", "atom", "in_", "length"]]]


def test_names_in_fact_heads_are_atoms(mod):
    assert [a for (a,) in _answers(mod, "kind", 1)] == [
        "integer", "assertz", ("f", "in_")]


def test_functor_takes_the_atom(mod):
    [[t]] = _answers(mod, "functor_name", 1)
    assert t[0] == "integer" and len(t) == 2


# ---- meta-arguments: the atom still dispatches ------------------------------

def test_call_in_closure_dispatches(mod):
    # was: TypeError: in_.__init__() takes from 1 to 4 positional arguments
    assert _answers(mod, "call_in", 1) == [[1]]


@pytest.mark.parametrize("pred, arity, expected", [
    ("call_integer", 0, [[]]),
    ("maplist_integer", 0, [[]]),
    ("maplist_succ", 1, [[[2, 3]]]),
    ("include_integer", 1, [[[1, 2]]]),
    ("foldl_plus", 1, [[6]]),
    ("var_closure", 1, [["integer"]]),
    ("assert_closure", 1, [[7]]),
    ("meta_arg", 0, [[]]),
    ("findall_between", 1, [[[1, 2, 3]]]),
])
def test_builtin_atom_as_closure(mod, pred, arity, expected):
    assert _answers(mod, pred, arity) == expected


# ---- the seam: a query and a ``--`` term ------------------------------------

def test_seam_query_and_term(tmp_path, monkeypatch):
    lib = tmp_path / f"r12_seam_lib{SEAM}"
    lib.write_text("kind(integer),\nkind(assertz),\n")
    host = tmp_path / f"r12_seam_host{SEAM}"
    host.write_text(
        "-private([f(_)])\n"
        "-import_from(r12_seam_lib, [kind])\n"
        "xs = [X for X in --kind(X)]\n"
        "ok = [Y for Y in --(must_be(integer, 3), Y is 1)]\n"
        "v = --[integer, assertz, f(in_)]\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _load_module("r12_seam_lib", str(lib))
    m = _load_module("r12_seam_host", str(host))
    assert m.xs == ["integer", "assertz"]
    assert m.ok == [1]
    assert m.v == ["integer", "assertz", ("f", "in_")]


def test_python_solve_with_the_atom(mod):
    assert len(list(solve(("must_be", "integer", 3),
                          module=mod.__dict__["$module"]))) == 1


def test_a_python_binding_under_a_builtin_name_is_kept(tmp_path):
    """A name the module binds itself (a Python value) is the user's value:
    the atom rule covers only an unshadowed builtin name."""
    from clausal.logic.compiler.terms_to_ast import _is_unshadowed_builtin_name
    from clausal.import_hook import runtime_builtins
    from clausal.logic.builtins._registry import _BUILTIN_CLASSES
    assert _is_unshadowed_builtin_name("integer", {})
    assert _is_unshadowed_builtin_name("integer",
                                       {"integer": _BUILTIN_CLASSES["integer"]})
    assert _is_unshadowed_builtin_name("assertz",
                                       {"assertz": runtime_builtins["assertz"]})
    assert not _is_unshadowed_builtin_name("integer", {"integer": 5})
    assert not _is_unshadowed_builtin_name("integer", {"integer": None})
    assert not _is_unshadowed_builtin_name("not_a_builtin_xyz", {})
