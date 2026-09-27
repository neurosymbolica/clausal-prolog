"""P3-3 Task 4 — bake-in from rows, and the stencil-v2 backend seam.

Two things are pinned here, both of which read the ``PredRow`` that Tasks 1-3
made the single home of predicate state:

* **Bake-in from the row.**  ``_inject_resolved_targets``'s
  ``_maybe_cache_dispatch`` captures a called predicate's compiled dispatch
  into the caller's globals under ``$disp_<name>_<arity>`` so generated code
  can jump straight in.  It now asks the ROW whether that is safe (``locked``,
  with a dispatch installed) rather than reading class attributes that merely
  forward to the row.  The staleness invariant that makes baking safe at all
  is asserted directly: only LOCKED rows are ever baked, so
  ``row.invalidate()`` on an unlocked row can never orphan a baked reference.

* **The backend seam.**  ``Database.set_backend_chooser`` is the ONE
  per-predicate backend decision point stencil-v2 will target (see
  ``implementation_plans/stencil-v2-scoping-memo.md``, "The integration
  seam").  With no chooser set — the default — nothing at all changes: the
  Python dispatch installs exactly as it did before this task.
"""

from __future__ import annotations

import os

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.database import Database
from clausal.logic.exceptions import LogicException
from clausal.logic.compiler.globals_env import _disp_key, _inject_resolved_targets
from clausal.logic.compiler.predicate import _install
from clausal.logic.predicate import (
    mint_predicate_handle, register_handle_owner)
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


FIXTURES = os.path.join(os.path.dirname(__file__), "clausal_modules")


def _fresh_db(name: str = "_seam") -> Database:
    return Database({"__name__": name})


def _bound_class(db: Database, functor: str, arity: int, *, locked: bool,
                 dispatch=None):
    """``db``'s row for ``functor/arity``, locked or not, with *dispatch*
    installed -- and the predicate HANDLE a module binds for it, which is
    what ``_inject_resolved_targets`` meets in a module's globals since the
    flip.  (A ``make_predicate`` class bound to the row until W4b-3 slice 6;
    the name is kept so the tests below read unchanged.)"""
    row = db.row(functor, arity, create=True)
    row.locked = locked
    if dispatch is not None:
        with db.mutate(functor, arity, author="test", kind="recompile",
                       detail="test fixture"):
            row.dispatch_fn = dispatch
    register_handle_owner(db)
    return mint_predicate_handle(db, functor)


def _dummy_dispatch(*_args, **_kwargs):
    return iter(())


# ── Bake-in reads the row ──────────────────────────────────────────────────


class TestBakeInReadsTheRow:
    def test_a_locked_row_with_a_dispatch_is_baked(self):
        db = _fresh_db()
        cls = _bound_class(db, "Leaf", 1, locked=True, dispatch=_dummy_dispatch)
        base_globals: dict = {}
        _inject_resolved_targets({("Leaf", 1)}, base_globals, db, {"Leaf": cls})
        assert base_globals[_disp_key("Leaf", 1)] is _dummy_dispatch

    def test_an_unlocked_row_is_never_baked(self):
        """The staleness invariant: an unlocked row's dispatch may be replaced
        or cleared at any time, so baking it would hand a call site a
        reference nothing can invalidate."""
        db = _fresh_db()
        cls = _bound_class(db, "Leaf", 1, locked=False, dispatch=_dummy_dispatch)
        # there IS one to bake
        assert db.row("Leaf", 1).dispatch_fn is _dummy_dispatch
        base_globals: dict = {}
        _inject_resolved_targets({("Leaf", 1)}, base_globals, db, {"Leaf": cls})
        assert _disp_key("Leaf", 1) not in base_globals

    def test_a_locked_row_with_no_dispatch_is_not_baked(self):
        db = _fresh_db()
        cls = _bound_class(db, "Leaf", 1, locked=True)
        base_globals: dict = {}
        _inject_resolved_targets({("Leaf", 1)}, base_globals, db, {"Leaf": cls})
        assert _disp_key("Leaf", 1) not in base_globals

    def test_an_arity_mismatch_is_not_baked(self):
        """Unchanged rationale (see ``_maybe_cache_dispatch``): baking
        ``citation/3``'s dispatch under ``$disp_citation_2`` would jump the
        call site straight past the arity check ``_get_dispatch`` exists to
        make."""
        db = _fresh_db()
        cls = _bound_class(db, "Leaf", 1, locked=True, dispatch=_dummy_dispatch)
        base_globals: dict = {}
        _inject_resolved_targets({("Leaf", 2)}, base_globals, db, {"Leaf": cls})
        # Operator ruling 2026-09-24 (the aliased-import leak): an UNQUALIFIED
        # wrong-arity call site now gets its own ``$disp_`` entry -- but never
        # the class's dispatch.  It re-resolves in this module under this
        # name and otherwise REFUSES, so the arity check is not jumped.
        from clausal.predicate_diagnostics import PredicateArityMismatchError
        baked = base_globals.get(_disp_key("Leaf", 2))
        assert baked is not None and baked is not _dummy_dispatch
        with pytest.raises(PredicateArityMismatchError):
            baked(1, 2, None)

    def test_no_disp_key_exists_for_an_unlocked_row_after_a_real_compile(self):
        """The invariant end-to-end: after a representative compile, no
        ``$disp_`` key anywhere in the module's compiled globals names an
        UNLOCKED row — so ``invalidate()`` on an unlocked row can never
        orphan a baked reference."""
        mod = _load_module(
            "_t4_bakein_fixture", os.path.join(FIXTURES, "family.clausal"))
        db = mod.__dict__["$module"].db
        unlocked = []
        for functor, arity in list(db._clauses):
            row = db.row(functor, arity)
            if not row.locked:
                unlocked.append((functor, arity))
        # Force one: clearing ``locked`` after the fact is what a later
        # recompile of a still-open predicate looks like.
        db.row("parent", 2).locked = False
        unlocked.append(("parent", 2))
        for functor, arity in list(db._clauses):
            fn = db.get_dispatch(functor, arity)
            if fn is None:
                continue
            for name, ar in unlocked:
                key = _disp_key(name, ar)
                assert fn.__globals__.get(key) is None, (
                    f"{key} is baked into {functor}/{arity}'s globals from an "
                    f"UNLOCKED row — invalidating it would orphan this jump"
                )

    def test_a_baked_call_site_still_answers(self):
        """Behaviour, not plumbing: bake-in sits on the call path, so a
        module whose predicates call each other must still answer."""
        mod = _load_module(
            "_t4_bakein_answers", os.path.join(FIXTURES, "family.clausal"))
        who = Var()
        got = sorted(deref(who) for _ in call(mod.ancestor, mint("tom"), who))
        assert got == [mint("ann"), mint("bob"), mint("liz"), mint("pat")]


# ── The backend seam ───────────────────────────────────────────────────────


@pytest.fixture
def clean_backend_seam():
    """Restore the process-wide chooser and backend registry."""
    from clausal.logic import database as _database
    previous = Database.set_backend_chooser(None)
    registered = dict(_database._BACKEND_INSTALLERS)
    try:
        yield
    finally:
        Database.set_backend_chooser(previous)
        _database._BACKEND_INSTALLERS.clear()
        _database._BACKEND_INSTALLERS.update(registered)


class TestBackendSeam:
    def test_the_default_backend_is_python(self, clean_backend_seam):
        db = _fresh_db()
        assert _install(db, "p", 1, _dummy_dispatch) is _dummy_dispatch
        assert db.get_dispatch("p", 1) is _dummy_dispatch
        assert db.row("p", 1).backend == "python"

    def test_no_chooser_means_the_seam_does_not_run(self, clean_backend_seam):
        """Default path: with no chooser set the seam must not so much as look
        a row up, so an install is exactly the install of before this task."""
        db = _fresh_db()
        assert db.backend_dispatch("p", 1, _dummy_dispatch) is _dummy_dispatch
        assert db._rows == {}, "the seam minted a row it had no reason to read"

    def test_the_chooser_sees_the_row_and_its_answer_is_recorded(
            self, clean_backend_seam):
        db = _fresh_db()
        seen = []

        def chooser(row):
            seen.append(row)
            return "python"

        assert Database.backend_chooser() is None  # the shipped default
        Database.set_backend_chooser(chooser)
        assert Database.backend_chooser() is chooser
        _install(db, "p", 2, _dummy_dispatch)
        assert [r.key for r in seen] == [("p", 2)]
        assert seen[0].db is db
        assert db.row("p", 2).backend == "python"
        assert db.get_dispatch("p", 2) is _dummy_dispatch

    def test_a_registered_backend_supplies_the_dispatch(self, clean_backend_seam):
        db = _fresh_db()
        calls = []

        def stencil_installer(row, fn):
            calls.append((row.key, fn))
            return _other_dispatch

        def _other_dispatch(*_a, **_k):
            return iter(())

        Database.register_backend("stencil-probe", stencil_installer)
        Database.set_backend_chooser(lambda row: "stencil-probe")
        assert _install(db, "p", 1, _dummy_dispatch) is _other_dispatch
        assert calls == [(("p", 1), _dummy_dispatch)]
        assert db.get_dispatch("p", 1) is _other_dispatch
        assert db.row("p", 1).backend == "stencil-probe"

    def test_a_backend_that_declines_falls_back_to_python(self, clean_backend_seam):
        """A real backend cannot compile every predicate shape.  Returning
        ``None`` means "not mine" and must leave the Python dispatch — and
        ``row.backend`` — exactly as they would have been."""
        Database.register_backend("declines", lambda row, fn: None)
        Database.set_backend_chooser(lambda row: "declines")
        db = _fresh_db()
        assert _install(db, "p", 1, _dummy_dispatch) is _dummy_dispatch
        assert db.get_dispatch("p", 1) is _dummy_dispatch
        assert db.row("p", 1).backend == "python"

    def test_an_unregistered_backend_name_is_loud(self, clean_backend_seam):
        """Fix round 1 (M-2): through the ENGINE's error family, like every
        other refusal in database.py — an ISO ``existence_error(backend, …)``
        carried by a ``LogicException``, so ``catch/3`` can see it and the
        message is not a stray Python builtin."""
        Database.set_backend_chooser(lambda row: "no-such-backend")
        db = _fresh_db()
        with pytest.raises(LogicException) as exc:
            _install(db, "p", 1, _dummy_dispatch)
        term = exc.value.term
        assert cell_functor(term) == "error"
        inner = cell_args(term)[0]
        assert cell_functor(inner) == "existence_error"
        assert cell_args(inner)[0] == mint("backend")
        assert cell_args(inner)[1] == "no-such-backend"
        assert "no-such-backend" in str(exc.value)
        assert "p/1" in str(exc.value)

    def test_python_cannot_be_re_registered(self, clean_backend_seam):
        with pytest.raises(ValueError):
            Database.register_backend("python", lambda row, fn: None)

    def test_a_python_chooser_leaves_a_real_module_unchanged(
            self, clean_backend_seam):
        """End-to-end: with the seam wired but choosing ``python``, a module
        loads and answers exactly as it does with no chooser at all."""
        path = os.path.join(FIXTURES, "family.clausal")
        baseline = _load_module("_t4_seam_baseline", path)
        Database.set_backend_chooser(lambda row: "python")
        with_seam = _load_module("_t4_seam_python", path)
        db = with_seam.__dict__["$module"].db
        assert all(db.row(*k).backend == "python" for k in db._clauses)
        assert sorted(baseline.__dict__["$module"].db._clauses) == sorted(
            db._clauses)
        who = Var()
        assert sorted(deref(who) for _ in call(with_seam.ancestor, mint("tom"), who)) \
            == [mint("ann"), mint("bob"), mint("liz"), mint("pat")]
