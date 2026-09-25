"""Operator rulings 2026-09-25 ("let's not auto-correct arity"):

1. keyword-only PARTIAL construction is refused, never padded -- in the
   runtime placer (``build_term_cell``: a handle's head, a class call) AND
   its compile-time twin (``_place_signature_slots``).  A construction with
   no arguments at all against a fielded signature is the same refusal.
3. a predicate NAME written in the seam's term position at ANOTHER arity is
   the compound at the WRITTEN arity -- longer (``--pq(1, 2, 3)`` for a
   ``pq/2``) as well as shorter -- never refused or corrected.  A DATA
   functor's declaration still fixes its slots.

Also pinned: an ``-edcg_pred`` plain clause at its visible arity keeps
loading -- the rewriter now SPELLS its hidden accumulator slots instead of
relying on the retired padding.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.predicate import (
    ClausalTermConstructionError, build_term_cell, head_cell, make_predicate,
)
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk


def _load(tmp_path, name, src):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(src).lstrip())
    sys.modules.pop(name, None)
    try:
        return _load_module(name, str(path))
    finally:
        sys.modules.pop(name, None)


# ── 1. no keyword-only partial construction ──────────────────────────────────


def test_build_term_cell_refuses_a_keyword_only_partial():
    with pytest.raises(ClausalTermConstructionError,
                       match=r"0 positional argument\(s\) and field names \(a\)"):
        build_term_cell("q", ("a", "b"), (), {"a": 1})
    assert build_term_cell("q", ("a", "b"), (), {"b": 2, "a": 1}) == ("q", 1, 2)


def test_build_term_cell_refuses_no_arguments_against_fields():
    with pytest.raises(ClausalTermConstructionError, match=r"q/2"):
        build_term_cell("q", ("a", "b"), (), {})
    assert build_term_cell("z", (), (), {}) == ("z",)


def test_a_stray_keyword_still_gets_its_own_message():
    with pytest.raises(ClausalTermConstructionError,
                       match=r"constructed with field names \(c\)"):
        build_term_cell("q", ("a", "b"), (), {"c": 1})


def test_a_class_call_and_a_handle_head_refuse_it_alike(tmp_path):
    Pt = make_predicate("np_pt", ["x", "y"])
    with pytest.raises(ClausalTermConstructionError):
        Pt(x=1)
    with pytest.raises(ClausalTermConstructionError):
        Pt()
    mod = _load(tmp_path, "_np_owner", """
        -module(_np_owner, [np_q(a, b)])
        np_q(1, 2),
    """)
    with pytest.raises(ClausalTermConstructionError):
        head_cell(mod.np_q, a=1)
    assert head_cell(mod.np_q, b=2, a=1) == ("np_q", 1, 2)


def test_the_compile_time_placer_refuses_it():
    from clausal.logic.compiler.terms_to_ast import _place_signature_slots
    with pytest.raises(SyntaxError, match=r"point/2"):
        _place_signature_slots(("x", "y"), [], [("x", 1)],
                               functor="point", missing=Var)
    with pytest.raises(SyntaxError, match=r"point/2"):
        _place_signature_slots(("x", "y"), [], [], functor="point",
                               missing=Var)
    assert _place_signature_slots(("x", "y"), [], [("y", 2), ("x", 1)],
                                  functor="point", missing=Var) == [1, 2]


# ── 3. the seam's term position: a predicate name at the WRITTEN arity ──────


def test_a_predicate_name_is_built_at_the_written_arity_in_the_seam(tmp_path):
    mod = _load(tmp_path, "_np_seam", """
        -module(_np_seam, [np_pq(a, b), np_point(x, y)])
        np_pq(1, 2),
        def longer():
            return --np_pq(1, 2, 3)
        def shorter():
            return --np_pq(1)
        def exact():
            return --np_pq(1, 2)
        def data_longer():
            return --np_point(1, 2, 3)
    """)
    assert mod.longer() == ("np_pq", 1, 2, 3)
    assert mod.shorter() == ("np_pq", 1)
    assert mod.exact() == ("np_pq", 1, 2)
    # a DATA functor's declaration still fixes its slots
    with pytest.raises(SyntaxError, match=r"np_point/2"):
        mod.data_longer()


# ── the EDCG visible-arity clause: hidden slots SPELLED, not padded ─────────


def test_an_edcg_visible_arity_fact_spells_its_hidden_slots(tmp_path):
    mod = _load(tmp_path, "_np_edcg", """
        -edcg_acc(cnt, V_, in_, out_, {out_ is in_ + V_})
        -edcg_pred(np_r, 1, [cnt])

        np_r(1),
    """)
    lm = mod.__dict__["$module"]
    # the clause is np_r/3 -- visible argument plus the two accumulator
    # slots -- and nothing at the written arity 1
    assert len(lm.db.clauses_for("np_r", 3)) == 1
    assert not lm.db.clauses_for("np_r", 1)
    X, A, B = Var(), Var(), Var()
    assert [walk(deref(X)) for _ in call("np_r", X, A, B, module=lm)] == [1]
