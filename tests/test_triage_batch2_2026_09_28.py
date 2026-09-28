"""Fix batch 2 of the 2026-09-28 engine-bug triage.

Each test is the triage's repro for one item, turned round to pin the fixed
behaviour.  Batch 1: messages and error shapes (no answer moves).  Batch 2:
crashes that become ISO error terms or answers.
"""
import importlib
import os
import sys
import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException


def _load(tmp_path, monkeypatch, name, src, libs=None, ext="seam"):
    """Load *src* as module *name* from *tmp_path*; *libs* are sibling files
    ``{filename: source}`` the module may import."""
    monkeypatch.syspath_prepend(str(tmp_path))
    for fname, lsrc in (libs or {}).items():
        (tmp_path / fname).write_text(textwrap.dedent(lsrc))
        sys.modules.pop(fname.rsplit(".", 1)[0], None)
    path = tmp_path / f"{name}.{ext}"
    path.write_text(textwrap.dedent(src))
    sys.modules.pop(name, None)
    return _load_module(name, str(path))


def _error_term(exc):
    from clausal.logic.solve import _deref_walk
    return _deref_walk(exc.term)


# ── Batch 2 ──────────────────────────────────────────────────────────────────


class TestA1C8SeamAnswersThatDoNotHash:
    def test_a_partial_list_answer_comes_through(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a1", """
            pl(L) <- (L is [1, *_])
            def run():
                return [L for L in --(L is [1, *_])]
            def run2():
                return [L for L in --pl(L)]
        """)
        # (``L is [1, *_], L is [H, *_]`` -- the triage's first spelling --
        # FAILS on main as well: two open partial lists do not unify.  That is
        # a separate wrong answer, not this crash.)
        for fn in (mod.run, mod.run2):
            (answer,) = fn()
            assert answer[0] == 1

    def test_a_dict_holding_a_list_comes_through(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_c8", """
            -private([a])
            m({a: [1, 2]}),
            def run():
                return [M for M in --m(M)]
        """)
        (answer,) = mod.run()
        assert answer["a"] == [1, 2]


class TestA2ImportedZeroArityGoal:
    LIB = {"tri_a2lib.seam": "ask,\n"}

    def test_if_seam_over_an_imported_atom_goal(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a2", """
            -import_from(tri_a2lib, [ask])
            def run():
                out = []
                if --ask:
                    out.append("ask")
                if --ask():
                    out.append("ask()")
                return out
        """, libs=self.LIB)
        assert mod.run() == ["ask", "ask()"]

    def test_clause_body_calling_an_imported_atom_goal(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a2d", """
            -import_from(tri_a2lib, [ask])
            p <- ask,
            def run():
                if --p:
                    return 1
                return 0
        """, libs=self.LIB)
        assert mod.run() == 1


class TestB3bPhraseWithAControlBody:
    SRC = """
        (state(S), [S]) >> ([S])
        (state2(S0, S), [S]) >> ([S0])
        inc >> (state(N0), {N == N0 + 1}, state2(_, N))
        def one():
            return [N for N in --phrase(inc, [0], [N])]
        def conj():
            return [N for N in --('=..'(G, [',', inc, inc]), phrase(G, [0], [N]))]
        def disj():
            return [N for N in --('=..'(C, [',', inc, inc]), '=..'(G, [';', inc, C]),
                                  phrase(G, [0], [N]))]
        def terminals():
            return [R for R in --('=..'(G, [',', [a], [b]]), phrase(G, [a, b, c], R))]
    """

    def test_conjunction_and_disjunction_bodies(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b3b",
                    "-private([a, b, c])\n" + textwrap.dedent(self.SRC))
        assert mod.one() == [1]
        assert mod.conj() == [2]
        assert mod.disj() == [1, 2]
        assert mod.terminals() == [["c"]]

    def test_a_conjunction_tuple_of_three_goals(self, tmp_path, monkeypatch):
        # (ws, eol) left over as a bare tuple would read as the CELL ws(eol);
        # the translation must build explicit ',' cells (roborev round 1).
        mod = _load(tmp_path, monkeypatch, "tri_b3b3", """
            -private([a, b, c])
            ws >> [b]
            eol >> [c]
            def run():
                return [G for G in --(G is ([a], ws, eol), phrase(G, [a, b, c]))]
        """)
        assert len(mod.run()) == 1


class TestB4aAssertzUnbound:
    def test_assertz_of_a_variable_is_an_instantiation_error(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b4a", """
            def run():
                return [Z for Z in --(assertz(_), Z is 1)]
        """)
        with pytest.raises(LogicException) as exc:
            mod.run()
        term = _error_term(exc.value)
        assert term[1] == "instantiation_error"
        assert term[2] == ("/", "assertz", 1)


class TestB4cC1C3UndeclaredFunctor:
    def test_assertz_of_an_undeclared_name_is_a_permission_error(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b4c", """
            def run():
                return [Z for Z in --(assertz(nodecl(1)), Z is 1)]
            def caught():
                return [E for E in --catch(assertz(nodecl(1)), E, True)]
        """)
        with pytest.raises(LogicException) as exc:
            mod.run()
        term = _error_term(exc.value)
        assert term[1] == ("permission_error", "modify", "static_procedure",
                           ("/", "nodecl", 1))  # ruling R7
        assert term[2] == ("/", "assertz", 1)
        # and catch/3 sees the ISO term, not a transliterated NameError
        (e,) = mod.caught()
        assert e[1] == ("permission_error", "modify", "static_procedure",
                        ("/", "nodecl", 1))

    def test_it_is_still_a_name_error_for_python_callers(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b4c2", """
            def run():
                return [Z for Z in --(assertz(nodecl(1)), Z is 1)]
        """)
        with pytest.raises(NameError):
            mod.run()

    def test_an_undeclared_functor_in_arithmetic_is_not_evaluable(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_c3", """
            def run():
                return [X for X in --'is'(X, nosuchfn(-3))]
            def run2():
                return [X for X in --(X == nosuchfn(2, 5))]
        """)
        for fn, pi in ((mod.run, ("/", "nosuchfn", 1)),
                       (mod.run2, ("/", "nosuchfn", 2))):
            with pytest.raises(LogicException) as exc:
                fn()
            assert _error_term(exc.value)[1] == ("type_error", "evaluable", pi)

    def test_a_pl_data_functor_is_an_iso_error_term(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_c1", """
            -import_from(tri_c1lib, [p])
            def run():
                return [X for X in --p(X)]
        """, libs={"tri_c1lib.pl": "p(f(1)).\n"})
        with pytest.raises(LogicException) as exc:
            mod.run()
        assert _error_term(exc.value)[1] == (
            "existence_error", "procedure", ("/", "f", 1))


class TestC13OpaquePythonObjects:
    @pytest.mark.parametrize("make", [
        lambda: __import__("socket").socket(),
        object,
        lambda: __import__("threading").Lock(),
    ])
    def test_solve_passes_an_opaque_object_through(self, make):
        from clausal import Module, Var, solve
        obj = make()
        try:
            X = Var()
            got = [X.value for _ in solve(("=", X, obj), module=Module("tri_c13"))]
            assert len(got) == 1 and got[0] is obj
        finally:
            close = getattr(obj, "close", None)
            if close is not None:
                close()

    def test_nested_opaque_object(self):
        from clausal import Module, Var, solve
        obj = object()
        X = Var()
        from clausal.logic.solve import _deref_walk
        got = [_deref_walk(X) for _ in solve(("=", X, [1, obj]),
                                             module=Module("tri_c13b"))]
        assert len(got) == 1 and got[0][0] == 1 and got[0][1] is obj
