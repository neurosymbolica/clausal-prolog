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
    _HANDLE_OWNERS, is_declared_predicate_name, mint_predicate_handle,
)


def _load_popped(tmp_path, name, source):
    """Load a module, then drop it from ``sys.modules`` as the runner does;
    return ``(module, db, handle)`` for its predicate ``<name>_p/1``."""
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    sys.modules.pop(name, None)
    module = _load_module(name, str(path))
    sys.modules.pop(name, None)
    # Isolate the HINT: the handle-owner registry (the cross-module
    # remainder, test_handle_owner_registry.py) would otherwise answer for
    # the popped module too and make the control below vacuous.
    _HANDLE_OWNERS.pop(name, None)
    db = module.__dict__["$module"].db
    handle = mint_predicate_handle(db, f"{name}_p")
    assert name not in sys.modules
    # Control: without the hint (and the registry) the popped owner is
    # unreachable.
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


def test_load_channel_hint_at_compile_module_s_own_point(tmp_path,
                                                        monkeypatch):
    """LOW 3: the tests above run the load-channel helpers AFTER the load,
    against the finished db.  This one runs ``_import_from_origins`` where
    ``compile_module`` really calls it -- step 3c, BEFORE step 4 writes a
    clause -- with the local ``db`` compile_module threads.  There the
    predicate is known only as a DECLARATION (the ``-module`` export), there
    is no row yet, and ``$module`` is still the placeholder: the no-hint
    route (``sys.modules`` -> placeholder) and the placeholder db both miss
    the handle; only compile_module's own db resolves it.  Covers the
    export-declared case; a predicate with neither export nor directive is
    unknown to the db at step 3c in any era."""
    import clausal.logic.compiler_v2 as cv
    from clausal.logic.compiler_v2 import ImportFromItem
    name = "q0c_real"
    path = tmp_path / f"{name}.clausal"
    path.write_text(f"-module({name}, [{name}_p/1])\n{name}_p(1),\n")
    orig = cv._import_from_origins
    seen = {}

    def spy(items, md, db=None):
        handle = mint_predicate_handle(db, f"{name}_p")
        seen["placeholder"] = md["$module"].db is not db
        seen["row"] = db.row(f"{name}_p", 1)
        seen["no_hint"] = is_declared_predicate_name(handle)
        seen["placeholder_hint"] = is_declared_predicate_name(
            handle, db=md["$module"].db)
        md[f"{name}_alias"] = handle
        extra = ImportFromItem(module="elsewhere", names=[f"{name}_alias"])
        seen["origins"] = orig([*items, extra], md, db=db)
        del md[f"{name}_alias"]
        return orig(items, md, db=db)
    monkeypatch.setattr(cv, "_import_from_origins", spy)
    sys.modules.pop(name, None)
    try:
        _load_module(name, str(path))
    finally:
        sys.modules.pop(name, None)
    assert seen["placeholder"] and seen["row"] is None
    assert not seen["no_hint"] and not seen["placeholder_hint"]
    handle = seen["origins"][f"{name}_alias"][1]
    assert handle is not None
    assert seen["origins"][f"{name}_p"] == ("elsewhere", handle)


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
#
# End to end: the gate accepts the popped module's local handle AND
# ``_dispatch_at``'s handle arm resolves it in the caller's db (Q0) -- before
# the hint reached ``_dispatch_at``/``qualify_mangled_goal`` the gate let the
# handle through and the call then failed, since ``resolve_module`` looks
# only in ``sys.modules``.

_RT_SRC = """\
-module({name}, [])
{name}_p(1, 10),
{name}_p(2, 20),
greeting >> (["hi"])
go <- (1 > 0)
"""


def _popped_runtime(tmp_path, name):
    module, db, handle = _load_popped(tmp_path, name, _RT_SRC.format(name=name))
    lm = module.__dict__["$module"]
    greeting = mint_predicate_handle(db, "greeting")
    go = mint_predicate_handle(db, "go")
    # Control: no hint, no resolution -- the handles are unreachable.
    assert not is_declared_predicate_name(greeting)
    assert not is_declared_predicate_name(go)
    return lm, handle, greeting, go


def test_runtime_call_phase5_runs_a_popped_local_handle(tmp_path):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    lm, handle, _greeting, _go = _popped_runtime(tmp_path, "q0c_rtc")
    lm.module_dict["q0c_rtc_alias"] = handle
    x, y = Var(), Var()
    got = [(deref(x), deref(y))
           for _ in call("q0c_rtc_alias", x, y, module=lm)]
    assert got == [(1, 10), (2, 20)]


def test_runtime_phrase_runs_a_popped_local_handle(tmp_path):
    from clausal.logic.atoms import mint
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    lm, _handle, greeting, _go = _popped_runtime(tmp_path, "q0c_rtp")
    assert len(list(call("phrase", greeting, [mint("hi")], module=lm))) == 1
    assert list(call("phrase", greeting, [mint("bye")], module=lm)) == []
    rest = Var()
    got = [deref(rest) for _ in call(
        "phrase", greeting, [mint("hi"), mint("x")], rest, module=lm)]
    assert got == [[mint("x")]]


def test_runtime_time_goal_runs_a_popped_local_handle(tmp_path, capsys):
    from clausal.logic.solve import call
    lm, _handle, _greeting, go = _popped_runtime(tmp_path, "q0c_rtt")
    assert len(list(call("time_goal", go, module=lm))) == 1
    capsys.readouterr()   # time_goal's timing line


def test_dispatch_at_resolves_a_popped_local_handle_only_with_the_hint(
        tmp_path):
    from clausal.logic.cells import qualify_mangled_goal
    from clausal.logic.predicate import _dispatch_at
    lm, handle, _greeting, _go = _popped_runtime(tmp_path, "q0c_rtd")
    assert qualify_mangled_goal(handle) is handle          # unreachable
    assert qualify_mangled_goal(handle, db=lm.db) is not handle
    assert _dispatch_at(handle, 2, lm.db) is lm.db.get_dispatch("q0c_rtd_p", 2)


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


def test_a_db_like_shim_is_no_hint_not_a_crash(tmp_path):
    """The tolerance lives in the resolvers (``_hint_db``), so a caller holding
    the compile-time ``_GlobalsDb`` shim (no ``module_dict``) passes it
    unguarded."""
    from clausal.logic.compiler.globals_env import _GlobalsDb
    from clausal.logic.predicate import resolve_predicate_row
    _module, db, handle = _load_popped(tmp_path, "q0c_shim", "q0c_shim_p(1),\n")
    shim = _GlobalsDb({})
    assert not hasattr(shim, "module_dict")
    assert resolve_predicate_row(handle, arity=1, db=shim) is None
    assert not is_declared_predicate_name(handle, db=shim)
