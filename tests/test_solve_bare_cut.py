"""``solve("!")`` succeeds once, as ``call(!)`` does.

A cut that is the whole query is local to it (ISO 7.8.3) and cuts nothing.
``solve`` already answered the other zero-arity control constructs by name
(``true`` succeeds once, ``fail``/``false`` fail); ``!`` was looked up as a
procedure ``!/0`` and raised PredicateNotFoundError, while the goal
``call(!)`` succeeded.  A module-qualified ``M:!`` takes the same route.
"""
from __future__ import annotations

import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import once, solve


@pytest.fixture
def mod(tmp_path):
    path = tmp_path / "solvecut.clausal"
    path.write_text(textwrap.dedent("""
        p(1),
        p(2),
    """).lstrip())
    return _load_module("solvecut", str(path))


@pytest.mark.parametrize("goal", ["!", (":", "solvecut", "!"), ("call", "!")])
def test_a_whole_query_cut_succeeds_once(mod, goal):
    assert len(list(solve(goal, module=mod))) == 1


def test_qualified_cut_needs_no_module_argument(mod):
    assert len(list(solve((":", "solvecut", "!")))) == 1


def test_once_of_a_cut(mod):
    assert once("!", module=mod) is not None


def test_bare_cut_answers_like_true(mod):
    assert (len(list(solve("!", module=mod)))
            == len(list(solve("true", module=mod))) == 1)
