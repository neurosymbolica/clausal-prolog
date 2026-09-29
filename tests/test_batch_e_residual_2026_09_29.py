"""Fix batch E (2026-09-29): residue of the 2026-09-28 engine-bug triage,
re-verified on main 44b358a9.

Each test is a repro turned round to pin the fixed behaviour.
"""
import sys
import textwrap

import pytest

from clausal.import_hook import _load_module


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


class TestStructuralEqSeesABoundVariableInsideATerm:
    """todo/structural-eq-misses-a-variable-bound-inside-a-list-2026-09-28:
    the bare ``==`` ground fallback compared a list/cell holding a BOUND
    variable against its value and answered false.  ISO ==/2 (8.4.1.1)
    dereferences every subterm; so do unification and the quoted '=='."""

    SRC = """
        -allow_singletons
        -private([f(_)])
        t1(X) <- (X is [Y], Y is 1, X == [1])
        t2(X) <- (X is ['-'(Y, 2)], Y is 1, X == ['-'(1, 2)])
        t3(X) <- (X is f(Y), Y is 1, X == f(1))
        q1(X) <- (Y is 1, X is [Y], X == [1])
        d1(X) <- (X is {'k': Y}, Y is 1, X == {'k': 1})
        n1(X) <- (X is [Y], Y is 1, X != [1])
        n2(X) <- (X is [Y], Y is 2, X != [1])
        u1(X) <- (X is [Y], X == [1])
        w1(X) <- (X is [Y], Y is 2, X == [1])
        def run(name):
            return [X for X in --call(++name, X)]
    """

    @pytest.mark.parametrize("name", ["t1", "t2", "t3", "q1", "d1", "n2"])
    def test_holds(self, tmp_path, monkeypatch, name):
        mod = _load(tmp_path, monkeypatch, "eq_bound_in_term", self.SRC)
        assert len(mod.run(name)) == 1

    @pytest.mark.parametrize("name", ["n1", "u1", "w1"])
    def test_does_not_hold(self, tmp_path, monkeypatch, name):
        mod = _load(tmp_path, monkeypatch, "eq_bound_in_term", self.SRC)
        assert mod.run(name) == []


class TestC1PrologDataFunctorsAreDeclared:
    """C1: an imported ``.pl`` whose clauses build compound DATA terms
    (``p(f(1)).``, ``X = g(2)``) loaded but raised
    existence_error(procedure, f/1) at run time -- the translator declared
    the file's data atoms but not its data functors.  ISO/Scryer answer
    ``p(f(1))``."""

    LIB = {"c1_lib.pl": """
        p(f(1)).
        q(X) :- X = g(2).
        r([h(a), h(b)]).
        s(Y) :- findall(X, member(X, [1, 2]), Y).
        t(u(1)).
        u(_).
        add(X) :- assertz(counter(X)).
        cnt(L) :- findall(X, counter(X), L).
    """}

    SRC = """
        -import_from(c1_lib, [p, q, r, s, t])
        def run():
            return ([X for X in --p(X)], [X for X in --q(X)],
                    [X for X in --r(X)], [X for X in --s(X)],
                    [X for X in --t(X)])
    """

    def test_data_terms_answer(self, tmp_path, monkeypatch):
        from clausal import to_python
        mod = _load(tmp_path, monkeypatch, "c1_main", self.SRC, libs=self.LIB)
        p, q, r, s, t = mod.run()
        assert p == [("f", 1)]
        assert q == [("g", 2)]
        assert r == [[("h", "a"), ("h", "b")]]
        assert s == [[1, 2]]
        assert t == [("u", 1)]

    def test_translation_declares_only_data_functors(self):
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        out = prolog_to_clausal(textwrap.dedent(self.LIB["c1_lib.pl"]))
        (private,) = [ln for ln in out.splitlines() if ln.startswith("-private(")]
        for spec in ("f(_)", "g(_)", "h(_)"):
            assert spec in private
        # a builtin (member/2) and a predicate the file defines (u/1) are
        # not data functors: declaring them would shadow the predicate
        assert "member(" not in private
        assert "u(" not in private
        # a predicate assertz creates at run time, called only through
        # meta-predicates, is not a data functor either
        assert "counter(" not in private

    def test_a_predicate_asserted_at_run_time_still_works(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "c1_main2", """
            -import_from(c1_lib, [add, cnt])
            def run():
                if not --add(7):
                    raise AssertionError("add(7) failed")
                return [L for L in --cnt(L)]
        """, libs=self.LIB)
        assert mod.run() == [[7]]

    @staticmethod
    def _private(src):
        from clausal.tools.prolog_to_clausal import prolog_to_clausal
        lines = [ln for ln in prolog_to_clausal(src).splitlines()
                 if ln.startswith("-private(")]
        return lines[0] if lines else ""

    def test_a_name_used_as_data_at_two_arities_is_declared_at_both(self):
        # declared field names are per (name, arity) since 2026-09-29
        # ("-module(lib, [q(X), q(X, Y)]): allow it"); it used to be left
        # undeclared, and the load then raised
        assert self._private("r(f(1)).\ns(f(1, 2)).\n") == (
            "-private([f(_), f(_, _)])")

    def test_an_evaluable_name_is_matched_by_arity(self):
        # atan2/2 is an evaluable (left alone); atan2/3 is only data here
        assert "atan2(" not in self._private("t(X) :- X = atan2(1, 2).\n")
        assert "atan2(_, _, _)" in self._private("t(X) :- X = atan2(1, 2, 3).\n")

    def test_an_atom_and_a_functor_of_one_name(self, tmp_path, monkeypatch):
        # the atom is written quoted ('a'), so only a(_) is declared and
        # both answers come back (roborev round 1 asked)
        assert self._private("p(a).\nq(a(1)).\n") == "-private([a(_)])"
        mod = _load(tmp_path, monkeypatch, "c1_main3", """
            -import_from(c1_lib3, [p, q])
            def run():
                return [X for X in --p(X)], [X for X in --q(X)]
        """, libs={"c1_lib3.pl": "p(a).\nq(a(1)).\n"})
        assert mod.run() == (["a"], [("a", 1)])
