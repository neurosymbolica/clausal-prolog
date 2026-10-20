"""A predicate IMPORTED under a special-form name runs as the import, with
its arguments as written, in a clause body exactly as through ``call/N``.

The ISO front end (``.pl`` and ``.clausal``) lowers the goal arguments of
the compiler's special forms -- ``once/1``, ``findall/3``, ``forall/2``,
``catch/3`` ... (``iso_l3._META_GOAL_ARGS``) -- as GOALS: a variable becomes
``call(X)``, a callable term a goal resolved at load.  It did so even when
the name was an import, so with ``:- use_module(m, [once/1]).`` the body
``once(X)`` called ``m:once(call(X))`` while ``call(once, X)`` and
``G = once(X), call(G)`` called ``m:once(X)``; ``once(foo(1))`` raised
``existence_error(procedure, foo/1)``; and the usage line library(re)'s
facade documents, ``:- use_module(library(re), [findall/3]).`` followed by
``findall("\\\\d", "a1b2", L)``, refused the file (``"a1b2"`` is not
callable).  The seam's ``-import_from`` never lowered the arguments of an
imported name as goals, so it already agreed (pinned in
``tests/test_call_runs_special_form_cells.py``).

Scryer, for the names that are no ISO builtin (``forall/2``, ``ignore/1``),
loads such a module and runs the import with the arguments as written, in
the body and through ``call/N`` alike.  It refuses a module that DEFINES an
ISO builtin (``once/1``, ``findall/3``, ``catch/3``) with
``permission_error(modify, static_procedure, PI)``; Clausal does not refuse
that yet (``todo/iso-a-file-can-redefine-a-builtin-2026-10-16.md``), and
until it does, the import is what runs on every route.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import textwrap

import pytest

from clausal import Var
from clausal.logic.solve import call
from clausal.logic.solve import _deref_walk

SURFACES = (".pl", ".clausal")

#: name -> (arity, the goal position the probe argument sits in).  Each
#: import binds that argument to ``mine`` and ignores the others.
IMPORTS = {
    "once": (1, 0),
    "findall": (3, 1),
    "forall": (2, 0),
    "catch": (3, 0),
}


class Tree:
    """A temporary ``sys.path`` entry; every module written is unloaded after."""

    def __init__(self, root, monkeypatch):
        self.root = root
        self.names: list[str] = []
        monkeypatch.syspath_prepend(str(root))

    def write(self, name: str, suffix: str, text: str) -> str:
        (self.root / (name + suffix)).write_text(
            textwrap.dedent(text).lstrip("\n"))
        self.names.append(name)
        sys.modules.pop(name, None)
        return name

    def load(self, name: str):
        importlib.invalidate_caches()
        return importlib.import_module(name)

    def close(self):
        for n in self.names:
            sys.modules.pop(n, None)
        for p in self.root.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        importlib.invalidate_caches()


@pytest.fixture
def tree(tmp_path, monkeypatch):
    t = Tree(tmp_path, monkeypatch)
    yield t
    t.close()


def _end(suffix, name):
    return f":- end_module({name}).\n" if suffix == ".clausal" else ""


def _args(name, x):
    """*name*'s argument list with *x* at the probe position, ``_`` elsewhere."""
    arity, at = IMPORTS[name]
    return ", ".join(x if i == at else "_" for i in range(arity))


def _importer(tree, suffix, tag, name):
    """Module ``<tag>_m`` defines and exports *name*; ``<tag>_u`` imports
    it and calls it four ways, each with an unbound argument at a position
    the special form takes as a goal."""
    export = f"{name}/{IMPORTS[name][0]}"
    m, u = f"{tag}_m", f"{tag}_u"
    tree.write(m, suffix, f"""
        :- module({m}, [{export}]).
        {name}({_args(name, "X")}) :- X = mine.
        {_end(suffix, m)}""")
    a = _args(name, "X")
    tree.write(u, suffix, f"""
        :- module({u}, [body/1, calln/1, univ/1, qualified/1, ground/0]).
        :- use_module({m}, [{export}]).
        body(X) :- {name}({a}).
        calln(X) :- call({name}, {a}).
        univ(X) :- G = {name}({a}), call(G).
        qualified(X) :- {m}:{name}({a}).
        ground :- {name}({_args(name, "mine")}).
        {_end(suffix, u)}""")
    return tree.load(u)


def _xs(mod, pred):
    X = Var()
    return [_deref_walk(X) for _ in call(pred, X, module=mod)]


@pytest.mark.parametrize("suffix", SURFACES)
@pytest.mark.parametrize("name", sorted(IMPORTS))
def test_the_body_runs_the_import_as_call_n_does(tree, suffix, name):
    mod = _importer(tree, suffix, f"isf_{name}_{suffix[1:]}", name)
    expected = ["mine"]
    assert _xs(mod, "calln") == expected
    assert _xs(mod, "univ") == expected
    assert _xs(mod, "body") == expected


@pytest.mark.parametrize("suffix", SURFACES)
@pytest.mark.parametrize("name", sorted(IMPORTS))
def test_a_qualified_call_runs_the_import_with_its_arguments(
        tree, suffix, name):
    mod = _importer(tree, suffix, f"isq_{name}_{suffix[1:]}", name)
    assert _xs(mod, "qualified") == ["mine"]


@pytest.mark.parametrize("suffix", SURFACES)
@pytest.mark.parametrize("name", sorted(IMPORTS))
def test_a_callable_argument_is_data_for_the_import(tree, suffix, name):
    """``once(mine)`` lowered ``mine`` as a goal, resolved at load:
    ``existence_error(procedure, mine/0)`` instead of the import's answer."""
    mod = _importer(tree, suffix, f"isg_{name}_{suffix[1:]}", name)
    assert len(list(call("ground", module=mod))) == 1


def test_library_re_findall_runs_from_a_clausal_body(tree):
    """The usage line of library(re)'s facade: the body findall/3 is the
    regex predicate, as ``call/N`` of it is."""
    tree.write("isf_re_u", ".clausal", r"""
        :- module(isf_re_u, [body/1, calln/1]).
        :- use_module(library(re), [findall/3]).
        body(L) :- findall("\\d", "a1b2", L).
        calln(L) :- call(findall, "\\d", "a1b2", L).
        :- end_module(isf_re_u).
        """)
    mod = tree.load("isf_re_u")
    expected = _xs(mod, "calln")
    assert expected and expected[0]          # not vacuous: two digits
    assert _xs(mod, "body") == expected


@pytest.mark.parametrize("suffix", SURFACES)
def test_an_unimported_special_form_still_lowers_its_goals(tree, suffix):
    """The control: with nothing imported, once/1 is the special form, and
    its argument is a goal."""
    tree.write(f"isf_plain_{suffix[1:]}", suffix, f"""
        :- module(isf_plain_{suffix[1:]}, [t/1]).
        t(X) :- once(member(X, [a, b])).
        {_end(suffix, f"isf_plain_{suffix[1:]}")}""")
    mod = tree.load(f"isf_plain_{suffix[1:]}")
    assert _xs(mod, "t") == ["a"]


@pytest.mark.parametrize("suffix", SURFACES)
def test_a_dropped_import_gives_the_special_form_its_goals_back(
        tree, suffix):
    """``use_module(m, [])`` after the clause drops the import, so the goal
    is the special form again: its argument, lowered as the import's data,
    is converted back to a goal (``call(X)``), not refused as a bare
    variable in goal position."""
    tag = f"isd_{suffix[1:]}"
    tree.write(f"{tag}_m", suffix, f"""
        :- module({tag}_m, [once/1]).
        once(X) :- X = mine.
        {_end(suffix, f"{tag}_m")}""")
    tree.write(f"{tag}_u", suffix, f"""
        :- module({tag}_u, [t/1]).
        :- use_module({tag}_m, [once/1]).
        t(X) :- once(X).
        :- use_module({tag}_m, []).
        {_end(suffix, f"{tag}_u")}""")
    mod = tree.load(f"{tag}_u")
    assert len(list(call("t", "true", module=mod))) == 1
    with pytest.raises(Exception, match="instantiation_error"):
        list(call("t", Var(), module=mod))
