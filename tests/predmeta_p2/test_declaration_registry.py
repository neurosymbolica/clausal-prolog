"""P2 Task 2 (R-P2-1, 2026-09-18): ONE declaration registry on the Database.

A fielded ``-private([point(X, Y)])`` / ``-module(m, [point(X, Y)])`` entry is a
DECLARATION of ``point/2`` with field names ``(x, y)``.  It starts as DATA (a
term constructor with no clauses); it is a PREDICATE once the Database knows a
row for it -- clauses, ``-dynamic``, or a ``-discontiguous``/``-table``/
``-shallow`` directive naming it (the fb0106f3 rule).  ``row()`` answers only
for predicates; ``signature_for``/``declared_fields`` answer for both.

The module-level ``__clausal_functor_signatures__`` map stays as the EXEC-TIME
carrier (generated code binds it before the module body runs; the seam and the
compiler's cell placer read it then); every reader goes through
``functor_signature_for``, which asks the Database first.
"""
from __future__ import annotations

import importlib
import shutil

import pytest


def _load(tmp_path, monkeypatch, name, src):
    (tmp_path / f"{name}.seam").write_text(src, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    m = importlib.import_module(name)
    return m, vars(m)["$module"].db


@pytest.fixture
def data_only(tmp_path, monkeypatch):
    yield _load(tmp_path, monkeypatch, "p2reg_data",
                "-private([point(X, Y)])\n\nq(1),\n")
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def test_a_fielded_declaration_alone_is_a_data_functor(data_only):
    _m, db = data_only
    assert db.declared_fields("point", 2) == ("X", "Y")
    assert db.signature_for("point", 2) == ("X", "Y")
    assert db.declared_kind("point", 2) == "data"
    assert db.row("point", 2) is None, "a data functor has NO predicate row (test_predrow's rule)"
    assert db.declared_kind("point", 3) is None and db.declared_fields("point", 3) is None


def test_an_undeclared_name_is_unknown(data_only):
    _m, db = data_only
    assert db.declared_kind("nosuch", 1) is None
    assert db.signature_for("nosuch", 1) is None


def test_a_directive_naming_the_declared_functor_makes_it_a_predicate(tmp_path, monkeypatch):
    _m, db = _load(tmp_path, monkeypatch, "p2reg_disc",
                   "-private([point(X, Y)])\n-discontiguous(point/2)\n\nq(1),\n")
    assert db.declared_fields("point", 2) == ("X", "Y")
    assert db.declared_kind("point", 2) == "predicate"
    assert db.row("point", 2) is not None
    assert db.is_defined("point", 2) is False, "a row is not a definition"


def test_clauses_make_a_declared_functor_a_predicate(tmp_path, monkeypatch):
    _m, db = _load(tmp_path, monkeypatch, "p2reg_clauses",
                   "-private([point(X, Y)])\n\npoint(1, 2),\n")
    assert db.declared_kind("point", 2) == "predicate"
    assert db.row("point", 2) is not None and db.is_defined("point", 2)


def test_dynamic_is_a_predicate_with_no_declared_fields(tmp_path, monkeypatch):
    _m, db = _load(tmp_path, monkeypatch, "p2reg_dyn", "-dynamic(d/1)\n\nq(1),\n")
    assert db.declared_kind("d", 1) == "predicate"
    assert db.declared_fields("d", 1) is None


def test_a_bare_export_entry_is_a_predicate_with_no_declared_fields(
        tmp_path, monkeypatch):
    """dynfix 2026-09-23 (todo/dynamic-declarations-are-invisible-to-arm-3-
    2026-09-22.md).  Parity with ``test_dynamic_is_a_predicate_with_no_
    declared_fields`` above, for the OTHER spelling the todo names: a bare
    ``name/arity`` entry in a ``-module``/``-private`` export list (R6b) --
    ``gv_free/1`` in ``tests/fixtures/gate_vocab.clausal`` is the
    real-world case.  It synthesizes placeholder field names on its CLASS
    (mirroring ``-dynamic`` exactly -- see
    ``term_rewriting._declare_predicate_export``) but, before this fix,
    registered NOTHING on the Database: ``declared_kind`` answered
    ``None``, indistinguishable from a name nobody ever declared.  Field
    names stay unanswerable here too -- same as ``-dynamic`` -- because
    there genuinely are none anywhere except the class's own synthesized
    guess."""
    _m, db = _load(tmp_path, monkeypatch, "p2reg_export3",
                   "-module(p2reg_export3, [r/2])\n\nq(1),\n")
    assert db.declared_kind("r", 2) == "predicate"
    assert db.declared_fields("r", 2) is None
    assert db.row("r", 2) is None, (
        "deliberately NOT a row -- a row would be LOCKED at load step 7 "
        "(nothing marks it -dynamic), refusing exactly the \"an importer "
        "may legitimately implement it later\" write "
        "test_mutation_gate.py's gv_free/1 pin needs to stay legal"
    )


def test_a_module_export_declares_too(tmp_path, monkeypatch):
    _m, db = _load(tmp_path, monkeypatch, "p2reg_export",
                   "-module(p2reg_export, [seg(A, B), q(N)])\n\nq(1),\n")
    assert db.declared_fields("seg", 2) == ("A", "B") and db.declared_kind("seg", 2) == "data"
    assert db.declared_kind("q", 1) == "predicate"


def test_the_funnel_asks_the_database_first(data_only):
    from clausal.logic.compiler.terms_to_ast import functor_signature_for
    m, db = data_only
    assert functor_signature_for("point", vars(m)) == ("X", "Y")
    # the Database is the source: a declaration made only there is visible
    db.declare_functor("late", ("k",))
    assert functor_signature_for("late", vars(m)) == ("k",)
    assert db.declared_kind("late", 1) == "data"
