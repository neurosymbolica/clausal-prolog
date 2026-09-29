"""Fix batch 1 of the 2026-09-28 engine-bug triage.

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


# ── Batch 1 ──────────────────────────────────────────────────────────────────


class TestA3BareZeroArityBuiltinGoal:
    """``p <- nl`` and ``q <- halt``: a bare 0-arity builtin in goal position
    is the call of that builtin (ISO; Scryer), as ``fail`` already is."""

    def test_bare_nl_in_a_clause_body_runs_nl(self, tmp_path, monkeypatch, capsys):
        mod = _load(tmp_path, monkeypatch, "tri_a3_nl", """
            p <- nl,
            def run():
                if --p:
                    return 1
                return 0
        """)
        assert mod.run() == 1
        assert capsys.readouterr().out == "\n"

    def test_bare_halt_in_a_clause_body_loads_and_halts(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a3_halt", """
            q <- halt,
            def run():
                if --q:
                    return 1
                return 0
        """)
        with pytest.raises(SystemExit):
            mod.run()


class TestA4AliasToTitleCase:
    def test_an_alias_to_a_titlecase_name_is_refused(self, tmp_path, monkeypatch):
        with pytest.raises(SyntaxError, match="Fibo.*TitleCase"):
            _load(tmp_path, monkeypatch, "tri_a4", """
                -import_from(tri_a4lib, [alias(fib, Fibo)])
            """, libs={"tri_a4lib.seam": "fib(0, 0),\n"})

    def test_a_lowercase_alias_still_loads(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a4ok", """
            -import_from(tri_a4oklib, [alias(fib, fibo)])
            def run():
                return [X for X in --fibo(0, X)]
        """, libs={"tri_a4oklib.seam": "fib(0, 0),\n"})
        assert mod.run() == [0]


class TestA5UndeclaredFunctorWording:
    def test_the_message_speaks_of_declaring_the_functor(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_a5", """
            p(X) <- (X is nodecl5(1))
            def run():
                return [X for X in --p(X)]
        """)
        with pytest.raises(Exception) as exc:
            mod.run()
        msg = str(exc.value)
        assert "term class" not in msg
        assert "from your_module import" not in msg
        assert "-private([nodecl5(_)])" in msg


class TestB3aDcgNonterminalAtTwoArities:
    def test_state1_and_state2_pushback_rules_define_two_nonterminals(
            self, tmp_path, monkeypatch):
        """FLIPPED (2026-09-29 ruling, one name at several arities as in
        ISO): ``state//1`` and ``state//2`` are ``state/3`` and ``state/4``,
        two procedures.  B3a's defect -- the raw "keyword argument
        repeated" from ``compile`` -- must stay gone either way."""
        mod = _load(tmp_path, monkeypatch, "tri_b3a", """
            (state(S), [S]) >> ([S])
            (state(S0, S), [S]) >> ([S0])
        """)
        db = mod.__dict__["$module"].db
        assert len(db.clauses_for("state", 3)) == 1
        assert len(db.clauses_for("state", 4)) == 1

    def test_a_declared_nonterminal_at_two_arities_names_the_rule(
            self, tmp_path, monkeypatch):
        """A FIELDED declaration fixes the arities a clause head may have
        (each declared arity its own fields since 2026-09-29; state//2 is
        not declared here); the refusal names the rule instead of dying in
        ``compile``."""
        with pytest.raises(SyntaxError) as exc:
            _load(tmp_path, monkeypatch, "tri_b3a_decl", """
                -private([state(S, DCG0, DCG1)])
                (state(S), [S]) >> ([S])
                (state(S0, S), [S]) >> ([S0])
            """)
        msg = str(exc.value)
        assert "keyword argument repeated" not in msg
        assert "has exactly the arities its declarations name" in msg
        assert "state" in msg


class TestB4bAssertzContext:
    def test_assertz_at_an_undeclared_arity_names_assertz(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b4b", """
            -dynamic(foo/2)
            -private([a])
            def run():
                return [Z for Z in --(assertz(foo(a)), Z is 1)]
        """)
        with pytest.raises(LogicException) as exc:
            mod.run()
        term = _error_term(exc.value)
        assert term[1] == ("permission_error", "modify", "static_procedure", ("/", "foo", 1))  # R7
        assert term[2] == ("/", "assertz", 1)


class TestB5StrictAtomsSuggestion:
    def test_the_global_atom_suggestion_is_the_quoted_atom(self, tmp_path, monkeypatch):
        with pytest.raises(NameError) as exc:
            _load(tmp_path, monkeypatch, "tri_b5", "q <- colour(red5),\n")
        msg = str(exc.value)
        assert "global_atom('atom', Atom)" in msg
        assert 'global_atom("atom", Atom)' not in msg

    def test_the_suggested_spelling_works(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_b5ok", """
            def run():
                return [A for A in --global_atom('red', A)]
        """)
        assert mod.run() == ["red"]


class TestB6UndefinedAnswerPrintsTheGoal:
    def test_the_message_is_the_goal_not_the_ast(self, tmp_path, monkeypatch):
        from clausal.logic.seam import UndefinedAnswer
        mod = _load(tmp_path, monkeypatch, "tri_b6", """
            -table(win/1)
            move(1, 2),
            move(2, 1),
            win(X) <- (move(X, Y), not win(Y))
            def run():
                return [X for X in --win(X)]
            def run1():
                if --win(1):
                    return 1
                return 0
        """)
        for fn in (mod.run, mod.run1):
            with pytest.raises(UndefinedAnswer) as exc:
                fn()
            msg = str(exc.value)
            assert "LoadName" not in msg and "Call(" not in msg
            assert "win(" in msg


class TestC12ListingPrintsStrings:
    def test_listing_writes_a_string_as_writeq_would(self, tmp_path, monkeypatch, capsys):
        mod = _load(tmp_path, monkeypatch, "tri_c12", """
            -dynamic(s/1)
            -private([b])
            s("a"),
            t(b),
            w <- listing('/'('s', 1))
            v <- listing('/'('t', 1))
            def run():
                out = []
                if --w:
                    out.append(True)
                if --v:
                    out.append(True)
                return tuple(out)
        """)
        assert mod.run() == (True, True)
        out = capsys.readouterr().out
        assert "'$chars'" not in out
        assert '"a"' in out
        assert "t(b)." in out

    def test_listing_does_not_fold_past_an_order_sensitive_goal(
            self, tmp_path, monkeypatch, capsys):
        mod = _load(tmp_path, monkeypatch, "tri_c12b", """
            p(X) <- (var(Y), X is Y)
            w <- listing('/'('p', 1))
            def run():
                if --w:
                    return True
                return False
        """)
        assert mod.run() is True
        out = capsys.readouterr().out
        # moved into the head it would read p(Y) <- var(Y): a different clause
        assert "var(" in out and " is " in out


class TestC16FloatBesideExactMessage:
    def test_the_remedy_is_a_spelling_that_loads(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_c16", """
            -import_from(united_states, [usd])
            def run():
                return [X for X in --eval_(1.5 * 10 (usd), X)]
            def exact():
                return [X for X in --eval_(rdiv(3, 2) * 10 (usd), X)]
        """)
        with pytest.raises(LogicException) as exc:
            mod.run()
        msg = str(exc.value)
        assert "decimal(M, S)" not in msg
        assert "rdiv(3, 2)" in msg
        assert _error_term(exc.value)[2] == ("/", "*", 2)
        # the suggested spelling answers
        assert len(mod.exact()) == 1


class TestC17RdivCulpritRendering:
    def test_a_quantity_culprit_renders_as_the_quantity(self, tmp_path, monkeypatch):
        mod = _load(tmp_path, monkeypatch, "tri_c17", """
            -import_from(united_states, [usd])
            def run():
                return [X for X in --eval_(rdiv(10 (usd), 3), X)]
        """)
        with pytest.raises(LogicException) as exc:
            mod.run()
        msg = str(exc.value)
        assert "Decimal(" not in msg and "{'usd'" not in msg
        assert "10 (usd)" in msg


def test_c9_date_module_docstring_matches_behaviour():
    import clausal.modules.py.datetime as dtmod
    assert "type_error(orderable" not in (dtmod.__doc__ or "")


def test_c4_item_is_gone_from_the_iso_report():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = open(os.path.join(here, "docs", "iso_prolog_compatibility_report.md")).read()
    # Scryer answers ``'<'(1, a)`` with exactly the same term, so it is no
    # difference to report.
    assert "The culprit of an ISO comparison names" not in text
