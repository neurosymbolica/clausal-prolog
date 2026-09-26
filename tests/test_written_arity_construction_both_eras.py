"""Ruling C (operator, 2026-09-24): a term is built at its WRITTEN arity --
never padded with fresh variables.

``todo/done/too-few-positional-args-pad-with-fresh-vars-QUESTION-2026-09-24.md``.

* a DATA functor's declaration fixes its slots: too FEW positional arguments
  is refused exactly like too many (compile time and the runtime class call);
* a PREDICATE name may be written at several arities (name+arity), so a
  short construction of one is the compound at the arity written --
  ``tok(X)`` naming the nonterminal tok//1 is ``('tok', X)`` -- and
  ``phrase/2,3`` APPENDS S0/S to it (ISO call/N) instead of dropping two
  padded slots.
"""
from __future__ import annotations

import ast

import pytest

from clausal.import_hook import _load_module
from clausal.logic.compiler.terms_to_ast import lowering_scope, term_to_ast_expr
from clausal.logic.predicate import (
    ClausalTermConstructionError, head_cell, mint_predicate_handle,
)
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import Call, LoadName

_SRC = """\
-module({name}, [v(STATUS, CITATION), w(A, B), mk(T), mk_head(T), tok/3, p1(X), p3(X, R)])
-private([ok, cited, solo])
v(ok, cited),
mk(T) <- (T is v(solo))
mk_head(v(solo)),
tok(T) >> ([T])
p1(X) <- phrase(tok(X), ["x"])
p3(X, R) <- phrase(tok(X), ["x", "y"], R)
"""


@pytest.fixture
def mod(tmp_path, request):
    name = "wac_" + "".join(c if c.isalnum() else "_" for c in request.node.name)
    p = tmp_path / f"{name}.clausal"
    p.write_text(_SRC.format(name=name))
    return _load_module(name, str(p))


def _load_src(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return _load_module(name, str(p))


def test_a_short_data_functor_construction_is_refused_at_load(tmp_path):
    with pytest.raises(SyntaxError, match=r"w/2 was constructed with 1"):
        _load_src(tmp_path, "wac_data_short",
                  "-module(wac_data_short, [w(A, B), mk(T)])\n"
                  "-private([solo])\n"
                  "mk(T) <- (T is w(solo))\n")


def test_a_long_data_functor_construction_is_still_refused(tmp_path):
    with pytest.raises(SyntaxError, match=r"w/2 was constructed with 3"):
        _load_src(tmp_path, "wac_data_long",
                  "-module(wac_data_long, [w(A, B), mk(T)])\n"
                  "-private([a, b, c])\n"
                  "mk(T) <- (T is w(a, b, c))\n")


def test_a_short_predicate_name_builds_the_written_arity(mod):
    lm = mod.__dict__["$module"]
    t = Var()
    assert [deref(t) for _ in call("mk", t, module=lm)] == [("v", "solo")]
    t = Var()   # the head-pattern twin (head_match)
    assert [deref(t) for _ in call("mk_head", t, module=lm)] == [("v", "solo")]


def test_the_runtime_handle_construction_refuses_too_few_like_too_many(mod):
    """Handle era: the module-dict binding is the handle, and the runtime
    construction against it is ``head_cell`` (the one the class call and the
    handle share, ``build_term_cell``).  Called from THIS module's frame, so
    no ``$module`` there: every construction error is kept."""
    v = mod.__dict__["v"]
    assert v == mint_predicate_handle(mod.__dict__["$module"].db, "v")
    with pytest.raises(ClausalTermConstructionError, match="1 positional"):
        head_cell(v, "solo")
    with pytest.raises(ClausalTermConstructionError, match="3 positional"):
        head_cell(v, "a", "b", "c")
    assert head_cell(v, "ok", "cited") == ("v", "ok", "cited")


def test_phrase_appends_the_pair_to_the_written_args(mod):
    lm = mod.__dict__["$module"]
    x, r = Var(), Var()
    assert [deref(x) for _ in call("p1", x, module=lm)] == ["x"]
    got = [(deref(x), deref(r)) for _ in call("p3", x, r, module=lm)]
    assert len(got) == 1 and got[0][0] == "x"
    # from Python: the written-arity cell; the old PADDED cell now names
    # tok//3, i.e. tok/5, and gets the other-arity refusal
    x = Var()
    assert [deref(x) for _ in call("phrase", ("tok", x), ["q"], module=lm)] == ["q"]
    from clausal.predicate_diagnostics import PredicateArityMismatchError
    with pytest.raises(PredicateArityMismatchError, match="passes 5"):
        list(call("phrase", ("tok", Var(), Var(), Var()), ["q"], module=lm))


def test_phrase_resolves_the_written_arity_cell_through_the_handle(mod):
    """The cell ``('tok', X)`` names tok by its plain name; the caller's
    binding for it is the handle the load bound (the class arm is gone with
    the class era)."""
    lm = mod.__dict__["$module"]
    assert mod.__dict__["tok"] == mint_predicate_handle(lm.db, "tok")
    x = Var()
    assert [deref(x) for _ in call("phrase", ("tok", x), ["q"], module=lm)] == ["q"]
    x, r = Var(), Var()
    assert [(deref(x), deref(r)) for _ in call(
        "phrase", ("tok", x), ["q", "w"], r, module=lm)] == [("q", ["w"])]


def test_a_short_predicate_construction_lowers_to_the_written_arity(mod):
    """Class era only: a HANDLE-bound name has no construction lowering yet
    (``cell_signature_for_name`` finds no fields on a handle -- pre-existing,
    independent of ruling C)."""
    md = dict(mod.__dict__)
    with lowering_scope(md):
        expr = term_to_ast_expr(Call(func=LoadName(name="tok"), args=["z"], kwargs=[]), {})
    tree = ast.fix_missing_locations(ast.Expression(expr))
    value = eval(compile(tree, "<t>", "eval"), dict(md))
    assert value == ("tok", "z")


def test_a_short_predicate_head_pattern_matches_the_written_arity(mod):
    """``head_match``'s twin of the construction rule: a nested predicate
    name in a head pattern is matched at the arity WRITTEN."""
    from clausal.logic.compiler.head_match import head_to_match_pattern

    term = Call(func=LoadName(name="v"), args=[Var()], kwargs=[])
    pat = head_to_match_pattern(term, {}, [], [], None,
                                globals_=dict(mod.__dict__))
    src = ast.unparse(ast.match_case(pattern=pat, body=[ast.Pass()]))
    assert src.startswith("case ['v', ") and src.count(",") == 1, src
