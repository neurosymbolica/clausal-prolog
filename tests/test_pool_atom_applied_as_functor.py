"""A name some OTHER module declared as an atom, applied as a functor here.

Every module dict is pre-seeded with the process-wide atom pool
(GLOBAL_ATOMS_DEFAULT rule 1.4), so once any module has declared the atom
``zz``, the name ``zz`` in a later module's dict is the plain str ``'zz'``.
A construction ``zz(1)`` of that undeclared functor compiled to a CALL of the
str and died at run time on CPython's ``TypeError: 'str' object is not
callable`` -- where the same module loaded first says "not in scope as a
term class".  Found 2026-09-25 as an order-dependent failure of the
retired-q() warning test (an earlier test had declared the atom ``q``).

Each test here pollutes the pool deliberately, so it pins the polluted
behaviour whatever ran before; the expected answers are the ones the same
source gives in a fresh process.
"""
from __future__ import annotations

import itertools
import os
import tempfile
import warnings

import pytest

from clausal.import_hook import _load_module, predicate_builtins
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM

_N = itertools.count()


def _load(stem, source):
    name = f"_pafn_{stem}_{next(_N)}"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}{SEAM}")
        with open(path, "w") as fh:
            fh.write(source)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return _load_module(name, path)


def _answers(mod, functor):
    lm = mod.__dict__["$module"]
    v = Var()
    return sorted((deref(v) for _ in call(functor, v, module=lm)), key=repr)


@pytest.fixture
def polluted():
    """Another module declares ``zz``, ``fact`` and ``logged`` as ATOMS."""
    _load("owner", "-module(_pafn_owner, [zz, fact, logged])\n"
                   "kind(zz),\nkind(fact),\nkind(logged),\n")
    assert all(type(predicate_builtins.get(n)) is str
               for n in ("zz", "fact", "logged"))


def test_construction_is_the_undeclared_functor_error_not_a_str_call(polluted):
    mod = _load("term", "r(T) <- (T is zz(1))\n")
    with pytest.raises(NameError, match=r"'zz/1' is not in scope: nothing declares the functor zz/1"):
        _answers(mod, "r")


def test_fact_argument_is_the_undeclared_functor_error(polluted):
    with pytest.raises(NameError, match=r"'zz/1' is not in scope: nothing declares the functor zz/1"):
        _answers(_load("fact", "s(zz(1)),\nr(T) <- s(T)\n"), "r")


def test_implicit_functors_still_builds_the_cell(polluted):
    mod = _load("owa", "-implicit_functors\nr(T) <- (T is zz(1))\n")
    assert _answers(mod, "r") == [("zz", 1)]


def test_a_bare_use_of_the_same_atom_still_is_the_atom(polluted):
    """The name key keeps the ATOM for an atom use in the same clause; only
    the construction is refused.  The atom use is quoted: under strict atoms
    a BARE ``zz`` would need a local declaration, and declaring ``zz`` as an
    atom here makes ``zz(1)`` a load-time atom-applied-as-functor error,
    which is not the pooled-name path this pins."""
    mod = _load("both", "r(U) <- (U is 'zz')\n"
                        "t(T) <- (T is zz(1))\n")
    assert _answers(mod, "r") == ["zz"]
    with pytest.raises(NameError, match=r"'zz/1' is not in scope"):
        _answers(mod, "t")


def test_term_expansion_introducing_a_pooled_functor_expands(polluted):
    """The TE pre-mint used to skip a name bound to a pooled atom, so the
    pattern compiled as a call of the str."""
    mod = _load("te", "term_expansion(fact(X), [fact(X), logged(X)], S, S),\n"
                      "fact(1),\n"
                      "r(X) <- logged(X)\n")
    assert _answers(mod, "r") == [1]
