"""Ruling Q0 (operator, final, 2026-09-24): a predicate HANDLE resolves in the
CALLER's db first, and a registry answers ONLY the cross-module remainder --
an owner module the ``.clausal`` test runner popped from ``sys.modules``.

The registry is HANDLE-ONLY.  A module name a user WRITES (``M:G``, a
``module=`` designator) still goes through ``solve.resolve_module``, which is
lookup-only in ``sys.modules`` (``test_resolution_never_imports``), so a
popped module never becomes reachable by a name somebody typed.

Name reuse (measured 24 of 579 ``load_clausal_module`` calls reused a module
name while an earlier module under it was alive): resolved BY IDENTITY when
the caller imported one of them, and REFUSED (``AmbiguousHandleOwnerError``)
when nothing says which -- never silently the wrong database.
"""

from __future__ import annotations

import gc
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import predicate as predmod
from clausal.logic.atoms import mangle
from clausal.logic.cells import qualify_mangled_goal
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import (
    AmbiguousHandleOwnerError, _dispatch_at, _field_names_for_name,
    is_declared_predicate, mint_predicate_handle, predicate_arities_for,
    resolve_predicate_row,
)
from clausal.logic.solve import resolve_module, solve
from clausal.logic.variables import Var, deref


def _write(tmp_path, name, source):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    return str(path)


def _load_popped(tmp_path, name, source):
    """Load a module, then drop it from ``sys.modules`` as the runner does.
    Returns the MODULE (the caller keeps it alive or drops it)."""
    path = _write(tmp_path, name, source)
    sys.modules.pop(name, None)
    module = _load_module(name, path)
    sys.modules.pop(name, None)
    return module


def _db(module):
    return module.__dict__["$module"].db


def _answers(goal, module=None):
    x = Var()
    if type(goal) is tuple:
        goal = goal + (x,)
    else:
        goal = (goal, x)
    return sorted(deref(x) for _ in solve(goal, module=module))


# ── cross-module popped owner resolves via the handle ─────────────────────

def test_a_cross_module_popped_owner_resolves_through_its_handle(tmp_path):
    owner = _load_popped(tmp_path, "q0r_owner", "q0r_p(1),\nq0r_p(2),\n")
    caller = _load_popped(tmp_path, "q0r_caller", "q0r_c(1),\n")
    owner_db, caller_db = _db(owner), _db(caller)
    handle = mint_predicate_handle(owner_db, "q0r_p")
    assert "q0r_owner" not in sys.modules
    row = owner_db.row("q0r_p", 1)
    assert row is not None and row.clauses, "no control: nothing to resolve"

    # Resolvers: the caller's hint does not capture it, the registry answers.
    assert resolve_predicate_row(handle, arity=1, db=caller_db) is row
    assert resolve_predicate_row(handle, arity=1) is row
    assert is_declared_predicate(handle, arity=1, db=caller_db)
    # Runtime (R2): the dispatch funnel and a goal built from the handle.
    assert _dispatch_at(handle, 1, caller_db) is owner_db.get_dispatch(
        "q0r_p", 1)
    assert _answers(handle) == [1, 2]


def test_call_n_from_a_popped_caller_reaches_a_popped_owner(tmp_path):
    """The dry run's R2 shape: the ``call/N`` funnel, running for one popped
    module (its db is the calling db), is handed a handle whose owner is
    ANOTHER popped module -- which defines no predicate of that name in the
    caller, and the caller's same-named predicate must not capture it."""
    from clausal.logic.builtins.higher_order import _resolve_named_goal
    owner = _load_popped(tmp_path, "q0r_own2", "q0r_q(7),\nq0r_q(8),\n")
    caller = _load_popped(tmp_path, "q0r_call2", "q0r_q(9),\n")
    handle = mint_predicate_handle(_db(owner), "q0r_q")
    x = Var()
    resolved = _resolve_named_goal(_db(caller), handle, (x,), "call/N")
    assert resolved is not None
    dispatch, args = resolved
    assert dispatch is _db(owner).get_dispatch("q0r_q", 1)
    assert dispatch is not _db(caller).get_dispatch("q0r_q", 1)


def test_a_qualified_goal_from_a_popped_handle_carries_the_module_object(
        tmp_path):
    """The designator a handle's qualified goal carries is the Module
    OBJECT when ``sys.modules`` cannot answer the name -- so
    ``resolve_module``'s name path is never asked about a popped module.
    A loaded (not popped) owner keeps the pure-data dotted name."""
    owner = _load_popped(tmp_path, "q0r_obj", "q0r_o(1),\n")
    handle = mint_predicate_handle(_db(owner), "q0r_o")
    q = qualify_mangled_goal((handle, 1))
    assert q[0] == ":" and q[2] == ("q0r_o", 1)
    assert q[1] is owner.__dict__["$module"]
    sys.modules["q0r_obj"] = owner
    try:
        assert qualify_mangled_goal((handle, 1)) == (":", "q0r_obj",
                                                     ("q0r_o", 1))
    finally:
        sys.modules.pop("q0r_obj", None)


# ── a user-written M:G never resolves through the registry ────────────────

def test_a_user_written_qualification_of_a_popped_module_does_not_resolve(
        tmp_path):
    owner = _load_popped(tmp_path, "q0r_user", "q0r_u(1),\n")
    handle = mint_predicate_handle(_db(owner), "q0r_u")
    assert _answers(handle) == [1], "control: the HANDLE does resolve"
    assert predmod._live_handle_owners("q0r_user") == [_db(owner)]

    with pytest.raises(LogicException, match="existence_error"):
        resolve_module("q0r_user")
    x = Var()
    with pytest.raises(LogicException, match="existence_error"):
        list(solve((":", "q0r_user", ("q0r_u", x))))
    with pytest.raises(LogicException, match="existence_error"):
        list(solve(("q0r_u", x), module="q0r_user"))
    assert "q0r_user" not in sys.modules, "resolution must never import"


# ── name reuse ────────────────────────────────────────────────────────────

def test_two_live_owners_under_one_name_are_refused_not_guessed(tmp_path):
    first = _load_popped(tmp_path, "q0r_reuse", "q0r_r(1),\n")
    second = _load_popped(tmp_path, "q0r_reuse", "q0r_r(2),\n")
    assert _db(first) is not _db(second)
    handle = mangle("q0r_reuse", "q0r_r")
    with pytest.raises(AmbiguousHandleOwnerError, match="q0r_reuse"):
        resolve_predicate_row(handle, arity=1)
    with pytest.raises(AmbiguousHandleOwnerError):
        qualify_mangled_goal((handle, 1))
    # A caller that IS one of them answers locally, with no ambiguity --
    # and ``_field_names_for_name`` honours that db too.
    for mod in (first, second):
        db = _db(mod)
        assert resolve_predicate_row(handle, arity=1, db=db) \
            is db.row("q0r_r", 1)
        assert _field_names_for_name(handle, 1, db, None) \
            == db.signature_for("q0r_r", 1)
    del first
    gc.collect()
    # One survivor: no longer ambiguous.
    assert resolve_predicate_row(handle, arity=1) is _db(second).row(
        "q0r_r", 1)


def test_an_importer_resolves_the_owner_it_imported_by_identity(tmp_path):
    """The owner is replaced under the same name AFTER the importer loaded:
    the importer's handle means the database it imported, by identity --
    ahead of both ``sys.modules`` and the registry."""
    _write(tmp_path, "q0r_src", "-module(q0r_src, [q0r_s/1])\n\nq0r_s(1),\n")
    sys.path.insert(0, str(tmp_path))
    try:
        sys.modules.pop("q0r_src", None)
        original = _load_module("q0r_src", str(tmp_path / "q0r_src.clausal"))
        importer = _load_popped(tmp_path, "q0r_imp", """
            -import_from(q0r_src, [q0r_s])
            q0r_i(X) <- q0r_s(X)
        """)
        imp_db = _db(importer)
        assert imp_db.adopted_owner_dbs("q0r_src") == [_db(original)]
        # A new module takes the name, in sys.modules; the original lives.
        _write(tmp_path, "q0r_src", "-module(q0r_src, [q0r_s/1])\n\nq0r_s(2),\n")
        sys.modules.pop("q0r_src", None)
        replacement = _load_module("q0r_src",
                                   str(tmp_path / "q0r_src.clausal"))
        assert sys.modules["q0r_src"] is replacement
        handle = mangle("q0r_src", "q0r_s")
        assert resolve_predicate_row(handle, arity=1, db=imp_db) \
            is _db(original).row("q0r_s", 1)
        # No hint: sys.modules answers, as it always has.
        assert resolve_predicate_row(handle, arity=1) \
            is _db(replacement).row("q0r_s", 1)
        # Popped too: the registry alone cannot tell them apart.
        sys.modules.pop("q0r_src", None)
        with pytest.raises(AmbiguousHandleOwnerError):
            resolve_predicate_row(handle, arity=1)
        assert resolve_predicate_row(handle, arity=1, db=imp_db) \
            is _db(original).row("q0r_s", 1)
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("q0r_src", None)


# ── weak cleanup ──────────────────────────────────────────────────────────

def test_a_dropped_module_leaves_no_registry_entry(tmp_path):
    module = _load_popped(tmp_path, "q0r_weak", "q0r_w(1),\n")
    handle = mint_predicate_handle(_db(module), "q0r_w")
    assert resolve_predicate_row(handle, arity=1) is not None
    assert "q0r_weak" in predmod._HANDLE_OWNERS
    del module
    gc.collect()
    assert "q0r_weak" not in predmod._HANDLE_OWNERS
    assert resolve_predicate_row(handle, arity=1) is None


# ── both eras ─────────────────────────────────────────────────────────────

def test_class_and_handle_agree_for_a_popped_owner_with_no_hint(tmp_path):
    """A class binding and the handle minted for it (``mint_predicate_handle``)
    answer the same with no caller db: the class arm's owner lookup is the
    handle rule too."""
    module = _load_popped(tmp_path, "q0r_eras",
                          "-dynamic(q0r_e/1, q0r_e/2)\n\nq0r_x(1),\n")
    db = _db(module)
    cls = module.__dict__["q0r_e"]
    handle = mint_predicate_handle(db, "q0r_e")
    assert predicate_arities_for(handle) == {1, 2}
    assert predicate_arities_for(cls) == {1, 2}
    assert predicate_arities_for(handle, db=db) == predicate_arities_for(
        cls, db=db) == {1, 2}
