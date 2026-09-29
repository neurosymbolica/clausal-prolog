"""One name at several arities in one file, as in ISO (operator ruling
2026-09-29).

ISO 13211-1 identifies a procedure by its predicate indicator ``Name/Arity``:
``p/1`` and ``p/2`` are unrelated procedures, and one file may define both.
Clausal used to refuse the second arity at load ("A functor name has exactly
one arity in Clausal").  The plan and census are in
``implementation_plans/multi-arity-names-2026-09-29.md``; its decision
numbers (D1-D9) are cited below.

What STAYS an error (D2): a clause head of a name whose FIELD NAMES were
declared -- a fielded ``-module``/``-private`` entry, ``-edcg_pred`` -- at an
arity no declaration names (since the per-arity ruling a list may declare
several arities, ``test_fields_per_arity.py``; ``-edcg_pred`` keeps one); a
call at an arity the name does not have is still refused (D7).
"""

from __future__ import annotations

import ast
import os
import textwrap

import pytest

from clausal import Var
from clausal.import_hook import EmbedTransformer, _load_module
from clausal.logic.predicate import field_names_for, is_declared_predicate
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.predicate_diagnostics import PredicateArityMismatchError


def _load(tmp_path, name, text, ext=".clausal"):
    path = os.path.join(tmp_path, name + ext)
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(text))
    return _load_module(f"tests_marity_{name}", path)


def _answers(mod, name, *args):
    """Every answer of ``name(*args)``, each a tuple of the dereferenced
    arguments."""
    out = []
    for _ in call(name, *args, module=mod):
        out.append(tuple(deref(a) for a in args))
    return out


def _db(mod):
    return mod.__clausal_module__.db


# ── D1: a procedure name at two arities loads, each arity its own ──────────


class TestTwoAritiesLoad:

    def test_the_minimal_repro(self, tmp_path):
        mod = _load(tmp_path, "repro", """
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
        """)
        x = Var()
        assert _answers(mod, "p", x) == [(1,)]
        x = Var()
        assert _answers(mod, "p", x, 3) == [(3, 3)]

    def test_each_arity_is_its_own_procedure(self, tmp_path):
        mod = _load(tmp_path, "separate", """
            f(1),
            f(1, 2),
            f(2),
            f(3, 4),
        """)
        db = _db(mod)
        assert len(db.clauses_for("f", 1)) == 2
        assert len(db.clauses_for("f", 2)) == 2
        x = Var()
        assert _answers(mod, "f", x) == [(1,), (2,)]

    def test_the_shorter_head_first(self, tmp_path):
        mod = _load(tmp_path, "shortfirst", """
            -private([art, meta])
            citation(art),
            citation(art, "Reg-Z Article 1(2)", meta),
        """)
        db = _db(mod)
        assert len(db.clauses_for("citation", 1)) == 1
        assert len(db.clauses_for("citation", 3)) == 1

    def test_a_zero_arity_head_beside_a_compound_one(self, tmp_path):
        mod = _load(tmp_path, "zero", """
            -private([a, b])
            foo(a, b),
            foo,
            bar,
            bar(1),
        """)
        db = _db(mod)
        assert len(db.clauses_for("foo", 2)) == 1
        assert len(db.clauses_for("foo", 0)) == 1
        assert len(db.clauses_for("bar", 0)) == 1
        assert len(db.clauses_for("bar", 1)) == 1

    def test_each_arity_keeps_its_own_field_names(self, tmp_path):
        mod = _load(tmp_path, "fields", """
            area(SHAPE) <- (SHAPE is 1)
            area(W, H) <- (W is H)
        """)
        db = _db(mod)
        handle = mod.area
        assert field_names_for(handle, arity=1, db=db) == ("shape",)
        assert field_names_for(handle, arity=2, db=db) == ("w", "h")
        assert is_declared_predicate(handle, arity=1, db=db)
        assert is_declared_predicate(handle, arity=2, db=db)
        assert not is_declared_predicate(handle, arity=3, db=db)

    def test_one_arity_calls_the_other(self, tmp_path):
        """The ``call_goal/1..N`` shape: the short one delegates."""
        mod = _load(tmp_path, "delegate", """
            len(L, N) <- len(L, 0, N)
            len([], ACC, ACC),
            len([_, *T], ACC, N) <- (eval_(ACC + 1, ACC1), len(T, ACC1, N))
        """)
        n = Var()
        assert _answers(mod, "len", [1, 2, 3], n) == [([1, 2, 3], 3)]

    def test_a_dcg_nonterminal_at_two_arities(self, tmp_path):
        mod = _load(tmp_path, "dcg", """
            state(S) >> [S]
            state(S0, S) >> [S0, S]
            state(S) >> [S, S]
        """)
        db = _db(mod)
        assert len(db.clauses_for("state", 3)) == 2
        assert len(db.clauses_for("state", 4)) == 1

    def test_a_compound_in_data_position_is_built_at_the_written_arity(
            self, tmp_path):
        """D5: data construction never has to choose an arity."""
        mod = _load(tmp_path, "data", """
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
            mk(T1, T2, A) <- (T1 is p(1), T2 is p(1, 2), A is p)
        """)
        t1, t2, a = Var(), Var(), Var()
        [(r1, r2, ra)] = _answers(mod, "mk", t1, t2, a)
        assert r1 == ("p", 1)
        assert r2 == ("p", 1, 2)
        assert ra == "p"          # D4: bare p is the atom

    def test_call_n_reaches_either_arity(self, tmp_path):
        mod = _load(tmp_path, "calln", """
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
            both(A, B) <- (call(p, A), call(p, B, 7))
        """)
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 7)]

    def test_a_call_at_a_third_arity_is_still_refused(self, tmp_path):
        """D7."""
        mod = _load(tmp_path, "third", """
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
            q <- p(1, 2, 3)
        """)
        with pytest.raises(PredicateArityMismatchError):
            list(call("q", module=mod))

    def test_a_dynamic_name_at_two_arities(self, tmp_path):
        mod = _load(tmp_path, "dyn", """
            -dynamic(seen/1, seen/2)
            go <- (assertz(seen(1)), assertz(seen(1, 2)))
        """)
        list(call("go", module=mod))
        db = _db(mod)
        assert len(db.clauses_for("seen", 1)) == 1
        assert len(db.clauses_for("seen", 2)) == 1

    def test_exported_at_two_arities_and_imported(self, tmp_path):
        _load(tmp_path, "marity_lib", """
            -module(marity_lib, [g/1, g/2])
            g(X) <- (X is 1)
            g(X, Y) <- (X is Y)
        """)
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            mod = _load(tmp_path, "marity_user", """
                -import_from(marity_lib, [g])
                both(A, B) <- (g(A), g(B, 5))
            """)
        finally:
            sys.path.remove(str(tmp_path))
        a, b = Var(), Var()
        assert _answers(mod, "both", a, b) == [(1, 5)]


# ── D2: a DECLARED field layout stays one arity per file ───────────────────


class TestDeclaredFieldsStayOneArity:

    def test_a_fielded_private_entry_at_another_arity(self, tmp_path):
        with pytest.raises(SyntaxError, match="conflicts with the declaration"):
            _load(tmp_path, "priv", """
                -private([h(A, B)])
                h(1, 2, 3),
            """)

    def test_a_fielded_module_export_at_another_arity(self, tmp_path):
        with pytest.raises(SyntaxError, match="conflicts with the declaration"):
            _load(tmp_path, "modexp", """
                -module(modexp, [f(A)])
                f(1, 2),
            """)

    def test_the_iso_spelling_in_the_export_list_is_free(self, tmp_path):
        mod = _load(tmp_path, "modiso", """
            -module(modiso, [f/1, f/2])
            f(1),
            f(1, 2),
        """)
        db = _db(mod)
        assert len(db.clauses_for("f", 1)) == 1
        assert len(db.clauses_for("f", 2)) == 1

    def test_an_edcg_predicate_at_another_arity(self, tmp_path):
        with pytest.raises(SyntaxError, match="conflicts with the declaration"):
            _load(tmp_path, "edcg", """
                -edcg_pred(q, 1, [])
                q(1, 2),
            """)


# ── D9 / the no-change guarantee ───────────────────────────────────────────


def _rewrite(text):
    src = textwrap.dedent(text)
    tree = ast.parse(src)
    t = EmbedTransformer(source_lines=src.splitlines(keepends=True),
                         filename="x.clausal")
    tree = t.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), t._module_items


class TestSingleArityOutputIsUnchanged:

    def test_a_single_arity_file_declares_each_name_once(self):
        out, _items = _rewrite("""
            p(X) <- (X is 1)
            p(2),
        """)
        assert out.count("$declare_head('p'") == 1

    def test_a_second_arity_declares_its_own_head(self):
        out, items = _rewrite("""
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
        """)
        assert "$declare_head('p', ('x',))" in out
        assert "$declare_head('p', ('x', 'y'))" in out
        [hf] = [i for i in items if type(i).__name__ == "HeadFieldNames"]
        assert hf.fields == {"p": ("x",)}
        assert hf.by_arity == {("p", 1): ("x",), ("p", 2): ("x", "y")}


def test_a_declared_conflict_names_the_per_arity_declaration(tmp_path):
    """Since the per-arity ruling (2026-09-29, "-module(lib, [q(X),
    q(X, Y)]): allow it") the way out is to declare the second arity too;
    the ISO indicator stays an alternative."""
    with pytest.raises(SyntaxError) as info:
        _load(tmp_path, "isonote", """
            -module(isonote, [f(A)])
            f(1, 2),
        """)
    flat = " ".join(str(info.value).split())
    assert "declare it in the same list, as `f(A, ARG_1)`" in flat
    assert "or as `f/2`" in flat


def test_a_prolog_file_defining_call_goal_1_to_8_imports(tmp_path):
    """The trigger: the ``.pl`` import path could not load a file defining
    ``call_goal/1..8`` (every arity after the first was refused)."""
    from clausal.import_hook import _load_prolog_module
    exports = ", ".join(f"call_goal/{n}" for n in range(1, 9))
    clauses = []
    for n in range(1, 9):
        extra = ", ".join(f"A{i}" for i in range(1, n))
        head = f"call_goal(G{', ' + extra if extra else ''})"
        body = f"call(G{', ' + extra if extra else ''})"
        clauses.append(f"{head} :- {body}.")
    src = (f":- module(cg_pl, [{exports}, succ_of/2]).\n"
           + "\n".join(clauses)
           + "\nsucc_of(X, Y) :- Y is X + 1.\n")
    path = os.path.join(tmp_path, "cg_pl.pl")
    with open(path, "w") as fh:
        fh.write(src)
    mod = _load_prolog_module("tests_marity_cg_pl", path)
    db = _db(mod)
    for n in range(1, 9):
        assert len(db.clauses_for("call_goal", n)) == 1, n
    y = Var()
    assert _answers(mod, "call_goal", "succ_of", 1, y) == [("succ_of", 1, 2)]


class TestReviewRound1:
    """roborev round 1 (2026-09-29)."""

    def test_a_fielded_declaration_after_two_arities_is_refused(
            self, tmp_path):
        """D2 must not depend on order: a fielded -private entry BELOW
        clauses at two arities that declares only ONE of them leaves the
        other undeclared (declaring both loads since the per-arity ruling,
        ``test_fields_per_arity.py``)."""
        with pytest.raises(SyntaxError, match="does not declare f/2"):
            _load(tmp_path, "latepriv", """
                f(1),
                f(1, 2),
                -private([f(A)])
            """)

    def test_a_fielded_declaration_after_one_arity_still_loads(
            self, tmp_path):
        """Unchanged from before the ruling: one arity, declared late."""
        mod = _load(tmp_path, "latepriv1", """
            f(1),
            -private([f(A)])
        """)
        assert len(_db(mod).clauses_for("f", 1)) == 1

    def test_a_dynamic_placeholder_a_zero_fact_and_a_real_head(self, tmp_path):
        mod = _load(tmp_path, "dynzero", """
            -dynamic(foo/2)
            foo,
            foo(X, Y) <- (X is Y)
            foo,
        """)
        db = _db(mod)
        assert len(db.clauses_for("foo", 0)) == 2
        assert len(db.clauses_for("foo", 2)) == 1
        out, items = _rewrite("""
            -dynamic(foo/2)
            foo,
            foo(X, Y) <- (X is Y)
            foo,
        """)
        assert out.count("$declare_head('foo', ())") == 1
        [hf] = [i for i in items if type(i).__name__ == "HeadFieldNames"]
        assert hf.by_arity == {("foo", 0): (), ("foo", 2): ("x", "y")}

    def test_an_edcg_declaration_after_two_arities_is_refused(self, tmp_path):
        with pytest.raises(SyntaxError, match="one arity"):
            _load(tmp_path, "lateedcg", """
                q(1),
                q(1, 2),
                -edcg_pred(q, 1, [])
            """)

    def test_a_data_construction_at_a_third_arity(self, tmp_path):
        """Ruling C: the compound at the arity written."""
        mod = _load(tmp_path, "third_data", """
            p(X) <- (X is 1)
            p(X, Y) <- (X is Y)
            mk(T) <- (T is p(1, 2, 3))
        """)
        t = Var()
        assert _answers(mod, "mk", t) == [(("p", 1, 2, 3),)]

    def test_a_constants_construction_at_an_undeclared_arity(self):
        from clausal.logic.predicate import (
            begin_loading_declarations, declare_head,
            end_loading_declarations,
        )
        from clausal.logic.constants import constant_functor_term
        ns = {"__name__": "marity_constns", "__d": declare_head}
        begin_loading_declarations(ns)
        try:
            exec("__d('p', ('a',)); __d('p', ('a', 'b', 'c'))", ns)
            assert constant_functor_term("p", (1, 2), {}, ns) == ("p", 1, 2)
            assert constant_functor_term("p", (1,), {}, ns) == ("p", 1)
        finally:
            end_loading_declarations(ns)
