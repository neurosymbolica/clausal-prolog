"""Ruling Q0 wired at the consumers (todo/q0-db-hint-must-be-wired-at-each-
consumer-2026-09-24.md).

The era-agnostic resolvers answer a module-qualified predicate HANDLE whose
module the ``.clausal`` test runner popped from ``sys.modules`` only when the
CALLER's database is passed as ``db=``.  No binding is a handle before the
flip, so nothing here changes behaviour today; these tests plant a handle by
hand (minted from the database, ruling X3) into a popped module and check,
one test per consumer family, that the site now passes its db.  Each asserts
the no-hint answer first -- so dropping the hint at the site fails the test,
and the control proves the handle really is unreachable without it.
"""

from __future__ import annotations

import sys
import textwrap

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import (
    is_declared_predicate_name, mint_predicate_handle,
)


def _load_popped(tmp_path, name, source):
    """Load a module, then drop it from ``sys.modules`` as the runner does;
    return ``(module, db, handle)`` for its predicate ``<name>_p/1``."""
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    sys.modules.pop(name, None)
    module = _load_module(name, str(path))
    sys.modules.pop(name, None)
    db = module.__dict__["$module"].db
    handle = mint_predicate_handle(db, f"{name}_p")
    assert name not in sys.modules
    # Control: without the hint the popped owner is unreachable.
    assert not is_declared_predicate_name(handle)
    assert is_declared_predicate_name(handle, db=db)
    return module, db, handle


# ── load channel (compiler_v2) ───────────────────────────────────────────────


def test_load_channel_import_origins_keeps_a_local_handle(tmp_path):
    from clausal.logic.compiler_v2 import (
        ImportFromItem, _import_from_origins, _imported_binding_by_canonical_name,
    )
    module, db, handle = _load_popped(tmp_path, "q0c_load", "q0c_load_p(1),\n")
    md = module.__dict__
    md["q0c_alias"] = handle
    item = ImportFromItem(module="somewhere", names=["q0c_alias"])
    origins = _import_from_origins([item], md, db=db)
    # The handle is a declared predicate, so it is kept AND indexed under its
    # own name too -- without the hint it would read as "not a predicate".
    assert origins["q0c_alias"] == ("somewhere", handle)
    assert origins["q0c_load_p"] == ("somewhere", handle)
    # And the foreignness check sees it as LOCAL (its row is this db's).
    assert _imported_binding_by_canonical_name(origins, db, "q0c_load_p", 1) is None


def test_load_channel_meta_interpreter_binding_resolves_locally(tmp_path):
    from clausal.logic.compiler_v2 import _meta_interpreter_row
    module, db, handle = _load_popped(tmp_path, "q0c_mi", "q0c_mi_p(1),\n")
    row = db.row("q0c_mi_p", 1)
    # Bound under a name with no row of its own, so arm 3 (the binding) runs.
    md = dict(module.__dict__, q0c_mi_alias=handle)
    assert _meta_interpreter_row(db, md, "q0c_mi_alias",
                                 refuse_ambiguous=True) is row


# ── mutation gate (Database._write_rows, through=) ───────────────────────────


def test_mutation_gate_through_a_local_handle_widens_to_its_row(tmp_path):
    _module, db, handle = _load_popped(
        tmp_path, "q0c_gate", "q0c_gate_p(1),\nq0c_gate_q(1),\n")
    rows = db._write_rows("q0c_gate_q", 1, through=handle, create=False)
    assert db.row("q0c_gate_p", 1) in rows
    assert len(rows) == 2


# ── compile-time globals (globals_env, arg_index) ────────────────────────────


def test_compile_time_call_target_and_shadowing_use_the_db(tmp_path):
    from clausal.logic.compiler.globals_env import (
        _atom_shadows_row, _is_call_target,
    )
    _module, db, handle = _load_popped(tmp_path, "q0c_ge", "q0c_ge_p(1),\n")
    assert not _is_call_target(handle, 1)
    assert _is_call_target(handle, 1, db)
    assert not _is_call_target(handle, 2, db)
    # A handle declared at THIS arity is the target, never shadowed.
    assert not _atom_shadows_row(handle, db, "q0c_ge_p", 1)


def test_compile_time_hint_row_reads_a_local_handle(tmp_path):
    from clausal.logic.compiler.arg_index import hint_row
    _module, db, handle = _load_popped(tmp_path, "q0c_hr", "q0c_hr_p(1),\n")
    row = db.row("q0c_hr_p", 1)
    assert row.locked
    # Keyed under a spelling with no row, so the binding fallback runs.
    assert hint_row(db, "q0c_hr_alias", 1, {"q0c_hr_alias": handle}) is row


def test_compile_time_dispatch_cache_bakes_a_local_handle(tmp_path):
    from clausal.logic.compiler.globals_env import _inject_resolved_targets
    _module, db, handle = _load_popped(tmp_path, "q0c_bk", "q0c_bk_p(1),\n")
    row = db.row("q0c_bk_p", 1)
    assert row.locked and row.dispatch_fn is not None
    base = {}
    _inject_resolved_targets({("q0c_bk_alias", 1)}, base, db,
                             {"q0c_bk_alias": handle})
    assert base.get("q0c_bk_alias") == handle
    assert any(v is row.dispatch_fn for v in base.values()), sorted(base)


def test_compile_time_cell_signature_lets_a_predicate_binding_win(tmp_path):
    """R6: the BINDING SHAPE decides data-vs-predicate.  A name that has a
    data signature but is bound to a predicate is not data -- which needs
    the handle SEEN as a predicate; unseen, it is an unknown mangled str and
    the data signature wins."""
    from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY
    from clausal.logic.compiler.terms_to_ast import cell_signature_for_name
    module, _db, handle = _load_popped(tmp_path, "q0c_ct", "q0c_ct_p(1),\n")
    ns = dict(module.__dict__, q0c_ct_alias=handle)
    ns[FUNCTOR_SIGNATURES_KEY] = {"q0c_ct_alias": ("x",)}
    assert cell_signature_for_name("q0c_ct_alias", ns) is None
    # Control: the same namespace without the $module (so no hint).
    ns_no_db = {k: v for k, v in ns.items() if k != "$module"}
    unseen = cell_signature_for_name("q0c_ct_alias", ns_no_db)
    assert unseen is not None and unseen[1] == ("x",)


# ── runtime call funnels (solve.call, time_goal, phrase) ─────────────────────


def test_runtime_call_phase5_routes_a_local_handle(tmp_path, monkeypatch):
    import clausal.logic.solve as solve_mod
    module, db, handle = _load_popped(tmp_path, "q0c_call", "q0c_call_p(1),\n")
    seen = []

    def _spy(obj, arity):
        seen.append((obj, arity))
        return db.get_dispatch("q0c_call_p", 1)
    monkeypatch.setattr(solve_mod, "_dispatch_at", _spy)
    module.__dict__["q0c_call_alias"] = handle
    # Drive only Phase 5's gate: it must hand the handle to _dispatch_at.
    try:
        next(solve_mod.call("q0c_call_alias", 1,
                            module=module.__dict__["$module"]), None)
    except Exception:  # noqa: BLE001 — only the routing is under test
        pass
    assert (handle, 1) in seen


def test_runtime_time_goal_gate_routes_a_local_handle(tmp_path, monkeypatch):
    import clausal.logic.builtins.control as control
    _module, db, handle = _load_popped(tmp_path, "q0c_tg", "q0c_tg_p(1),\n")
    sentinel = object()
    monkeypatch.setattr(control, "_ensure_trampoline_dispatch",
                        lambda goal, arity: sentinel)
    assert control._goal_dispatch_and_args(handle, db=db) == (sentinel, ())


def test_runtime_phrase_gate_routes_a_local_handle(tmp_path, monkeypatch):
    import clausal.logic.builtins.dcg as dcg
    _module, db, handle = _load_popped(tmp_path, "q0c_ph", "q0c_ph_p(1),\n")
    seen = []

    class _Stop(Exception):
        pass

    def _spy(obj, arity):
        seen.append((obj, arity))
        raise _Stop
    monkeypatch.setattr(dcg, "_dispatch_at", _spy)
    for fn, args in ((dcg._phrase__2, (handle, [])),
                     (dcg._phrase__3, (handle, [], []))):
        try:
            gen = fn(db, None, None, None, None, *args, None)
            next(iter(gen))
        except _Stop:
            pass
    assert seen == [(handle, 2), (handle, 2)]


# ── diagnostics (import_diagnostics, predicate_diagnostics) ──────────────────


def test_diagnostics_list_a_local_handle(tmp_path):
    from clausal.import_diagnostics import _defined_names
    from clausal.predicate_diagnostics import _local_entries
    module, db, handle = _load_popped(tmp_path, "q0c_dg", "q0c_dg_p(1),\n")
    module.__dict__["q0c_dg_alias"] = handle
    names = {e if isinstance(e, str) else e[0] for e in _defined_names(module)}
    assert "q0c_dg_alias" in names
    entries = _local_entries(module.__dict__, "q0c_dg", db)
    assert ("q0c_dg_alias", 1) in entries


def test_a_same_named_placeholder_db_captures_the_handle_and_answers_nothing(
        tmp_path):
    """Why the load channel threads ``compile_module``'s LOCAL db rather than
    reading ``module_dict["$module"].db``: during the load that entry is the
    import hook's PLACEHOLDER module, whose Database shares the module dict --
    so it has the same ``module_name()``, captures every local handle, and
    answers from an empty store."""
    from clausal.logic.database import Database
    module, db, handle = _load_popped(tmp_path, "q0c_ph0", "q0c_ph0_p(1),\n")
    placeholder = Database(module.__dict__)
    assert placeholder.module_name() == db.module_name()
    assert not is_declared_predicate_name(handle, db=placeholder)
