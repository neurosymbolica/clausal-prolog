"""Two seam rulings (operator, 2026-09-30).

RULING 1 -- ``':'(M, G)`` builds the ISO qualified goal ``M:G`` as a TERM.
A dotted ``lib.p(X)`` in data position stays the plain ``p(X)`` cell
(ruling (a)), so seam had no way to build a qualified goal as data:
``':'(lib, mp(X))`` raised ``existence_error(procedure, (:)/2)`` wherever it
was written.  It is now the cell ``(":", lib, ("mp", X))`` -- the very term
the .pl front end reads for ``lib:mp(X)`` -- which call/N, findall/3,
aggregate_all/3 & co. already run in ``lib``.  The second argument is
resolved in lib: the caller declares nothing about ``mp``.

RULING 2 -- ``name()`` is the atom ``name``.  ``call(zz())`` raised a Python
``TypeError`` about the reserved 1-tuple ``('zz',)``, and ``T is zz()``
quietly bound that reserved 1-tuple.  A zero-argument call is now the atom
wherever a goal or term is expected; a name bound to a Python callable is
still called.

Every test here fails on d7f1a837 (the ``:`` shapes and the zero-argument
meta-call/data shapes); the Python-call tests pin behaviour that must not
move.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import sys
import textwrap

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk

_LIB = """
    -module(sqclib, [mp(X), q(A, B), z/0])
    mp(1),
    mp(2),
    q(A, B) <- (B is A)
    z,
"""

# Native .pl front end: ``sqclib:mp(1)`` read by the ISO reader.
_PL = """\
:- module(sqcpl, [mk/1, mkz/1]).
mk(T) :- T = sqclib:mp(1).
mkz(T) :- T = sqclib:z.
"""

_PYHELP = "def f0():\n    return 42\n"

# The caller declares NOTHING about mp/z/q; its own mp/1 answers 99, so a
# goal that ran in the caller would be visible.
_USER = """
    -module(sqcuser, [])
    -import_module(sqclib)
    -import_module(sqcpl)
    import time
    import sqcpyhelp
    from sqcpyhelp import f0
    own(99),
    zz,
    ok(_),

    is_then_call(X) <- (T is ':'(sqclib, mp(X)), call(T))
    call_direct(X) <- call(':'(sqclib, mp(X)))
    via_findall(L) <- findall(X, ':'(sqclib, mp(X)), L)
    via_aggregate(N) <- aggregate_all('count', ':'(sqclib, mp(_)), N)
    as_goal(X) <- ':'(sqclib, mp(X))
    via_once(X) <- once(':'(sqclib, mp(X)))
    via_not(X) <- (not ':'(sqclib, mp(3)), X is 1)
    quoted_module(X) <- call(':'('sqclib', mp(X)))
    var_module(X) <- (M is 'sqclib', call(':'(M, mp(X))))
    nested(X) <- call(':'(sqclib, ':'(sqclib, mp(X))))
    maplist_closure(X) <- (maplist(':'(sqclib, q(1)), [1, 1]), X is 1)
    paren_zero(X) <- (call(':'(sqclib, z())), X is 1)
    data(T) <- (T is ':'(sqclib, mp(1)))
    dotted_data_unchanged(T) <- (T is sqclib.mp(1))

    same_as_pl(X) <- (sqcpl.mk(A), T is ':'(sqclib, mp(1)), A == T, X is 1)
    same_as_pl_zero(X) <- (sqcpl.mkz(A), T is ':'(sqclib, z()), A == T,
                           X is 1)
    show(X) <- (T is ':'(sqclib, mp(1)), writeq(T), nl, X is 1)

    unknown_module(X) <- call(':'('sqcnosuchmod', mp(X)))
    unknown_predicate(X) <- call(':'(sqclib, own(X)))

    zz_call(X) <- (call(zz()), X is 1)
    zz_aggregate(N) <- aggregate_all('count', zz(), N)
    zz_findall(L) <- findall(1, zz(), L)
    zz_maplist(X) <- (maplist(ok(), [1, 2]), X is 1)
    zz_goal(X) <- (zz(), X is 1)
    dotted_zero_call(X) <- (call(sqclib.z()), X is 1)
    dotted_zero_goal(X) <- (sqclib.z(), X is 1)
    zz_data(T) <- (T is zz())
    zz_list(T) <- (T is [zz(), 1])
    dotted_zero_data(T) <- (T is sqclib.z())

    py_bare(T) <- (T is f0())
    py_escape(T) <- (T is ++f0())
    py_dotted(T) <- (T is sqcpyhelp.f0())
    py_dotted_escape(T) <- (T is ++sqcpyhelp.f0())
    py_time(T) <- (T is time.time())
"""


# A BARE name as the goal of ``':'`` -- strict atoms refused the whole
# module on d7f1a837 ("undeclared atoms 'mp', 'z'"), so it loads alone.
_USER_BARE = """
    -module(sqcbare, [])
    -import_module(sqclib)
    call_extra(X) <- call(':'(sqclib, mp), X)
    bare_zero(X) <- (call(':'(sqclib, z)), X is 1)
"""


@pytest.fixture(scope="module")
def user(tmp_path_factory):
    d = tmp_path_factory.mktemp("sqc")
    (d / "sqclib.clausal").write_text(textwrap.dedent(_LIB).lstrip())
    (d / "sqcpl.pl").write_text(_PL)
    (d / "sqcpyhelp.py").write_text(_PYHELP)
    (d / "sqcuser.clausal").write_text(textwrap.dedent(_USER).lstrip())
    (d / "sqcbare.clausal").write_text(textwrap.dedent(_USER_BARE).lstrip())
    names = ("sqclib", "sqcpl", "sqcpyhelp", "sqcuser", "sqcbare")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("CLAUSAL_PL_FRONTEND", "native")
        mp.syspath_prepend(str(d))
        for n in names:
            sys.modules.pop(n, None)
        importlib.invalidate_caches()
        try:
            pl = importlib.import_module("sqcpl")
            from clausal import import_hook as ih
            assert type(pl.__loader__) is ih.NativePrologLoader
            m = importlib.import_module("sqcuser")
            yield m.__dict__["$module"]
        finally:
            for n in names:
                sys.modules.pop(n, None)


@pytest.fixture(scope="module")
def bare(user):
    return importlib.import_module("sqcbare").__dict__["$module"]


def _answers(module, goal):
    x = Var()
    return [walk(x) for _ in call(goal, x, module=module)]


def _error_formal(module, goal):
    with pytest.raises(LogicException) as exc:
        _answers(module, goal)
    return cell_args(exc.value.term)[0]


# ── RULING 1: ':'(M, G) ─────────────────────────────────────────────────────

@pytest.mark.parametrize("goal, expected", [
    ("is_then_call", [1, 2]),
    ("call_direct", [1, 2]),
    ("via_findall", [[1, 2]]),
    ("via_aggregate", [2]),
    ("as_goal", [1, 2]),
    ("via_once", [1]),
    ("via_not", [1]),
    ("quoted_module", [1, 2]),
    ("var_module", [1, 2]),
    ("nested", [1, 2]),
    ("maplist_closure", [1]),
    ("paren_zero", [1]),
])
def test_a_colon_goal_runs_in_its_module(user, goal, expected):
    """Each raised existence_error(procedure, (:)/2) on d7f1a837; the caller
    declares nothing about mp/q/z and its own facts never answer."""
    assert _answers(user, goal) == expected


@pytest.mark.parametrize("goal, expected", [
    ("call_extra", [1, 2]),
    ("bare_zero", [1]),
])
def test_a_bare_name_as_the_colon_goal_needs_no_declaration(
        bare, goal, expected):
    """``':'(sqclib, mp)`` / ``':'(sqclib, z)``: the name is sqclib's."""
    assert _answers(bare, goal) == expected


def test_the_colon_term_is_the_qualified_goal_cell(user):
    assert _answers(user, "data") == [(":", "sqclib", ("mp", 1))]


def test_a_dotted_call_in_data_position_is_still_the_plain_cell(user):
    """Ruling (a) is kept."""
    assert _answers(user, "dotted_data_unchanged") == [("mp", 1)]


@pytest.mark.parametrize("goal", ["same_as_pl", "same_as_pl_zero"])
def test_the_seam_term_is_the_pl_front_ends_term(user, goal):
    """``':'(sqclib, mp(1))`` in seam == ``sqclib:mp(1)`` read by the native
    .pl front end (and ``':'(sqclib, z())`` == ``sqclib:z``)."""
    assert _answers(user, goal) == [1]


def test_the_pl_term_and_the_seam_term_are_equal_in_python(user):
    pl = sys.modules["sqcpl"].__dict__["$module"]
    assert _answers(pl, "mk") == _answers(user, "data")


def test_writeq_prints_the_iso_form(user):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert _answers(user, "show") == [1]
    assert buf.getvalue().strip() == "sqclib:mp(1)"


def test_an_unknown_module_is_an_iso_existence_error(user):
    formal = _error_formal(user, "unknown_module")
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal)[0] == mint("module")


def test_an_unknown_predicate_is_an_iso_existence_error(user):
    """``own/1`` is the CALLER's predicate; sqclib defines none."""
    formal = _error_formal(user, "unknown_predicate")
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal) == (mint("procedure"), ("/", mint("own"), 1))


# ── RULING 2: name() is the atom name ───────────────────────────────────────

@pytest.mark.parametrize("goal, expected", [
    ("zz_call", [1]),              # TypeError on d7f1a837
    ("zz_aggregate", [1]),         # TypeError on d7f1a837
    ("zz_maplist", [1]),           # TypeError on d7f1a837
    ("dotted_zero_call", [1]),     # TypeError on d7f1a837
    ("zz_findall", [[1]]),
    ("zz_goal", [1]),
    ("dotted_zero_goal", [1]),
])
def test_a_zero_argument_call_is_the_goal_of_its_name(user, goal, expected):
    assert _answers(user, goal) == expected


@pytest.mark.parametrize("goal, expected", [
    ("zz_data", ["zz"]),
    ("zz_list", [["zz", 1]]),
    ("dotted_zero_data", ["z"]),
])
def test_a_zero_argument_call_in_data_is_the_atom(user, goal, expected):
    """d7f1a837 bound the reserved 1-tuple ``('zz',)`` / ``('z',)``."""
    got = _answers(user, goal)
    assert got == expected
    assert all(type(t) is not tuple for t in got)


@pytest.mark.parametrize("goal", [
    "py_bare", "py_escape", "py_dotted", "py_dotted_escape",
])
def test_a_zero_argument_python_call_is_still_a_python_call(user, goal):
    assert _answers(user, goal) == [42]


def test_a_zero_argument_python_module_function_is_still_called(user):
    (t,) = _answers(user, "py_time")
    assert type(t) is float
