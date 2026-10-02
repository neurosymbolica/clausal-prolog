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

from clausal.logic.atoms import mint
from clausal.logic.database import Clause, Database, PredRow, WriteStamp
from tests._suffix import SEAM


def _clause(functor, *args):
    return Clause(head=(functor, *args) if args else functor, body=[])


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
    assert db.retract(("k", 1)) is True
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



# ── the class reads THROUGH the row ─────────────────────────────────────────


# ── the arity-blind mirror is gone (identity todo instance 3) ───────────────


def test_database_no_longer_has_pred_cls_for():
    assert not hasattr(Database, "_pred_cls_for")


# ── detached compatibility mode: no Database anywhere ───────────────────────


# ── _bind_row: rebinding carries the per-CLASS state ────────────────────────


    # ``dynamic_arities`` used to travel here too, unioned across rebinds.  It
    # is DERIVED from the Database now (option D, 2026-09-22), so there is no
    # per-class set to carry: a rebound class reads the declarations of
    # whichever Database its new row belongs to.


# ── _bind_row: a DETACHED row's clauses travel, or the bind is refused ──────
#
# Final review I-1.  A class minted by ``make_predicate`` and asserted into
# before any load holds its clauses on a private detached row that nothing but
# the class can reach.  Binding it to a real row used to carry three fields
# and leave the clauses behind — invisibly, and since Task 2 made the row the
# only store, unrecoverably.  Two outcomes now, and silent loss is neither.


# ── the declared-at set is DERIVED from the Database (option D, 2026-09-22) ──
#
# There used to be a test here --
# ``test_dynamic_arities_is_row_local_and_independent_of_row_dynamic`` --
# pinning that the set was row-LOCAL and "cannot be reconstructed" from
# ``row.dynamic``, on the grounds that a per-(f, a) BOOLEAN cannot express
# either "nothing was declared" or "more than one arity".
#
# That is true of ONE key and false of the SET.  Scanning ``db._dynamic`` for
# every entry with a given functor recovers both distinctions, so
# ``_declared_arity`` derives the set that way and the per-class property is
# gone.  The one thing the old shape could express and this cannot is an
# explicitly EMPTY stamp as distinct from never having been stamped --
# meaningless here, since ``_declared_arity`` declines on both.

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
    path = tmp_path / f"{name}{SEAM}"
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
    # ... and the binding shape that answer produced is the predicate's
    # HANDLE (W4b-2d; it was the class), resolving to that very row.
    from clausal.logic.predicate import (
        mint_predicate_handle, resolve_predicate_row,
    )
    binding = getattr(module, "pfn_greeting")
    assert binding == mint_predicate_handle(db, "pfn_greeting")
    assert resolve_predicate_row(binding, arity=1, db=db) is row
    assert resolve_predicate_row(binding, arity=1, db=db).clauses is row.clauses


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
    assert not isinstance(getattr(module, "pfn_point"), type)


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


# ── F1: the predicate-state facades were RETIRED (W2, 2026-09-22) ──────────
# Their raising tombstones lived on the metaclass; the tests of them went with
# the class at W4b-3 slice 7.


# ── F2: reading never mints; ensure_clauses() is the one promotion point ────


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
    row = db.row("f3_static", 1)
    assert row.locked is True, "step 7 must have locked it, or this pins nothing"
    assert _one_arg_answers(module, "f3_static") == [1]

    with pytest.raises(LogicException) as exc_info:
        db.assertz(Clause(head=("f3_static", 2), body=[]))
    assert "may not write f3_static/1" in exc_info.value.message

    assert len(db.row("f3_static", 1).clauses) == 1, "nothing was written"
    assert _one_arg_answers(module, "f3_static") == [1], (
        "the answers did not move — this is the door Task 2 left open"
    )
    # The class-side door (``cls._assertz``) the dual store never covered
    # does not exist post-flip: the module binding is a handle (a str), which
    # carries no write channel of its own.
    binding = getattr(module, "f3_static")
    assert type(binding) is str and not hasattr(binding, "_assertz")


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
    assert _one_arg_answers(module, "f4_fact") == [7]

    assert _run_goal(module, "retract", ("f4_fact", 7)) == 1
    assert db.clauses_for("f4_fact", 1) == []
    assert db.row("f4_fact", 1).clauses == []
    assert _one_arg_answers(module, "f4_fact") == [], (
        "a retracted last clause must not keep answering from the stale "
        "dispatch it was compiled into"
    )

    # ... and the predicate comes back when a clause does.
    assert _run_goal(module, "assertz", ("f4_fact", 9)) == 1
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
