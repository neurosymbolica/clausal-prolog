"""``through=`` made era-agnostic, per
``implementation_plans/w4b2-open-questions-2026-09-23.md`` and
``.superpowers/sdd/through-report.md``.

``Database._write_rows`` computes the blast radius of a mutation-gate write:
the row named by ``(functor, arity)`` plus, optionally, a SECOND row named by
``through=`` -- the channel that catches the aliased-import clobber, because
an ``-import_from`` can share a class whose OWN row lives in a different
Database than the one the write's ``(functor, arity)`` key names in *this*
database.

Today ``through=`` is always a ``PredicateMeta`` class.  Post-flip it can
instead be a mangled atom (``"module\\x1fname"``).  The OLD resolution --
``getattr(through, "_row", None)`` -- answers ``None`` for a mangled atom
exactly as it does for "this class has no row yet", so a flipped call site
would silently stop adding the second row to the blast radius: the gate
would go on policing only the target row, on precisely the write ``through=``
exists to widen.  These tests pin the fix: the resolver discriminates on
``through=``'s SHAPE, not on whether the shape happens to yield a row, and
an unrecognised shape raises instead of resolving to ``None``.
"""
from __future__ import annotations

import dataclasses
import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.database import (
    Clause, Database, PredRow, WRITE_LOAD_CLAUSES,
)
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import resolve_predicate_row


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str, as_name: str | None = None):
    return _load_module(as_name or f"tests.fixtures.{stem}", _fixture_path(stem))


def _db_of(module):
    return module.__dict__["$module"].db


def _clause(functor, *args):
    return Clause(head=(functor, *args) if args else functor, body=[])


def _row_ids(rows):
    """Identity set of *rows* -- ``PredRow`` is a plain (unfrozen)
    dataclass, so two distinct, still-empty rows for different keys compare
    ``==`` (``_key`` is a ``compare=False`` field) and are unhashable; every
    comparison in this file is about OBJECT IDENTITY -- "is the row I
    expect actually IN the blast radius" -- never value equality."""
    return {id(r) for r in rows}


def _is_exactly(rows, *expected) -> bool:
    """True iff *rows* holds exactly the given row objects, by identity --
    same reasoning as ``_row_ids``, but also pins the COUNT (a list
    equality check like ``rows == [target]`` would pass even if
    ``_write_rows`` returned some OTHER value-equal empty row instead of
    ``target`` itself)."""
    return len(rows) == len(expected) and _row_ids(rows) == {id(r) for r in expected}


# ── Positive control: the aliased-import fixture pair really diverges ──────
#
# ``gate_dyn_owner``/``gate_dyn_user`` (tests/fixtures/…) are the exact
# fixtures ``test_mutation_gate.py`` already uses to pin the aliased-import
# clobber fix.  The user module declares its OWN ``-dynamic(gd_p/1)`` BEFORE
# ``-import_from``-ing the owner's ``gd_p`` -- so ``adopt_row`` (which never
# displaces an existing entry) leaves the user's database holding a private,
# empty row under the SAME key the owner's row uses, while the shared class
# stays bound to the OWNER's row.  Without this divergence, every test below
# would only prove a same-db write works, which is not what ``through=``
# exists for.

def test_positive_control_the_fixture_pair_diverges():
    """If this fails, no test below is exercising the aliased-import shape
    ``through=`` was built for -- see the module docstring's warning against
    a weaker substitute."""
    owner = _load_fixture("gate_dyn_owner")
    user = _load_fixture("gate_dyn_user")
    owner_db = _db_of(owner)
    user_db = _db_of(user)
    cls = owner.gd_p

    owner_row = owner_db.row("gd_p", 1)
    user_row = user_db.row("gd_p", 1)
    assert owner_row is not None and user_row is not None
    # Post-flip the shared binding is a handle; the row it reads is the db's
    # answer -- from the owner and from the importer alike.
    assert resolve_predicate_row(cls, arity=1, db=owner_db) is owner_row, (
        "the shared binding reads the OWNER's row")
    assert resolve_predicate_row(user.gd_p, arity=1, db=user_db) is owner_row, (
        "and so does the importer's binding")
    assert user_row is not owner_row, (
        "the fixture pair no longer diverges -- construct a different "
        "aliased-import scenario before trusting the tests below"
    )


def test_aliased_import_blast_radius_contains_both_rows_for_mutate():
    """``mutate``'s write-time blast radius (``create=True``) must contain
    BOTH the user db's own row at the key and the owner's row the shared
    class actually reads -- the second row a same-db write could never
    prove."""
    owner = _load_fixture("gate_dyn_owner")
    user = _load_fixture("gate_dyn_user")
    owner_row = _db_of(owner).row("gd_p", 1)
    user_db = _db_of(user)
    user_row = user_db.row("gd_p", 1)
    cls = owner.gd_p

    rows = user_db._write_rows("gd_p", 1, through=cls)
    assert _row_ids(rows) == {id(user_row), id(owner_row)}


def test_aliased_import_blast_radius_contains_both_rows_for_refusal_for():
    """Same blast radius, computed the ``refusal_for`` (``create=False``)
    way -- a dry run must not ask about a different set of rows than the
    write it is standing in for would touch."""
    owner = _load_fixture("gate_dyn_owner")
    user = _load_fixture("gate_dyn_user")
    owner_row = _db_of(owner).row("gd_p", 1)
    user_db = _db_of(user)
    user_row = user_db.row("gd_p", 1)
    cls = owner.gd_p

    rows = user_db._write_rows("gd_p", 1, through=cls, create=False)
    assert _row_ids(rows) == {id(user_row), id(owner_row)}


# ── The class arm, today's era ───────────────────────────────────────────────



def test_none_through_yields_just_the_target():
    db = Database()
    target = db.row("solo2", 1, create=True)
    assert _is_exactly(db._write_rows("solo2", 1, through=None), target)


# ── The mangled-atom arm, post-flip ──────────────────────────────────────────

def _load_hide_owner():
    return _load_module("through_era_hide_owner", _fixture_path("hide_owner"))


def test_mangled_atom_through_resolves_the_owning_module_s_row():
    _load_hide_owner()
    handle = mangle("through_era_hide_owner", "holds")

    local_db = Database()
    local_row = local_db.row("holds", 1, create=True)

    rows = local_db._write_rows("holds", 1, through=handle)
    assert local_row in rows
    assert len(rows) == 2, (
        "the mangled atom must add the OWNING module's row, distinct from "
        "this database's own row at the same key"
    )
    other = [r for r in rows if r is not local_row][0]
    assert other.clauses, "the resolved row is the owner's, which has clauses"


def test_mangled_atom_naming_an_unloaded_module_yields_just_the_target():
    """A recognised shape (a mangled atom) that happens to resolve to no row
    -- the module is not loaded -- is a legitimate, silent no-op, exactly
    like an unbound class."""
    db = Database()
    target = db.row("ghostly", 1, create=True)
    ghost = mangle("through_era_no_such_module_ever_loaded", "ghostly")

    assert _is_exactly(db._write_rows("ghostly", 1, through=ghost), target)


# ── Unrecognised shapes: loud, not silent ────────────────────────────────────


@dataclasses.dataclass
class _NotAPredicate:
    x: int


def _unrecognised_values():
    db = Database()
    a_row = db.row("bystander", 1, create=True)
    return [
        "not_mangled_at_all",
        a_row,                 # a bare PredRow -- NOT an accepted shape
        object(),
        42,
        _NotAPredicate(1),
        ("tuple", "of", "stuff"),
    ]


@pytest.mark.parametrize("bad", _unrecognised_values())
def test_unrecognised_through_shape_raises_from_write_rows(bad):
    db = Database()
    db.row("f", 1, create=True)
    with pytest.raises(TypeError) as excinfo:
        db._write_rows("f", 1, through=bad)
    assert repr(bad) in str(excinfo.value)


@pytest.mark.parametrize("bad", _unrecognised_values())
def test_unrecognised_through_shape_raises_from_mutate(bad):
    db = Database()
    db.row("f", 1, create=True)
    with pytest.raises(TypeError):
        with db.mutate("f", 1, author="me", kind=WRITE_LOAD_CLAUSES,
                       through=bad):
            pass  # pragma: no cover -- must not be reached


@pytest.mark.parametrize("bad", _unrecognised_values())
def test_unrecognised_through_shape_raises_from_refusal_for(bad):
    db = Database()
    db.row("f", 1, create=True)
    with pytest.raises(TypeError):
        db.refusal_for("f", 1, author="me", kind=WRITE_LOAD_CLAUSES,
                       through=bad)


# ── mutate and refusal_for must agree ────────────────────────────────────────

