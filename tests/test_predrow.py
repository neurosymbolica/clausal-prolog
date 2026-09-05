"""Tests for PredRow + Database.row() — the P3-3 Task 1 authoritative store.

Strictly additive: PredRow is a new per-(functor, arity) facade backed by the
Database's EXISTING dicts (``_clauses``, ``_dispatch``, ``_lazy_recompile``,
``_signatures``, ``_dynamic``) — not a second parallel store. The legacy
public methods (``assertz``, ``asserta``, ``retract``, ``set_dispatch``,
``get_dispatch``, ``register_signature``, ``mark_dynamic``) are untouched by
this task and must keep behaving byte-identically; these tests pin the VIEW
COHERENCE between the row facade and that legacy state, in both directions.
"""

import pytest

from clausal.logic.database import Clause, Database, PredRow, WriteStamp
from clausal.terms import Compound


def _clause(functor, *args):
    return Clause(head=Compound(functor, tuple(args)), body=[])


# ── row() identity + create semantics ───────────────────────────────────────


def test_row_create_false_returns_none_for_unknown():
    db = Database()
    assert db.row("nope", 2) is None
    assert db.row("nope", 2, create=False) is None


def test_row_create_true_mints_a_row():
    db = Database()
    row = db.row("f", 2, create=True)
    assert row is not None
    assert isinstance(row, PredRow)
    assert row.clauses == []


def test_row_identity_is_cached():
    db = Database()
    row1 = db.row("f", 2, create=True)
    row2 = db.row("f", 2)
    assert row1 is row2
    # And a fresh create=True call for the same key returns the same object.
    row3 = db.row("f", 2, create=True)
    assert row1 is row3


def test_row_distinguishes_arity():
    db = Database()
    row2 = db.row("f", 2, create=True)
    row3 = db.row("f", 3, create=True)
    assert row2 is not row3


def test_row_create_false_finds_a_predicate_known_only_via_legacy_assertz():
    """A predicate that only ever went through the legacy db.assertz path
    (never touched db.row) must still be discoverable via row(create=False) —
    the Database is the authoritative store regardless of entry path."""
    db = Database()
    db.assertz(_clause("g", 1, 2))
    row = db.row("g", 2, create=False)
    assert row is not None
    assert len(row.clauses) == 1


# ── view coherence: clauses ──────────────────────────────────────────────────


def test_legacy_assertz_visible_in_row_clauses():
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    db.assertz(c)
    assert row.clauses == [c]


def test_row_clauses_append_visible_via_clauses_for():
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    row.clauses.append(c)
    assert db.clauses_for("f", 2) == [c]


def test_row_clauses_is_the_same_list_object_assertz_mutates():
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    db.assertz(c)
    # Not just equal — the identical list object (view coherence, not a copy).
    assert db._clauses[("f", 2)] is row.clauses


def test_row_clauses_preexisting_via_asserta_then_row():
    db = Database()
    c1 = _clause("h", 1)
    c2 = _clause("h", 2)
    db.assertz(c1)
    db.asserta(c2)
    row = db.row("h", 1)
    assert row is not None
    assert row.clauses == [c2, c1]


def test_row_clauses_retract_visible_through_row():
    db = Database()
    c1 = _clause("k", 1)
    db.assertz(c1)
    row = db.row("k", 1)
    assert row.clauses == [c1]
    assert db.retract(Compound("k", (1,))) is True
    assert row.clauses == []


# ── view coherence: dispatch_fn / lazy_recompile / signature / dynamic ──────


def test_row_dispatch_fn_reads_through_set_dispatch():
    db = Database()
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    row = db.row("f", 2)
    assert row.dispatch_fn is fn


def test_row_dispatch_fn_setter_visible_via_get_dispatch():
    db = Database()
    row = db.row("f", 2, create=True)
    fn = lambda: None  # noqa: E731
    row.dispatch_fn = fn
    assert db.get_dispatch("f", 2) is fn


def test_row_lazy_recompile_reads_through_set_dispatch():
    db = Database()
    fn = lambda: "fn"  # noqa: E731
    lazy = lambda: "recompiled"  # noqa: E731
    db.set_dispatch("f", 2, fn, lazy_recompile=lazy)
    row = db.row("f", 2)
    assert row.lazy_recompile is lazy


def test_row_signature_reads_through_register_signature():
    db = Database()
    db.register_signature("f", 2, ("a", "b"))
    row = db.row("f", 2)
    assert row.signature == ("a", "b")


def test_row_signature_setter_visible_via_signature_for():
    db = Database()
    row = db.row("f", 2, create=True)
    row.signature = ("x", "y")
    assert db.signature_for("f", 2) == ("x", "y")


def test_row_dynamic_reads_through_mark_dynamic():
    db = Database()
    db.mark_dynamic("f", 2)
    row = db.row("f", 2)
    assert row.dynamic is True


def test_row_not_dynamic_by_default():
    db = Database()
    row = db.row("f", 2, create=True)
    assert row.dynamic is False


# ── invalidate() ─────────────────────────────────────────────────────────────


def test_invalidate_clears_dispatch_fn_only():
    db = Database()
    row = db.row("f", 2, create=True)
    fn = lambda: None  # noqa: E731
    lazy = lambda: "recompiled"  # noqa: E731
    row.dispatch_fn = fn
    row.lazy_recompile = lazy
    row.invalidate()
    assert row.dispatch_fn is None
    assert row.lazy_recompile is lazy


def test_invalidate_visible_through_legacy_get_dispatch_dict():
    db = Database()
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    row = db.row("f", 2)
    row.invalidate()
    assert db._dispatch[("f", 2)] is None


# ── Finding 1 (fix round 1): self-healing across a wholesale dict wipe ─────


def test_row_self_heals_across_wholesale_backing_dict_wipe():
    """``clauses`` is a live property, not a captured reference, so a
    wholesale wipe of the backing dicts (an existing pattern in this
    codebase: tests/test_search.py:472-474 does
    ``db._clauses.clear(); db._dispatch.clear(); db._lazy_recompile.clear()``)
    does not leave a cached PredRow pointing at an orphaned list or a stale
    dispatch value — the next access re-aliases whatever the dict holds."""
    db = Database()
    row = db.row("f", 2, create=True)
    c1 = _clause("f", 1, 2)
    db.assertz(c1)
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    assert row.clauses == [c1]
    assert row.dispatch_fn is fn

    # The exact wholesale-wipe pattern already used elsewhere in the suite.
    db._clauses.clear()
    db._dispatch.clear()
    db._lazy_recompile.clear()

    # The cached PredRow object persists (Database._rows is never
    # invalidated) but every field is a live read-through, so it re-aliases
    # the fresh (now-empty) entries rather than holding a stale copy.
    assert row.clauses is db._clauses[("f", 2)]
    assert row.clauses == []
    assert row.dispatch_fn is None

    # And a subsequent legacy assertz is visible through the row again.
    c2 = _clause("f", 3, 4)
    db.assertz(c2)
    assert row.clauses == [c2]


# ── PredRow defaults for new (not-yet-wired) fields ─────────────────────────


def test_predrow_defaults():
    db = Database()
    row = db.row("f", 2, create=True)
    assert row.backend == "python"
    assert row.locked is False
    assert row.source is None
    assert row.writes == []


# ── WriteStamp + writes cap ──────────────────────────────────────────────────


def test_writestamp_is_a_namedtuple_with_expected_fields():
    ws = WriteStamp(author="mod:foo", kind="assertz", detail="f/2")
    assert ws.author == "mod:foo"
    assert ws.kind == "assertz"
    assert ws.detail == "f/2"


def test_row_record_write_appends():
    db = Database()
    row = db.row("f", 2, create=True)
    row.record_write("mod:foo", "assertz", "f/2")
    assert row.writes == [WriteStamp("mod:foo", "assertz", "f/2")]


def test_row_writes_capped_at_32():
    db = Database()
    row = db.row("f", 2, create=True)
    for i in range(40):
        row.record_write("mod:foo", "assertz", i)
    assert len(row.writes) == 32
    # Oldest entries dropped; last 32 (details 8..39) survive in order.
    assert [w.detail for w in row.writes] == list(range(8, 40))


# ── Finding 2 (fix round 1): row() minting must not flip is_defined() ──────


def test_row_create_false_on_dispatch_only_predicate_does_not_flip_is_defined():
    """Minting a row (even via the auto-vivify create=False path) from a
    predicate that only ever had dispatch/signature/dynamic state must NOT
    eagerly create a ``_clauses`` entry — that would silently flip
    ``Database.is_defined()`` False->True as a side effect of merely calling
    ``db.row()``."""
    db = Database()
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    assert db.is_defined("f", 2) is False
    row = db.row("f", 2, create=False)
    assert row is not None
    assert db.is_defined("f", 2) is False


def test_row_clauses_first_read_lazily_vivifies_is_defined():
    """Reading ``row.clauses`` is the (intentional, narrow, documented) point
    where the empty ``_clauses`` entry is created — pinned here as expected
    behavior, not a regression. Task 2's compile-install path is the real,
    deliberate minting site for clause lists going forward; this is just the
    mechanical consequence of ``clauses`` being a live setdefault-backed
    property (see PredRow.clauses's docstring and task-1-report.md)."""
    db = Database()
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    row = db.row("f", 2, create=False)
    assert db.is_defined("f", 2) is False
    _ = row.clauses  # first read of the property
    assert db.is_defined("f", 2) is True
