"""The generic-compound note still fires for a DECLARED, clause-less
predicate (roborev L4, 2026-09-17).

``testing._note_generic_compound_confusion`` is the failure diagnostic that
says out loud "that binding is a generic ``Compound``, not the declared term
of the same name/arity — they render identically and never unify".  P1 routed
its declaredness test to ``db.row(functor, arity)``, which is exactly the
question the measured equivalence LIMIT does not answer: a name declared with
fields and given no clauses is a ``PredicateMeta`` in the module dict with no
row at all (``test_membership_equivalence`` pins that shape).  For such a
predicate the note went silent and the confusion it exists for came back.

So the class leg stays as a FALLBACK, arity-checked, ahead of the atom branch.
"""
from __future__ import annotations

import importlib
import shutil
import types

import pytest

from clausal.terms import Compound
from clausal.testing import _note_generic_compound_confusion


@pytest.fixture
def declared_only(tmp_path, monkeypatch):
    """A module with ``p/1`` DECLARED and clause-less, plus a clausal control."""
    (tmp_path / "gcnote.seam").write_text(
        "-private([p(X)])\n-discontiguous(p/1)\n\nq(1),\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    m = importlib.import_module("gcnote")
    yield m
    for d in tmp_path.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def _notes_for(module, functor, args):
    diag = types.SimpleNamespace(notes=[])
    _note_generic_compound_confusion(
        diag, vars(module), [("T", Compound(functor, tuple(args)))])
    return diag.notes


def test_the_note_fires_for_a_predicate_with_clauses(declared_only):
    """Positive control: the row leg, unchanged."""
    notes = _notes_for(declared_only, "q", [1])
    assert notes and "GENERIC compound q/1" in notes[0]


def test_the_note_fires_for_a_declared_clause_less_predicate(declared_only):
    from clausal.logic.predicate import PredicateMeta
    declared = vars(declared_only)["p"]
    db = vars(declared_only)["$module"].db
    # the shape this test is about, pinned so it cannot go vacuous
    assert isinstance(declared, PredicateMeta) and len(declared._fields) == 1
    assert db.row("p", 1) is None
    notes = _notes_for(declared_only, "p", [1])
    assert notes and "GENERIC compound p/1" in notes[0]


def test_the_class_leg_is_arity_checked(declared_only):
    """``p`` is declared at arity 1 only; a generic ``p/2`` is not shadowing
    anything this module declares."""
    assert _notes_for(declared_only, "p", [1, 2]) == []


def test_an_undeclared_functor_still_gets_no_note(declared_only):
    assert _notes_for(declared_only, "nosuch", [1]) == []
