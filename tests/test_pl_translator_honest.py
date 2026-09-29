"""The ``.pl`` import translator must not answer silently wrong.

Every case here loads a ``.pl`` file through the REAL ``PrologLoader`` and
checks the ANSWERS against what Scryer Prolog gives for the same file (the
expected values were measured with Scryer; see each test).  A construct the
engine cannot run must be a load-time error naming it, never a comment, a
drop or a rename.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.import_hook import _load_prolog_module
from clausal.logic.solve import query
from clausal.logic.variables import Var
from clausal.tools.prolog_to_clausal import (
    PrologTranslationError, prolog_to_clausal,
)

_PREFIX = "plhonest_"


@pytest.fixture(autouse=True)
def _on_path(tmp_path):
    sys.path.insert(0, str(tmp_path))
    yield
    sys.path.remove(str(tmp_path))
    for key in list(sys.modules):
        if key.startswith(_PREFIX) or key.startswith("plhpkg"):
            del sys.modules[key]


def _load(tmp_path, name, source):
    path = tmp_path / f"{_PREFIX}{name}.pl"
    path.write_text(textwrap.dedent(source))
    return _load_prolog_module(f"{_PREFIX}{name}", str(path))


def _answers(mod, pred):
    x = Var()
    return [s["X"] for s in query((pred, x), {"X": x}, mod)]


# ── A. bagof/setof keep the existential quantifier ─────────────────────

_SETOF_SRC = """\
    p(1, a).
    p(2, a).
    p(3, b).
    q(1, a, 1).
    q(2, b, 2).
    s(L) :- setof(X, Y^p(X, Y), L).
    b(L) :- bagof(X, Y^p(X, Y), L).
    g(L) :- setof(X, p(X, _Y), L).
    n(L) :- setof(X, A^B^q(X, A, B), L).
    c(L) :- setof(X, Y^(p(X, Y), X > 1), L).
"""


class TestCaretQuantifier:
    """ISO 8.10.2/8.10.3: ``Y^G`` makes Y existential, so the solutions are
    NOT grouped by Y.  Scryer: s -> [[1,2,3]], b -> [[1,2,3]],
    g -> [[1,2],[3]] (no ^, grouped), n -> [[1,2]], c -> [[2,3]]."""

    def test_setof_caret_is_one_answer(self, tmp_path):
        m = _load(tmp_path, "setof", _SETOF_SRC)
        assert _answers(m, "s") == [[1, 2, 3]]

    def test_bagof_caret_is_one_answer(self, tmp_path):
        m = _load(tmp_path, "bagof", _SETOF_SRC)
        assert _answers(m, "b") == [[1, 2, 3]]

    def test_no_caret_still_groups(self, tmp_path):
        m = _load(tmp_path, "group", _SETOF_SRC)
        assert _answers(m, "g") == [[1, 2], [3]]

    def test_nested_caret(self, tmp_path):
        m = _load(tmp_path, "nested", _SETOF_SRC)
        assert _answers(m, "n") == [[1, 2]]

    def test_caret_over_conjunction(self, tmp_path):
        m = _load(tmp_path, "conj", _SETOF_SRC)
        assert _answers(m, "c") == [[2, 3]]

    def test_caret_over_unification_goal(self, tmp_path):
        # member/2 emits the infix `X in L`, and `Y ^ X in L` would read as
        # `(Y ^ X) in L`: the goal is parenthesised.  Scryer: [[1,2]].
        m = _load(tmp_path, "unif", """\
            u(L) :- setof(X, Y^member(X-Y, [2-b, 1-a]), L).
        """)
        assert _answers(m, "u") == [[1, 2]]


# ── B. no rename of a name the program means literally ────────────────


class TestNoStaleRenames:
    """A Prolog name crosses unchanged unless the engine spells the SAME
    predicate differently.  ``profile_get/3`` was renamed to Clausal's
    ``get/3`` (an export-direction mapping for a downstream helper library,
    run backwards), so a program's own ``profile_get`` vanished."""

    def test_undefined_profile_get_is_an_existence_error(self, tmp_path):
        # Scryer: error(existence_error(procedure, profile_get/3), _)
        m = _load(tmp_path, "pg_undef", """\
            t(V) :- X = foo, profile_get(X, k, V).
        """)
        with pytest.raises(Exception, match="profile_get"):
            _answers(m, "t")

    def test_own_profile_get_is_called(self, tmp_path):
        m = _load(tmp_path, "pg_own", """\
            profile_get(foo, k, 1).
            t(V) :- profile_get(foo, k, V).
        """)
        assert _answers(m, "t") == [1]
        x = Var()
        assert [s["X"] for s in query(("profile_get", "foo", "k", x),
                                      {"X": x}, m)] == [1]

    def test_imported_profile_get_is_called(self, tmp_path):
        (tmp_path / f"{_PREFIX}pg_lib.pl").write_text(textwrap.dedent(f"""\
            :- module({_PREFIX}pg_lib, [profile_get/3]).
            profile_get(foo, k, 2).
        """))
        m = _load(tmp_path, "pg_user", f"""\
            :- use_module({_PREFIX}pg_lib, [profile_get/3]).
            t(V) :- profile_get(foo, k, V).
        """)
        assert _answers(m, "t") == [2]

    def test_atomic_is_the_iso_type_test(self, tmp_path):
        # was renamed to is_atomic/1, which does not exist
        m = _load(tmp_path, "atomic", """\
            t(X) :- atomic(foo), X = 1.
            t(X) :- atomic(f(a)), X = 2.
        """)
        assert _answers(m, "t") == [1]

    def test_a_program_defining_a_renamed_name_keeps_it(self, tmp_path):
        # time/1 maps to Clausal's time_goal/1 -- but not when the program
        # defines its own time/1
        m = _load(tmp_path, "owntime", """\
            time(7).
            t(X) :- time(X).
        """)
        assert _answers(m, "t") == [7]
        # ... and it is time/1 under its own name, as the program wrote it
        assert _answers(m, "time") == [7]
