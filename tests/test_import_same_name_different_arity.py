"""Importing ``p/1`` from one module and ``p/2`` from another keeps BOTH.

A predicate is named by name AND arity (ISO), so ``p/1`` from ``m1`` and
``p/2`` from ``m2`` are two unrelated procedures, and a module may import
each from wherever it lives -- Scryer and SWI keep both.  Clausal kept only
the later import: a module namespace holds one binding per NAME, the second
import overwrote the first, and a call ``p(X)`` then raised an arity
mismatch against ``m2``'s ``p/2``, although the importer's database had
adopted ``m1``'s ``p/1`` row.

Both surfaces: a ``.clausal`` ``:- use_module(M, [p/N])`` (and a whole-module
``:- use_module(M)``) and the seam's ``-import_from``.  The calls are direct
body calls and meta-calls (``call/N``, ``maplist``).

todo/clausal-surface-gaps-found-moving-the-docs-2026-10-17.md, item 5.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import textwrap

import pytest

from clausal import Var
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.predicate_diagnostics import PredicateArityMismatchError
from tests._suffix import SEAM


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


def _answers(mod, name, arity):
    args = [Var() for _ in range(arity)]
    return [tuple(deref(a) for a in args)
            for _ in call(name, *args, module=mod)]


# ── Clausal Prolog (.clausal) ───────────────────────────────────────────────


def _clausal_libs(tree, prefix):
    tree.write(f"{prefix}_m1", ".clausal", f"""
        :- module({prefix}_m1, [p/1]).
        p(one).
        :- end_module({prefix}_m1).
    """)
    tree.write(f"{prefix}_m2", ".clausal", f"""
        :- module({prefix}_m2, [p/2]).
        p(two, 2).
        :- end_module({prefix}_m2).
    """)


_CLAUSAL_BODY = """
    t1(X) :- p(X).
    t2(X, Y) :- p(X, Y).
    c1(X) :- call(p, X).
    c2(X, Y) :- call(p, X, Y).
    m1(L) :- maplist(p, L).
"""


def _clausal_importer(tree, name, directives):
    tree.write(name, ".clausal",
               f":- module({name}, [t1/1, t2/2, c1/1, c2/2, m1/1]).\n"
               + "".join(f":- {d}.\n" for d in directives)
               + textwrap.dedent(_CLAUSAL_BODY).lstrip("\n")
               + f":- end_module({name}).\n")
    return tree.load(name)


class TestClausalPrologTwoModules:

    @pytest.mark.parametrize("order", ["p1_first", "p2_first"])
    def test_both_indicator_imports_answer(self, tree, order):
        _clausal_libs(tree, "isda_c")
        directives = ["use_module(isda_c_m1, [p/1])",
                      "use_module(isda_c_m2, [p/2])"]
        if order == "p2_first":
            directives.reverse()
        mod = _clausal_importer(tree, f"isda_c_main_{order}", directives)
        assert _answers(mod, "t1", 1) == [("one",)]
        assert _answers(mod, "t2", 2) == [("two", 2)]

    def test_meta_calls_reach_both(self, tree):
        _clausal_libs(tree, "isda_m")
        mod = _clausal_importer(tree, "isda_m_main", [
            "use_module(isda_m_m1, [p/1])",
            "use_module(isda_m_m2, [p/2])"])
        assert _answers(mod, "c1", 1) == [("one",)]
        assert _answers(mod, "c2", 2) == [("two", 2)]
        lst = [Var()]
        assert len(list(call("m1", lst, module=mod))) == 1

    def test_whole_module_imports_keep_both(self, tree):
        _clausal_libs(tree, "isda_w")
        mod = _clausal_importer(tree, "isda_w_main", [
            "use_module(isda_w_m1)", "use_module(isda_w_m2)"])
        assert _answers(mod, "t1", 1) == [("one",)]
        assert _answers(mod, "t2", 2) == [("two", 2)]
        assert _answers(mod, "c1", 1) == [("one",)]

    def test_one_module_exporting_both_arities(self, tree):
        tree.write("isda_s_m", ".clausal", """
            :- module(isda_s_m, [p/1, p/2]).
            p(a).
            p(b, 2).
            :- end_module(isda_s_m).
        """)
        mod = _clausal_importer(tree, "isda_s_main", [
            "use_module(isda_s_m, [p/1, p/2])"])
        assert _answers(mod, "t1", 1) == [("a",)]
        assert _answers(mod, "t2", 2) == [("b", 2)]

    def test_an_arity_imported_from_neither_is_still_refused(self, tree):
        _clausal_libs(tree, "isda_r")
        tree.write("isda_r_main", ".clausal", """
            :- module(isda_r_main, [t3/3]).
            :- use_module(isda_r_m1, [p/1]).
            :- use_module(isda_r_m2, [p/2]).
            t3(X, Y, Z) :- p(X, Y, Z).
            :- end_module(isda_r_main).
        """)
        mod = tree.load("isda_r_main")
        with pytest.raises(PredicateArityMismatchError):
            _answers(mod, "t3", 3)


# ── The seam (-import_from) ─────────────────────────────────────────────────


def _seam_libs(tree, prefix):
    tree.write(f"{prefix}_s1", SEAM, f"""
        -module({prefix}_s1, [p/1, one])
        p(one),
    """)
    tree.write(f"{prefix}_s2", SEAM, f"""
        -module({prefix}_s2, [p/2, two])
        p(two, 2),
    """)


_SEAM_BODY = """
    t1(X) <- p(X)
    t2(X, Y) <- p(X, Y)
    c1(X) <- call(p, X)
    c2(X, Y) <- call(p, X, Y)
"""


def _seam_importer(tree, name, directives):
    tree.write(name, SEAM, "".join(f"{d}\n" for d in directives) + "\n"
               + textwrap.dedent(_SEAM_BODY).lstrip("\n"))
    return tree.load(name)


class TestSeamTwoModules:

    @pytest.mark.parametrize("entries", ["indicators", "bare_names"])
    def test_both_imports_answer(self, tree, entries):
        prefix = f"isda_{entries}"
        _seam_libs(tree, prefix)
        p1, p2 = (("p/1", "p/2") if entries == "indicators" else ("p", "p"))
        mod = _seam_importer(tree, f"{prefix}_main", [
            f"-import_from({prefix}_s1, [{p1}])",
            f"-import_from({prefix}_s2, [{p2}])"])
        assert _answers(mod, "t1", 1) == [("one",)]
        assert _answers(mod, "t2", 2) == [("two", 2)]
        assert _answers(mod, "c1", 1) == [("one",)]
        assert _answers(mod, "c2", 2) == [("two", 2)]
