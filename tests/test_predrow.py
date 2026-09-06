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

from clausal.logic.atoms import char_atom, mint
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
    """ADAPTED, P3-3 Task 2 fix round 1: appending goes through
    ``ensure_clauses()``, the sanctioned mint. A plain ``clauses`` read no
    longer creates the Database entry (see the two tests below), so the
    original spelling — ``row.clauses.append(c)`` — would have appended to an
    unminted per-row list that ``clauses_for`` cannot see."""
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    row.ensure_clauses().append(c)
    assert db.clauses_for("f", 2) == [c]


def test_appending_to_an_unminted_read_is_invisible_until_promotion():
    """The read/mint split, both halves. An append onto the list a plain read
    hands back stays out of the Database until something mints — and the mint
    is IDENTITY-PRESERVING, so the append is not lost when it happens."""
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    unminted = row.clauses
    unminted.append(c)
    assert db.clauses_for("f", 2) == []
    assert db.is_defined("f", 2) is False

    promoted = row.ensure_clauses()
    assert promoted is unminted, "the mint must promote the SAME list object"
    assert db._clauses[("f", 2)] is unminted
    assert db.clauses_for("f", 2) == [c]


def test_ensure_clauses_is_idempotent_and_keeps_the_existing_entry():
    db = Database()
    row = db.row("f", 2, create=True)
    c = _clause("f", 1, 2)
    db.assertz(c)
    live = db._clauses[("f", 2)]
    assert row.ensure_clauses() is live
    assert row.ensure_clauses() is live
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
    """ADAPTED (P3-3 Task 3): installing a dispatch now requires an open
    ``Database.mutate`` transaction — the door the aliased-import clobber
    came through.  The view-coherence claim under test is unchanged."""
    db = Database()
    row = db.row("f", 2, create=True)
    fn = lambda: None  # noqa: E731
    with db.mutate("f", 2, author="test", kind="recompile"):
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
    with db.mutate("f", 2, author="test", kind="recompile"):
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
    # invalidated) but every field is a live read-through, so it reports the
    # wipe rather than holding a stale copy of what was there before.
    #
    # ADAPTED, P3-3 Task 2 fix round 1: the original assertion here was
    # ``row.clauses is db._clauses[("f", 2)]`` — which only held because the
    # read itself re-created the entry. A read mints nothing now, so after a
    # wipe the key is simply GONE and the read hands back a fresh empty list.
    # Self-healing is unchanged in the way that matters: no stale clause
    # survives the wipe, and the next MUTATION re-aliases.
    assert ("f", 2) not in db._clauses
    assert row.clauses == []
    assert row.dispatch_fn is None

    # And a subsequent legacy assertz is visible through the row again, with
    # the aliasing restored.
    c2 = _clause("f", 3, 4)
    db.assertz(c2)
    assert row.clauses == [c2]
    assert row.clauses is db._clauses[("f", 2)]


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


def test_row_clauses_read_does_not_vivify_is_defined():
    """INVERTED, P3-3 Task 2 fix round 1. Task 1 pinned the opposite: reading
    ``row.clauses`` used to ``setdefault`` the entry into existence, flipping
    ``is_defined`` False -> True, and that was documented as an accepted
    narrow side effect because only ``PredRow`` read the property.

    Task 2 routed every ``PredicateMeta._clauses`` read through it, which
    turned ``__repr__``, ``_clause_arity``, ``_declared_arity`` and the
    compiler's own inspections into minting sites — a clause-less
    ``-dynamic`` predicate reported itself defined merely for having been
    looked at. Reads mint nothing now; ``ensure_clauses()`` is the one
    promotion point, and Task 1's "compile-install is the deliberate minting
    site" contract holds again."""
    db = Database()
    fn = lambda: None  # noqa: E731
    db.set_dispatch("f", 2, fn)
    row = db.row("f", 2, create=False)
    assert db.is_defined("f", 2) is False
    for _ in range(3):
        assert row.clauses == []          # repeated plain reads
    assert db.is_defined("f", 2) is False
    assert ("f", 2) not in db._clauses
    # ... and the SAME list comes back each time, so an append is not lost
    # between reads (it just is not visible to the Database until a mint).
    assert row.clauses is row.clauses


# ══════════════════════════════════════════════════════════════════════════════
# P3-3 Task 2 — THE INVERSION: PredicateMeta state is a read-through onto the
# row; the Database's class-mirror blocks and arity-blind `_pred_cls_for` die.
# ══════════════════════════════════════════════════════════════════════════════

from clausal.logic.predicate import PredicateMeta, make_predicate  # noqa: E402


# ── the class reads THROUGH the row ─────────────────────────────────────────


def test_bound_class_clauses_is_the_database_row_list_itself():
    """The whole point of the inversion: one list, not two that must be kept
    in step. Before Task 2 ``cls._clauses`` was a private per-class list and
    ``Database.assertz`` had to mirror every append onto it."""
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    # ADAPTED, P3-3 Task 2 fix round 1: binding alone mints nothing, so the
    # identity is asserted once the predicate actually HAS a clause list —
    # which is the only state in which "one list, not two" is a claim about
    # anything. Before the mint, the class and the row still agree: they hand
    # back the same unminted list object.
    assert p._clauses is db.row("p", 1).clauses
    assert ("p", 1) not in db._clauses
    db.assertz(_clause("p", 1))
    assert p._clauses is db._clauses[("p", 1)]
    assert p._clauses is db.row("p", 1).clauses


def test_db_assertz_is_visible_through_the_bound_class_without_a_mirror():
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    c = _clause("p", 1)
    db.assertz(c)
    assert p._clauses == [c]
    assert p._clauses is db._clauses[("p", 1)]


def test_db_asserta_and_retract_are_visible_through_the_bound_class():
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    first, second = _clause("p", 1), _clause("p", 2)
    db.assertz(first)
    db.asserta(second)
    assert p._clauses == [second, first]
    assert db.retract(second.head) is True
    assert p._clauses == [first]


def test_db_mutation_invalidates_the_dispatch_the_class_reads():
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    db.set_dispatch("p", 1, lambda *a: iter([]))
    assert p._dispatch_fn is not None
    db.assertz(_clause("p", 1))
    assert p._dispatch_fn is None
    assert db._dispatch[("p", 1)] is None


def test_class_writes_land_in_the_database():
    """Every relocated attribute, in the write direction."""
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    fn = lambda *a: iter([])  # noqa: E731
    lazy = lambda: fn  # noqa: E731
    with p._mutate("test", "recompile"):        # the gate, P3-3 Task 3
        p._dispatch_fn = fn
    p._lazy_recompile = lazy
    p._signature = ("a",)
    p._locked = True
    p._clauses_source = ("m", "/tmp/m.clausal")
    p._dynamic_arities = {1}
    row = db.row("p", 1)
    assert db._dispatch[("p", 1)] is fn
    assert db._lazy_recompile[("p", 1)] is lazy
    assert db.signature_for("p", 1) == ("a",)
    assert row.locked is True
    assert row.source == ("m", "/tmp/m.clausal")
    assert row.dynamic_arities == {1}


def test_clauses_wholesale_rebind_goes_through_the_row():
    """``cls._clauses = []`` (the reset spelling several tests use) replaces the
    Database's entry rather than orphaning the class onto a private list."""
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    db.assertz(_clause("p", 1))
    fresh = []
    p._clauses = fresh
    assert db._clauses[("p", 1)] is fresh
    assert p._clauses is fresh
    assert db.clauses_for("p", 1) == []


def test_get_dispatch_recompiles_through_the_rows_lazy_callback():
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    fn = lambda *a: iter([])  # noqa: E731
    calls = []

    def lazy():
        calls.append(1)
        db._dispatch[("p", 1)] = fn
        return fn

    db.set_dispatch("p", 1, fn, lazy_recompile=lazy)
    db.assertz(_clause("p", 1))          # clears dispatch, keeps lazy
    assert db._dispatch[("p", 1)] is None
    assert p._get_dispatch() is fn
    assert calls == [1]


def test_get_dispatch_prefers_what_install_stored_over_the_callbacks_return():
    """The tabled-wrapper invariant: ``_install`` puts the SLG wrapper on the
    row, so whatever the recompile callback happens to return loses."""
    db = Database()
    p = make_predicate("p", ["a"])
    p._bind_row(db, "p", 1)
    raw = lambda *a: iter([])      # noqa: E731
    wrapped = lambda *a: iter([])  # noqa: E731

    def lazy():
        db._dispatch[("p", 1)] = wrapped   # what _install stores
        return raw                          # what the compile returned

    db.set_dispatch("p", 1, None, lazy_recompile=lazy)
    assert p._get_dispatch() is wrapped


def test_get_dispatch_without_clauses_or_lazy_still_raises():
    p = make_predicate("lonely", ["a"])
    with pytest.raises(NotImplementedError):
        p._get_dispatch()


# ── the arity-blind mirror is gone (identity todo instance 3) ───────────────


def test_assertz_no_longer_appends_onto_an_arity_mismatched_class():
    """``_pred_cls_for`` looked the functor up in ``module_dict`` and ignored
    arity entirely, so a ``p/1`` assertz appended its clause onto a class that
    was ``p/3``. There is no second store to miss now: the row for ``p/1`` is
    the only place the clause goes, and the ``p/3`` class reads ``p/3``'s row."""
    p3 = make_predicate("p", ["a", "b", "c"])
    db = Database(module_dict={"p": p3})
    p3._bind_row(db, "p", 3)
    db.assertz(_clause("p", 1))
    assert p3._clauses == []
    assert db.clauses_for("p", 1) == [_clause("p", 1)]


def test_retract_no_longer_reaches_into_an_arity_mismatched_class():
    p3 = make_predicate("p", ["a", "b", "c"])
    db = Database(module_dict={"p": p3})
    p3._bind_row(db, "p", 3)
    keep = _clause("p", 9, 9, 9)
    db.assertz(keep)
    db.assertz(_clause("p", 1))
    assert db.retract(_clause("p", 1).head) is True
    assert p3._clauses == [keep]


def test_database_no_longer_has_pred_cls_for():
    assert not hasattr(Database, "_pred_cls_for")


# ── detached compatibility mode: no Database anywhere ───────────────────────


def test_bare_make_predicate_is_a_working_predicate_with_no_database():
    """The out-of-tree contract (~22 external ``_get_dispatch`` implementors,
    ``clausal.reflection``, ``clpb``, the builtin registry): a class minted by
    a bare ``make_predicate`` must append clauses, take a dispatch and answer
    ``_get_dispatch()`` with no Database in sight."""
    cls = make_predicate("Detached", ["x"])
    assert cls._clauses == []
    assert cls._dispatch_fn is None
    assert cls._lazy_recompile is None
    assert cls._signature is None
    assert cls._locked is False
    assert cls._clauses_source is None
    assert cls._dynamic_arities is None

    c = Clause(head=cls(1), body=[])
    cls._clauses.append(c)
    assert cls._clauses == [c]

    fn = lambda *a: iter([])  # noqa: E731
    with cls._mutate("test", "recompile"):      # the gate, P3-3 Task 3
        cls._dispatch_fn = fn
    assert cls._get_dispatch() is fn
    assert cls._get_dispatch(1) is fn
    cls._lock()
    assert cls._locked is True
    cls._unlock()
    assert cls._locked is False


def test_detached_classes_of_the_same_name_and_arity_do_not_share_state():
    """Each detached class gets its OWN private row — the builtin registry
    mints several same-named classes (one per arity) in one process."""
    a = make_predicate("dup", ["x"])
    b = make_predicate("dup", ["x"])
    a._clauses.append("A")
    assert b._clauses == []
    a._locked = True
    assert b._locked is False
    assert a._row is not b._row


def test_detached_row_is_private_and_lazy():
    cls = make_predicate("Lazy", ["x"])
    assert cls._row is None, "no row until some predicate state is touched"
    _ = cls._clauses
    assert isinstance(cls._row, PredRow)
    assert cls._row._db is not None
    assert cls._row._key == ("Lazy", 1)


def test_predicate_meta_mutators_work_detached_and_respect_the_lock():
    cls = make_predicate("Mut", ["x"])
    c1, c2 = Clause(head=cls(1), body=[]), Clause(head=cls(2), body=[])
    cls._assertz(c1)
    cls._asserta(c2)
    assert cls._clauses == [c2, c1]
    assert cls._retract(c2.head) is True
    assert cls._clauses == [c1]
    cls._lock()
    with pytest.raises(RuntimeError):
        cls._assertz(c2)
    with pytest.raises(RuntimeError):
        cls._asserta(c2)
    with pytest.raises(RuntimeError):
        cls._retract(c1.head)


# ── _bind_row: rebinding carries the per-CLASS state ────────────────────────


def test_bind_row_is_idempotent():
    db = Database()
    cls = make_predicate("p", ["a"])
    cls._bind_row(db, "p", 1)
    row = cls._row
    cls._bind_row(db, "p", 1)
    assert cls._row is row


def test_bind_row_uses_the_passed_functor_not_the_class_name():
    """An aliased ``-import_from`` binds a class under a name that is not its
    own; the clauses live under the name the CLAUSE HEADS use."""
    db = Database()
    cls = make_predicate("original", ["a"])
    cls._bind_row(db, "alias", 1)
    assert cls._row._key == ("alias", 1)
    db.assertz(_clause("alias", 1))
    assert len(cls._clauses) == 1


def test_rebinding_carries_dynamic_arities_locked_and_source():
    """These three were per-CLASS slots before the inversion, so they travel
    with the class when it is re-bound (a clause-free import getting clauses
    downstream, a file compiled twice, a name defined at two arities).

    ``authorized=True`` because a cross-database re-bind is policed from P3-3
    Task 3 fix round 1 — it MOVES predicate identity, so only the clause
    install the mutation gate has cleared may do it. This test stands in for
    that site; what it pins is the carry-over, which is unchanged."""
    db1, db2 = Database(), Database()
    cls = make_predicate("p", ["a"])
    cls._bind_row(db1, "p", 1)
    cls._dynamic_arities = {1}
    cls._locked = True
    cls._clauses_source = ("m1", "/tmp/m1.clausal")
    cls._bind_row(db2, "p", 3, authorized=True)
    assert cls._dynamic_arities == {1}
    assert cls._locked is True
    assert cls._clauses_source == ("m1", "/tmp/m1.clausal")
    # ... and the union, not a replacement, when the target has its own.
    cls._dynamic_arities = {3}
    cls._bind_row(db1, "p", 1, authorized=True)
    assert cls._dynamic_arities == {1, 3}


def test_rebinding_leaves_the_old_rows_clauses_where_they_were():
    db1, db2 = Database(), Database()
    cls = make_predicate("p", ["a"])
    cls._bind_row(db1, "p", 1)
    db1.assertz(_clause("p", 1))
    cls._bind_row(db2, "p", 1, authorized=True)   # policed; see above
    assert cls._clauses == []
    assert db1.clauses_for("p", 1) == [_clause("p", 1)]


def test_an_unauthorized_rebind_leaves_the_class_where_it_is():
    """The police itself: a recompile or a dispatch install may not move a
    class off another database's row (P3-3 Task 3 fix round 1). A class on
    its private DETACHED row is unbound, not foreign, so its first bind is
    always allowed."""
    db1, db2 = Database(), Database()
    cls = make_predicate("p", ["a"])
    cls._bind_row(db1, "p", 1)                    # first bind: detached -> db1
    db1.assertz(_clause("p", 1))

    cls._bind_row(db2, "p", 1)                    # unauthorized: refused
    assert cls._row is db1.row("p", 1)
    assert cls._clauses == [_clause("p", 1)]

    # Re-binding WITHIN the same database is not a move and stays open (a
    # name defined at two arities).
    cls._bind_row(db1, "p", 3)
    assert cls._row is db1.row("p", 3)


# ── _bind_row: a DETACHED row's clauses travel, or the bind is refused ──────
#
# Final review I-1.  A class minted by ``make_predicate`` and asserted into
# before any load holds its clauses on a private detached row that nothing but
# the class can reach.  Binding it to a real row used to carry three fields
# and leave the clauses behind — invisibly, and since Task 2 made the row the
# only store, unrecoverably.  Two outcomes now, and silent loss is neither.


class TestBindRowCarriesDetachedClauses:
    """The reviewer's own P2 scenario, both ways round."""

    def test_a_standalone_predicate_keeps_its_clauses_when_it_is_bound(self):
        """``make_predicate`` + two ``_assertz``, compiled into a Module's
        database, then a builtin ``assertz`` of a third clause: three answers,
        in order, from the one row the class now reads."""
        from clausal.logic.compiler.predicate import compile_predicate_trampoline
        from clausal.logic.database import Module
        from clausal.logic.solve import solve
        from clausal.logic.variables import Var, deref

        P = make_predicate("dp", ["x"])
        P._assertz(Clause(head=P(x=1), body=[]))
        P._assertz(Clause(head=P(x=2), body=[]))
        assert P._row.detached is True and len(P._clauses) == 2

        module_dict = {"dp": P}
        mod = Module("i1_prog", module_dict=module_dict)
        mod.db.mark_dynamic("dp", 1)
        compile_predicate_trampoline(
            "dp", 1, list(P._clauses), mod.db,
            globals_=module_dict, pred_cls=P,
        )
        # The bind happened, and it did not cost the two clauses.
        assert P._row is mod.db.row("dp", 1)
        assert P._row.detached is False
        assert len(P._clauses) == 2

        X = Var()
        assert [deref(X) for _ in solve(("dp", X), mod)] == [1, 2]

        for _ in solve(("assertz", ("dp", 3)), mod):
            pass
        assert len(P._clauses) == 3
        assert P._row is mod.db.row("dp", 1)
        Y = Var()
        assert [deref(Y) for _ in solve(("dp", Y), mod)] == [1, 2, 3]

    def test_the_detached_rows_write_stamps_travel_with_its_clauses(self):
        db = Database()
        P = make_predicate("dpw", ["x"])
        P._assertz(Clause(head=P(x=1), body=[]))
        stamps_before = list(P._row.writes)
        assert stamps_before, "the _assertz is a stamped write"

        P._bind_row(db, "dpw", 1)
        assert P._row is db.row("dpw", 1)
        assert len(P._clauses) == 1
        assert P._row.writes[:len(stamps_before)] == stamps_before

    def test_the_detached_row_is_emptied_rather_than_left_duplicating(self):
        db = Database()
        P = make_predicate("dpe", ["x"])
        P._assertz(Clause(head=P(x=1), body=[]))
        old_row = P._row
        P._bind_row(db, "dpe", 1)
        assert old_row.clauses == []
        assert len(P._clauses) == 1

    def test_two_non_empty_clause_sets_refuse_the_bind_instead_of_losing_one(self):
        """Nothing says which set wins or how they interleave, so the bind is
        refused — naming both rows.  This is the reviewer's probe verbatim
        (``compile_predicate_trampoline`` with no database, so the class is
        still detached when the builtin ``assertz`` writes the db row):
        before the fix it answered ``[3]``, two clauses gone in silence."""
        from clausal.logic.compiler.predicate import compile_predicate_trampoline
        from clausal.logic.database import Module
        from clausal.logic.exceptions import LogicException
        from clausal.logic.solve import solve

        P = make_predicate("dq", ["x"])
        P._assertz(Clause(head=P(x=1), body=[]))
        P._assertz(Clause(head=P(x=2), body=[]))
        module_dict = {"dq": P}
        mod = Module("i1_prog2", module_dict=module_dict)
        mod.db.mark_dynamic("dq", 1)
        compile_predicate_trampoline(
            "dq", 1, list(P._clauses), None,
            globals_=module_dict, pred_cls=P,
        )
        assert P._row.detached is True

        with pytest.raises(LogicException) as exc_info:
            for _ in solve(("assertz", ("dq", 3)), mod):
                pass
        message = exc_info.value.term.args[1]
        assert "detached row" in message
        assert "dq/1" in message
        assert "silently discard" in message
        # And nothing was lost on the way out: both sets are still readable.
        assert len(P._clauses) == 2
        assert len(mod.db.row("dq", 1).clauses) == 1


# ── _dynamic_arities keeps its None-vs-set semantics (row-LOCAL, not derived)


def test_dynamic_arities_is_row_local_and_independent_of_row_dynamic():
    """``row.dynamic`` is a per-(f, a) boolean; ``_dynamic_arities`` is a
    per-NAME set whose None-vs-set and size-1-vs-larger distinctions both
    decide ``_declared_arity``. Deriving one from the other would be lossy, so
    the set stays its own row field."""
    db = Database()
    cls = make_predicate("p", ["a"])
    cls._bind_row(db, "p", 1)
    db.mark_dynamic("p", 1)
    assert db.row("p", 1).dynamic is True
    assert cls._dynamic_arities is None, "declared-at is not the same question"
    cls._dynamic_arities = set()
    assert cls._dynamic_arities == set()
    assert cls._dynamic_arities is not None, "empty set != never stamped"


# ── _predicate_functor_names must agree with Database truth ─────────────────
#
# Step 3 asks "will this declared name have clauses?" from the CLAUSE NODES,
# before step 4 attaches anything, and the answer decides the binding shape:
# a predicate keeps its ``PredicateMeta`` class, a data functor is unbound to
# its interned spelling so its terms compile to cells (R6).  A divergence
# between that answer and what the Database ends up holding silently flips
# goal-vs-data-cell emission, with no error anywhere — so it is pinned here,
# one case each way, against the row-backed truth the inversion installs.


def _load_pfn_module(tmp_path, monkeypatch, name, source):
    import textwrap
    import clausal.logic.compiler_v2 as cv2
    from clausal.import_hook import _load_module

    captured = {}
    orig = cv2._predicate_functor_names

    def spy(predicate_nodes, module_items):
        result = orig(predicate_nodes, module_items)
        captured["names"] = set(result)
        return result

    monkeypatch.setattr(cv2, "_predicate_functor_names", spy)
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    module = _load_module(name, str(path))
    assert "names" in captured, "the spy never fired — the anchor moved"
    return module, getattr(module, "$module").db, captured["names"]


_PFN_SOURCE = """
    -module(pfn_sync_mod, [pfn_greeting/1, pfn_point(X, Y)])

    pfn_greeting(N) <- (N == 1)

    pfn_origin(P) <- (P == pfn_point(0, 0))
"""


def test_predicate_functor_names_says_predicate_and_the_database_agrees(
    tmp_path, monkeypatch
):
    """A declared name WITH clauses: step 3 calls it a predicate, and the
    Database really does hold a row with those clauses."""
    module, db, names = _load_pfn_module(
        tmp_path, monkeypatch, "pfn_sync_mod", _PFN_SOURCE
    )
    assert "pfn_greeting" in names
    row = db.row("pfn_greeting", 1)
    assert row is not None, "step 3 called it a predicate; the db has no row"
    assert len(row.clauses) == 1
    # ... and the binding shape that answer produced is the class, reading
    # through that very row.
    cls = getattr(module, "pfn_greeting")
    assert isinstance(cls, PredicateMeta)
    assert cls._row is row
    assert cls._clauses is row.clauses


def test_predicate_functor_names_says_data_and_the_database_agrees(
    tmp_path, monkeypatch
):
    """A declared functor with NO clauses: step 3 calls it data, and the
    Database really does hold nothing for it at any arity."""
    module, db, names = _load_pfn_module(
        tmp_path, monkeypatch, "pfn_sync_data", _PFN_SOURCE
    )
    assert "pfn_point" not in names
    assert db.row("pfn_point", 2) is None
    assert not [k for k in db._clauses if k[0] == "pfn_point"]
    # ... and the binding shape that answer produced is the ATOM, which is
    # what makes ``pfn_point(0, 0)`` compile to a cell.
    assert getattr(module, "pfn_point") == mint("pfn_point")
    assert not isinstance(getattr(module, "pfn_point"), PredicateMeta)


# ══════════════════════════════════════════════════════════════════════════════
# P3-3 Task 2, fix round 1
# ══════════════════════════════════════════════════════════════════════════════


def _one_arg_answers(module, functor):
    """Every solution of ``functor(X)`` in *module*, X deref'd."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, Trail, deref
    lm = module.__dict__["$module"]
    out = []
    trail = Trail()
    x = Var()
    for _ in call(functor, x, module=lm, trail=trail):
        out.append(deref(x))
    return out


def _run_goal(module, functor, arg):
    """Run ``functor(arg)`` once; return the number of solutions taken (0 or 1)."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Trail
    lm = module.__dict__["$module"]
    trail = Trail()
    for _ in call(functor, arg, module=lm, trail=trail):
        return 1
    return 0


# ── F1: the INSTANCE face of the seven relocated attributes ─────────────────
#
# The seven moved to METACLASS properties, which serve ``cls.x`` and are never
# consulted for ``instance.x`` — and ``__slots__`` leaves instances no
# ``__dict__`` to fall back on. Before the move an instance resolved them by
# the ordinary MRO walk onto the plain class attribute. Every predicate class
# therefore also carries a plain class-level property of each name, delegating
# to the class (and so to the row), so both faces coexist and instance reads
# stay LIVE.

_RELOCATED = (
    "_clauses",
    "_clauses_source",
    "_dispatch_fn",
    "_lazy_recompile",
    "_signature",
    "_locked",
    "_dynamic_arities",
)


def test_instances_still_resolve_all_seven_relocated_attributes():
    cls = make_predicate("InstFace", ["x"])
    inst = cls(1)
    assert [getattr(inst, n) for n in _RELOCATED] == [
        [], None, None, None, None, False, None,
    ], "an instance must read the same defaults the class does"


def test_instance_reads_of_all_seven_are_live_through_the_class():
    """Mutate through the class (and through the Database), read through an
    instance — the instance must see it, for every one of the seven."""
    db = Database()
    cls = make_predicate("InstLive", ["x"])
    cls._bind_row(db, "InstLive", 1)
    inst = cls(1)

    c = _clause("InstLive", 1)
    db.assertz(c)                                   # via the Database
    fn = lambda *a: iter([])                        # noqa: E731
    lazy = lambda: fn                               # noqa: E731
    with cls._mutate("test", "recompile"):          # via the class, gated
        cls._dispatch_fn = fn
    cls._lazy_recompile = lazy
    cls._signature = ("x",)
    cls._locked = True
    cls._clauses_source = ("m", "/tmp/m.clausal")
    cls._dynamic_arities = {1}

    assert inst._clauses == [c]
    assert inst._clauses is db._clauses[("InstLive", 1)]
    assert inst._dispatch_fn is fn
    assert inst._lazy_recompile is lazy
    assert inst._signature == ("x",)
    assert inst._locked is True
    assert inst._clauses_source == ("m", "/tmp/m.clausal")
    assert inst._dynamic_arities == {1}

    # ... and a SECOND instance made after the writes agrees with the first.
    assert cls(2)._locked is True


def test_instance_writes_to_the_relocated_names_still_refuse():
    """Read-only on purpose: ``instance._locked = True`` raised AttributeError
    before this task too (not in ``__slots__``, no instance ``__dict__``), so
    a setter would be a new capability rather than a restored one."""
    cls = make_predicate("InstRO", ["x"])
    inst = cls(1)
    for name in _RELOCATED:
        with pytest.raises(AttributeError):
            setattr(inst, name, object())


def test_a_field_named_like_a_relocated_attribute_stays_a_field():
    """``__slots__`` has already claimed that name; injecting a property of the
    same name would be a ValueError at class creation. The field wins, and the
    CLASS-level read still answers from the row."""
    cls = make_predicate("FieldClash", ["_signature"])
    assert cls._fields == ("_signature",)
    inst = cls("field value")
    assert inst._signature == "field value", "the field, not the row"
    assert cls._signature is None, "the class still reads the row"
    cls._signature = ("_signature",)
    assert cls._signature == ("_signature",)
    assert inst._signature == "field value"


# ── F2: reading never mints; ensure_clauses() is the one promotion point ────


def test_reading_a_bound_clauseless_class_leaves_is_defined_false():
    """The regression this fix exists for. Task 2 routed every
    ``PredicateMeta._clauses`` read through the row, and the getter used to
    ``setdefault`` — so merely LOOKING at a clause-less ``-dynamic`` class
    (``__repr__``, ``_clause_arity``, ``_declared_arity``, the compiler's own
    inspections) reported it defined."""
    db = Database()
    cls = make_predicate("declared_only", ["x"])
    cls._bind_row(db, "declared_only", 1)
    db.mark_dynamic("declared_only", 1)
    cls._dynamic_arities = {1}

    assert cls._clauses == []
    assert repr(cls)                     # __repr__ reads _clauses and len()s it
    assert cls._clause_arity() is None   # walks the clause list
    assert cls._declared_arity(2) == 1   # reads _clauses then _dynamic_arities

    assert db.is_defined("declared_only", 1) is False
    assert ("declared_only", 1) not in db._clauses


def test_the_first_assertz_onto_a_bound_class_mints_and_aliases():
    """... and the sanctioned mutators do mint, both directions."""
    db = Database()
    cls = make_predicate("mints", ["x"])
    cls._bind_row(db, "mints", 1)
    assert db.is_defined("mints", 1) is False

    cls._assertz(Clause(head=cls(1), body=[]))       # class-side mutator
    assert db.is_defined("mints", 1) is True
    assert cls._clauses is db._clauses[("mints", 1)]

    db.assertz(_clause("mints", 2))                  # Database-side mutator
    assert len(cls._clauses) == 2

    other = make_predicate("mints2", ["x"])
    other._bind_row(db, "mints2", 1)
    other._asserta(Clause(head=other(1), body=[]))
    assert db.is_defined("mints2", 1) is True


def test_define_predicate_mints_through_db_assertz():
    """``LogicModule.define_predicate`` is a sanctioned minting site; it gets
    there by delegating to ``Database.assertz``, so it needs no separate
    ``ensure_clauses`` of its own. Pinned so a future refactor that stops
    delegating notices."""
    import inspect
    from clausal.logic.database import Module
    source = inspect.getsource(Module.define_predicate)
    assert "self.db.assertz(" in source


# ── F3: db.assertz is gated like every other channel ───────────────────────


def test_low_level_db_assertz_is_refused_on_a_locked_static_predicate(
    tmp_path, monkeypatch
):
    """FLIPPED by P3-3 Task 3, as Task 2 said it would be.

    Task 2 pinned the opposite of this: ``Database._pred_cls_for`` used to
    return ``None`` for a LOCKED class, so a low-level ``db.assertz`` reached
    ``db._clauses`` but not the class, and solve() kept answering the old
    clause set — a PARTIAL bypass guard, there by accident of the dual store.
    With the class reading the row, that accident was gone and ``db.assertz``
    on a locked static predicate CHANGED THE ANSWERS: ``[1]`` became
    ``[1, 2]``.

    The mutation gate closes it.  ``Database.assertz`` is a channel like any
    other now: it asks the one policy ("may this author write this row"), and
    a runtime author writing a locked, owned row is refused — with the same
    diagnostic the other three channels raise, from the same place.

    See ``.superpowers/sdd/p33-state-relocation/task-2-inversions.md``,
    "Fix round 1 — carry-forward for Task 3"."""
    from clausal.logic.exceptions import LogicException

    module, db, _ = _load_pfn_module(
        tmp_path, monkeypatch, "f3_locked_bypass",
        """
        -module(f3_locked_bypass, [f3_static/1])

        f3_static(1)
        """,
    )
    cls = getattr(module, "f3_static")
    assert cls._locked is True, "step 7 must have locked it, or this pins nothing"
    assert _one_arg_answers(module, "f3_static") == [1]

    with pytest.raises(LogicException) as exc_info:
        db.assertz(Clause(head=cls(2), body=[]))
    assert "may not write f3_static/1" in str(exc_info.value.term.args[1])

    assert len(cls._clauses) == 1, "nothing was written"
    assert _one_arg_answers(module, "f3_static") == [1], (
        "the answers did not move — this is the door Task 2 left open"
    )
    # The enforcement doors the dual store never covered are still shut.
    with pytest.raises(RuntimeError):
        cls._assertz(Clause(head=cls(3), body=[]))


# ── F4: retract/1's last-clause path must invalidate the dispatch ───────────


def test_retract_builtin_of_the_last_clause_leaves_no_answers(
    tmp_path, monkeypatch
):
    """The diff's only NEW logic. ``retract/1`` in ``builtins/database_ops.py``
    deletes straight out of ``db._clauses`` and only recompiles ``if clauses``
    — so when the LAST clause goes there is no recompile, and the dispatch
    compiled from the clause that just left would keep answering. The deleted
    class-mirror loop used to clear it as a side effect of syncing; that is now
    an explicit ``row.invalidate()``.

    Verified to bite: with the ``row.invalidate()`` removed, the assertions
    below report ``[7]`` after the retract instead of ``[]``."""
    module, db, _ = _load_pfn_module(
        tmp_path, monkeypatch, "f4_retract_last",
        """
        -dynamic(f4_fact/1)
        -module(f4_retract_last, [f4_fact/1])

        f4_fact(7)
        """,
    )
    cls = getattr(module, "f4_fact")
    assert _one_arg_answers(module, "f4_fact") == [7]

    assert _run_goal(module, "retract", cls(7)) == 1
    assert db.clauses_for("f4_fact", 1) == []
    assert cls._clauses == []
    assert _one_arg_answers(module, "f4_fact") == [], (
        "a retracted last clause must not keep answering from the stale "
        "dispatch it was compiled into"
    )

    # ... and the predicate comes back when a clause does.
    assert _run_goal(module, "assertz", cls(9)) == 1
    assert _one_arg_answers(module, "f4_fact") == [9]


def test_retract_builtin_does_not_create_a_dispatch_entry_it_did_not_find():
    """The invalidate is guarded on an EXISTING ``_dispatch`` entry, exactly as
    ``Database.assertz``/``asserta``/``retract`` guard theirs — an
    unconditional ``_dispatch[key] = None`` would flip ``db.row(create=False)``
    from ``None`` to a row for a key nothing ever compiled."""
    db = Database()
    c = _clause("never_compiled", 1)
    db.assertz(c)
    assert ("never_compiled", 1) not in db._dispatch
    assert db.retract(c.head) is True
    assert ("never_compiled", 1) not in db._dispatch
