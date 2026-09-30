"""Two operator rulings (2026-09-30) following ``':'(M, G)`` in seam.

RULING A -- the Python-side ``--term`` builder (``seam.seam_term``) builds
``--':'(M, G)`` as the qualified goal cell ``(":", M, G)``: the very term
seam ``':'(m, mp(1))`` and the native .pl ``m:mp(1)`` produce (``==``).  It
raised ``NameError: 'mp' is not a declared or imported functor``.  It KEEPS
refusing ``foo()`` (ruling 2026-09-06, "foo() is not a term form"), inside
``':'`` too.

RULING B -- calling a qualified goal whose module does NOT exist raises
Scryer's ``error(existence_error(procedure, mp/1), mp/1)`` (verified on
scryer-prolog: ``call(nosuchmod:mp(_))``, ``nosuchmod:mp(_)``,
``call(nosuchmod:mp, _)`` and ``findall(X, nosuchmod:mp(X), _)`` all give
exactly that term), in both front ends.  It was
``error(existence_error(module, 'nosuchmod'), call/1)``.

Every test here fails on 5428c692 except the pins of what is kept
(``foo()`` refused in ``--``, the module error for a non-atom designator)
and the two .pl body-goal cases (``pl_goal``, ``pl_findall``): the native
front end lowers a WRITTEN ``M:G`` body goal itself and already raised
Scryer's form there; they pin that every route now agrees.
"""
from __future__ import annotations

import importlib
import sys
import textwrap

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call, solve
from clausal.logic.variables import Var, walk

_LIB = """
    -module(cfulib, [mp(X), z/0])
    mp(1),
    mp(2),
    z,
"""

_PL = """\
:- module(cfupl, [mk/1, mkq/1, pl_call/1, pl_goal/1, pl_extra/1,
                  pl_findall/1, pl_phrase/1]).
mk(T) :- T = cfulib:mp(1).
mkq(T) :- T = cfulib:(cfulib:mp(1)).
pl_call(X) :- call(cfunosuchmod:mp(X)).
pl_goal(X) :- cfunosuchmod:mp(X).
pl_extra(X) :- call(cfunosuchmod:mp, X).
pl_findall(L) :- findall(X, cfunosuchmod:mp(X), L).
pl_phrase(L) :- phrase(cfunosuchmod:g, L).
"""

_USER = """
    -module(cfuuser, [])
    -import_module(cfulib)
    -import_module(cfupl)

    clause_term(T) <- (T is ':'(cfulib, mp(1)))

    def seam_term():
        return --':'(cfulib, mp(1))

    def seam_term_quoted():
        return --':'('cfulib', mp(1))

    def seam_term_var():
        return --':'(M, mp(1))

    def seam_term_bare():
        return --':'(cfulib, z)

    def seam_term_nested():
        return --':'(cfulib, ':'(cfulib, mp(1)))

    def seam_term_zero():
        return --':'(cfulib, z())

    def seam_term_open():
        return --':'(cfulib, mp(X))

    seam_call(X) <- call(':'('cfunosuchmod', mp(X)))
    seam_goal(X) <- ':'('cfunosuchmod', mp(X))
    seam_extra(X) <- call(':'('cfunosuchmod', mp), X)
    seam_var(X) <- (M is 'cfunosuchmod', call(':'(M, mp(X))))
    seam_findall(L) <- findall(X, ':'('cfunosuchmod', mp(X)), L)
"""


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    d = tmp_path_factory.mktemp("cfu")
    (d / "cfulib.clausal").write_text(textwrap.dedent(_LIB).lstrip())
    (d / "cfupl.pl").write_text(_PL)
    (d / "cfuuser.clausal").write_text(textwrap.dedent(_USER).lstrip())
    names = ("cfulib", "cfupl", "cfuuser")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CLAUSAL_PL_FRONTEND", "native")
        mp.syspath_prepend(str(d))
        for n in names:
            sys.modules.pop(n, None)
        importlib.invalidate_caches()
        try:
            pl = importlib.import_module("cfupl")
            from clausal import import_hook as ih
            assert type(pl.__loader__) is ih.NativePrologLoader
            user = importlib.import_module("cfuuser")
            yield user, pl
        finally:
            for n in names:
                sys.modules.pop(n, None)


def _answers(module, goal):
    x = Var()
    return [walk(x) for _ in call(goal, x, module=module.__dict__["$module"])]


def _is_identical(module, a, b):
    """ISO ``==`` in the engine, not Python equality."""
    return len(list(solve(("==", a, b), module.__dict__["$module"]))) == 1


# ── RULING A: --':'(M, G) ───────────────────────────────────────────────────

def test_the_seam_term_is_the_pl_term_and_the_clause_term(mods):
    user, pl = mods
    built = user.seam_term()
    (pl_term,) = _answers(pl, "mk")
    (clause_term,) = _answers(user, "clause_term")
    assert built == (":", "cfulib", ("mp", 1))
    assert _is_identical(user, built, pl_term)
    assert _is_identical(user, built, clause_term)


def test_a_quoted_module_builds_the_same_term(mods):
    user, pl = mods
    (pl_term,) = _answers(pl, "mk")
    assert _is_identical(user, user.seam_term_quoted(), pl_term)


def test_a_variable_module_is_a_fresh_variable(mods):
    user, _pl = mods
    t = user.seam_term_var()
    assert t[0] == ":" and t[2] == ("mp", 1)
    assert isinstance(walk(t[1]), Var)


def test_a_bare_name_goal_is_the_atom(mods):
    user, _pl = mods
    assert user.seam_term_bare() == (":", "cfulib", "z")


def test_a_nested_qualification_is_the_pl_term(mods):
    user, pl = mods
    (pl_term,) = _answers(pl, "mkq")
    assert _is_identical(user, user.seam_term_nested(), pl_term)


def test_the_built_term_runs_in_its_module(mods):
    user, _pl = mods
    t = user.seam_term_open()
    got = [walk(t[2][1]) for _ in solve(t, user.__dict__["$module"])]
    assert got == [1, 2]


def test_foo_paren_is_still_not_a_seam_term(mods):
    """Kept (ruling 2026-09-06): ``foo()`` is refused in ``--``, inside
    ``':'`` as well."""
    user, _pl = mods
    with pytest.raises(SyntaxError, match=r"z\(\) is not a term"):
        user.seam_term_zero()


# ── RULING B: a module that does not exist ──────────────────────────────────

_SCRYER_MP1 = ("error", ("existence_error", "procedure", ("/", "mp", 1)),
               ("/", "mp", 1))


@pytest.mark.parametrize("front, goal", [
    ("pl", "pl_call"),
    ("pl", "pl_goal"),
    ("pl", "pl_extra"),
    ("pl", "pl_findall"),
    ("seam", "seam_call"),
    ("seam", "seam_goal"),
    ("seam", "seam_extra"),
    ("seam", "seam_var"),
    ("seam", "seam_findall"),
])
def test_calling_into_a_missing_module_is_scryers_missing_procedure(
        mods, front, goal):
    user, pl = mods
    with pytest.raises(LogicException) as exc:
        _answers(pl if front == "pl" else user, goal)
    assert exc.value.term == _SCRYER_MP1


def test_solve_on_a_missing_module_is_the_missing_procedure(mods):
    user, _pl = mods
    with pytest.raises(LogicException) as exc:
        list(solve((":", "cfunosuchmod", ("mp", Var())),
                   user.__dict__["$module"]))
    assert exc.value.term == _SCRYER_MP1


def test_call_n_extras_count_in_the_arity(mods):
    """Scryer: ``call(nosuchmod:mp(1), 2, 3)`` is ``mp/3``."""
    user, _pl = mods
    with pytest.raises(LogicException) as exc:
        list(call("call", (":", "cfunosuchmod", ("mp", 1)), 2, 3,
                  module=user.__dict__["$module"]))
    assert exc.value.term == ("error",
                              ("existence_error", "procedure", ("/", "mp", 3)),
                              ("/", "mp", 3))


def test_phrase_over_a_missing_module_is_the_missing_nonterminal(mods):
    """``phrase(nosuchmod:g, L)`` asks for g/2, as ``call(nosuchmod:g, S0,
    S)`` does.  (Scryer's phrase/2 writes the culprit qualified,
    ``nosuchmod:g/2``; call/N's form is the one used here.)"""
    _user, pl = mods
    with pytest.raises(LogicException) as exc:
        _answers(pl, "pl_phrase")
    assert exc.value.term == ("error",
                              ("existence_error", "procedure", ("/", "g", 2)),
                              ("/", "g", 2))


def test_a_missing_outer_module_keeps_the_module_error_through_call(mods):
    """``nosuchmod:cfulib:mp(X)``: cfulib would answer, so no procedure is
    missing; every layer is still resolved (Scryer answers here -- the
    outer module is ignored)."""
    user, _pl = mods
    goal = (":", "cfunosuchmod", (":", "cfulib", ("mp", Var())))
    with pytest.raises(LogicException) as exc:
        list(call("call", goal, module=user.__dict__["$module"]))
    assert exc.value.term[1][:2] == ("existence_error", "module")


def test_a_non_atom_designator_keeps_the_module_error(mods):
    """Not ruled: ``7:mp(X)`` is not a module that does not exist."""
    user, _pl = mods
    with pytest.raises(LogicException) as exc:
        list(solve((":", 7, ("mp", Var())), user.__dict__["$module"]))
    assert exc.value.term[1][:2] == ("existence_error", "module")
