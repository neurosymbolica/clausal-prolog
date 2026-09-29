"""Declared field names are per ARITY (operator ruling 2026-09-29).

``-module(lib, [q(X), q(X, Y)]): allow it.``  The parenthesized export is the
form the documentation teaches and downstream code uses, so a name may be DECLARED with
field names at several arities in one file: each ``(name, arity)`` carries
its own fields.  This lifts Q1/D2 of
``implementation_plans/multi-arity-names-2026-09-29.md`` for declarations
that name every arity; a clause head at an arity the declarations do NOT
name stays the old ``SyntaxError`` (a typo guard), and ``-edcg_pred`` stays
one arity (Q4).

Keyword construction (``f(A=1)``: a seam, a constant, the runtime) follows
Q3: the WRITTEN arity (positional + keyword count) when it is declared,
else the one declared arity the keywords fit, else
``AmbiguousArityConstructionError``.
"""

from __future__ import annotations

import ast
import os
import sys
import textwrap

import pytest

from clausal import Var
from clausal.import_hook import EmbedTransformer, _load_module
from clausal.logic.compiler.terms_to_ast import (
    functor_signature_for, lowering_scope, term_to_ast_expr,
)
from clausal.logic.predicate import AmbiguousArityConstructionError
from clausal.logic.seam import seam_term
from clausal.logic.solve import call
from clausal.logic.variables import deref
from clausal.pythonic_ast.nodes import Keyword
from clausal.terms import Call, LoadName


def _load(tmp_path, name, text, ext=".clausal"):
    path = os.path.join(tmp_path, name + ext)
    with open(path, "w") as fh:
        fh.write(textwrap.dedent(text))
    return _load_module(name, path)


def _answers(mod, name, *args):
    out = []
    for _ in call(name, *args, module=mod):
        out.append(tuple(deref(a) for a in args))
    return out


def _db(mod):
    return mod.__clausal_module__.db


def _kw_call(name, *args, **kwargs):
    return Call(func=LoadName(name=name), args=list(args),
                kwargs=[Keyword(name=k, value=v) for k, v in kwargs.items()])


def _lower(mod, node):
    md = dict(mod.__dict__)
    with lowering_scope(md):
        expr = term_to_ast_expr(node, {})
    tree = ast.fix_missing_locations(ast.Expression(expr))
    return eval(compile(tree, "<t>", "eval"), md)


# ── the operator's repro ───────────────────────────────────────────────────


def test_an_export_list_declaring_two_arities_loads(tmp_path):
    mod = _load(tmp_path, "fpa_lib2", """
        -module(fpa_lib2, [q(X), q(X, Y)])
        q(1),
        q(1, 2),
    """)
    x = Var()
    assert _answers(mod, "q", x) == [(1,)]
    x, y = Var(), Var()
    assert _answers(mod, "q", x, y) == [(1, 2)]
    db = _db(mod)
    assert db.declared_fields("q", 1) == ("X",)
    assert db.declared_fields("q", 2) == ("X", "Y")


def test_each_declared_arity_keeps_its_own_fields(tmp_path):
    mod = _load(tmp_path, "fpa_fields", """
        -module(fpa_fields, [q(X), q(X, Y)])
        q(1),
        q(1, 2),
    """)
    ns = mod.__dict__
    assert functor_signature_for("q", ns, arity=1) == ("X",)
    assert functor_signature_for("q", ns, arity=2) == ("X", "Y")


def test_a_private_list_declaring_two_arities_builds_both(tmp_path):
    mod = _load(tmp_path, "fpa_priv", """
        -private([f(A), f(A, B)])
        mk(T1, T2) <- (T1 is f(1), T2 is f(1, 2))
    """)
    t1, t2 = Var(), Var()
    assert _answers(mod, "mk", t1, t2) == [(("f", 1), ("f", 1, 2))]
    # keyword construction, at the arity written (Q3): seam and compiler
    assert seam_term(_kw_call("f", A=1), mod.__dict__) == ("f", 1)
    assert seam_term(_kw_call("f", A=1, B=2), mod.__dict__) == ("f", 1, 2)
    assert seam_term(_kw_call("f", 1, B=2), mod.__dict__) == ("f", 1, 2)
    assert _lower(mod, _kw_call("f", A=1)) == ("f", 1)
    assert _lower(mod, _kw_call("f", B=2, A=1)) == ("f", 1, 2)


def test_a_keyword_construction_fitting_two_arities_is_ambiguous(tmp_path):
    mod = _load(tmp_path, "fpa_amb", """
        -private([g(A, B), g(A, B, C)])
        mk(T) <- (T is g(1, 2))
    """)
    # g(A=1) is written at arity 1, which is not declared; both g/2 and g/3
    # name A, so the keywords fit either: refused, never a guess.
    with pytest.raises(AmbiguousArityConstructionError, match=r"g/2, g/3"):
        seam_term(_kw_call("g", A=1), mod.__dict__)
    with pytest.raises(AmbiguousArityConstructionError, match=r"g/2, g/3"):
        _lower(mod, _kw_call("g", A=1))
    # a keyword only g/3 has decides it (then the no-padding rule speaks)
    assert seam_term(_kw_call("g", A=1, B=2, C=3), mod.__dict__) == (
        "g", 1, 2, 3)


def test_an_importer_calls_both_arities(tmp_path):
    _load(tmp_path, "fpa_qlib", """
        -module(fpa_qlib, [q(X), q(X, Y), pt(X), pt(X, Y)])
        q(1),
        q(1, 2),
    """)
    sys.path.insert(0, str(tmp_path))
    try:
        mod = _load(tmp_path, "fpa_quser", """
            -import_from(fpa_qlib, [q, pt])
            both(A, B, C) <- (q(A), q(B, C))
            mk(T1, T2) <- (T1 is pt(1), T2 is pt(1, 2))
        """)
    finally:
        sys.path.remove(str(tmp_path))
    a, b, c = Var(), Var(), Var()
    assert _answers(mod, "both", a, b, c) == [(1, 1, 2)]
    t1, t2 = Var(), Var()
    assert _answers(mod, "mk", t1, t2) == [(("pt", 1), ("pt", 1, 2))]
    # the imported registry carries both arities' fields
    assert seam_term(_kw_call("pt", X=1), mod.__dict__) == ("pt", 1)
    assert seam_term(_kw_call("pt", Y=2, X=1), mod.__dict__) == ("pt", 1, 2)


def test_declarations_after_clauses_at_both_arities(tmp_path):
    mod = _load(tmp_path, "fpa_late", """
        f(1),
        f(1, 2),
        -private([f(A), f(A, B)])
    """)
    assert len(_db(mod).clauses_for("f", 1)) == 1
    assert len(_db(mod).clauses_for("f", 2)) == 1


def test_an_indicator_entry_declares_the_other_arity(tmp_path):
    mod = _load(tmp_path, "fpa_mixed", """
        -module(fpa_mixed, [q(X), q/2])
        q(1),
        q(1, 2),
    """)
    assert len(_db(mod).clauses_for("q", 1)) == 1
    assert len(_db(mod).clauses_for("q", 2)) == 1


# ── what stays as it was ───────────────────────────────────────────────────


class TestUndeclaredArityStaysAnError:

    def test_a_clause_at_an_arity_no_entry_names(self, tmp_path):
        with pytest.raises(SyntaxError, match="conflicts with the declaration"):
            _load(tmp_path, "fpa_undecl", """
                -module(fpa_undecl, [q(X), q(X, Y)])
                q(1, 2, 3),
            """)

    def test_a_single_fielded_entry_still_refuses_another_arity(
            self, tmp_path):
        with pytest.raises(SyntaxError) as info:
            _load(tmp_path, "fpa_single", """
                -module(fpa_single, [f(A)])
                f(1, 2),
            """)
        flat = " ".join(str(info.value).split())
        assert "conflicts with the declaration of f/1" in flat
        # the remedy names the per-arity declaration now
        assert ("declare it in the same list, as `f(A, ARG_1)`" in flat
                and "or as `f/2`" in flat)

    def test_a_late_declaration_missing_an_arity_is_refused(self, tmp_path):
        with pytest.raises(SyntaxError, match="does not declare f/2"):
            _load(tmp_path, "fpa_late1", """
                f(1),
                f(1, 2),
                -private([f(A)])
            """)

    def test_edcg_pred_keeps_one_arity(self, tmp_path):
        with pytest.raises(SyntaxError, match="conflicts with the declaration"):
            _load(tmp_path, "fpa_edcg", """
                -edcg_pred(q, 1, [])
                q(1, 2),
            """)


def _rewrite(text):
    src = textwrap.dedent(text)
    tree = ast.parse(src)
    t = EmbedTransformer(source_lines=src.splitlines(keepends=True),
                         filename="x.clausal")
    tree = t.visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def test_a_single_arity_declaration_emits_the_tuple_registry():
    """Single-arity output is unchanged: the registry value stays a tuple."""
    out = _rewrite("""
        -module(m, [q(X)])
        q(1),
    """)
    assert "'q': ('X',)" in out
    assert out.count("$declare_head('q'") == 1


def test_a_two_arity_declaration_emits_both_heads_and_a_per_arity_entry():
    out = _rewrite("""
        -module(m, [q(X), q(X, Y)])
        q(1),
        q(1, 2),
    """)
    assert "$declare_head('q', ('X',))" in out
    assert "$declare_head('q', ('X', 'Y'))" in out
    assert "'q': {1: ('X',), 2: ('X', 'Y')}" in out


def test_single_arity_keyword_construction_is_unchanged(tmp_path):
    mod = _load(tmp_path, "fpa_one", """
        -private([f(A, B)])
        mk(T) <- (T is f(1, 2))
    """)
    assert seam_term(_kw_call("f", A=1, B=2), mod.__dict__) == ("f", 1, 2)
    assert functor_signature_for("f", mod.__dict__) == ("A", "B")
    assert functor_signature_for("f", mod.__dict__, arity=3) == ("A", "B")


def test_a_prolog_data_functor_at_two_arities(tmp_path):
    """The ``.pl`` translator declares a data functor at every arity it is
    used at (it used to leave a two-arity one undeclared)."""
    from clausal.import_hook import _load_prolog_module
    src = ("mk(X, Y) :- X = box(1), Y = box(1, 2).\n")
    path = os.path.join(tmp_path, "fpa_pl.pl")
    with open(path, "w") as fh:
        fh.write(src)
    mod = _load_prolog_module("fpa_pl", path)
    x, y = Var(), Var()
    assert _answers(mod, "mk", x, y) == [(("box", 1), ("box", 1, 2))]


def test_a_keyword_construction_fitting_no_declared_arity(tmp_path):
    """No declared arity has field C: refused naming the arities (it was a
    placement error while a name had one declaration)."""
    mod = _load(tmp_path, "fpa_nofit", """
        -private([f(A), f(A, B)])
        mk(T) <- (T is f(1))
    """)
    with pytest.raises(AmbiguousArityConstructionError,
                       match=r"none of them fits"):
        seam_term(_kw_call("f", C=1), mod.__dict__)


def test_a_dynamic_placeholder_then_a_template_entry_at_another_arity(
        tmp_path):
    """The placeholder is unseated by the first clause; the template entry's
    arity stays declared, with its own fields (``_unseat_directive_minted``
    promotes it)."""
    mod = _load(tmp_path, "fpa_dyntpl", """
        -dynamic(q/1)
        -module(fpa_dyntpl, [q(X, Y)])
        q(1),
        q(1, 2),
    """)
    db = _db(mod)
    assert len(db.clauses_for("q", 1)) == 1
    assert len(db.clauses_for("q", 2)) == 1
    assert db.declared_fields("q", 2) == ("X", "Y")
    with pytest.raises(SyntaxError, match="conflicts with the declaration"):
        _load(tmp_path, "fpa_dyntpl3", """
            -dynamic(q/1)
            -module(fpa_dyntpl3, [q(X, Y)])
            q(1, 2, 3),
        """)


def test_a_prolog_evaluable_beside_data_of_the_same_name(tmp_path):
    """roborev: ``atan2/2`` is an evaluable, ``atan2/3`` data here.  A
    declaration of ``atan2/3`` alone would answer ``atan2(1, 2)`` too, so
    the translator leaves the name undeclared, as before."""
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal(
        "t(X, Y) :- X = atan2(1, 2), Y = atan2(1, 2, 3).\n")
    assert "atan2(_" not in out
