"""``_find_pred_cls`` is ARITY-CHECKED on every leg, and its last leg is
symmetric with the no-row one (final review I1 + roborev L3, 2026-09-17).

The reroute of this site (P1 Task 3) replaced a class read with a row read on
two of its four legs and dropped the ``len(_fields) == arity`` check the
docstring's ARITY-CHECKED paragraph promises on the other two:

* the ROW-MATCHED leg (``candidate._row is named_row`` -> ``candidate``) hands
  back whatever class sits on that row, and a class can sit on a row of a
  DIFFERENT arity -- ``todo/dynamic-at-another-arity-moves-the-class-2026-09-17.md``
  is a live, pre-existing way to produce exactly that;
* the LAST leg answered ``None`` whenever neither the module's binding nor the
  head's own class was on the named row, where the no-row leg in the same
  function falls back to the arity-checked class read.

Both legs measured before the fix: the first returned ``d/1``'s class for
``('d', 2)`` (canonical, pre-P1, returns ``None``), the second returned
``None`` for a plain-Python-imported class the module can see.
"""
from __future__ import annotations

from clausal.import_hook import _load_module
from clausal.logic.builtins.database_ops import _find_pred_cls
from clausal.logic.predicate import (
    make_predicate, mint_predicate_handle, resolve_predicate_row,
)


def _write(tmp_path, name, src):
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    return p


def _load(tmp_path, name, src):
    return _load_module(name, str(_write(tmp_path, name, src))).__dict__["$module"]


# -- the row-matched leg is arity-checked (I1) -------------------------------


def test_a_class_sitting_on_another_aritys_row_is_not_returned_for_that_arity(
        tmp_path):
    """``-dynamic(d/2)`` beside ``d(1),`` USED TO move ``d/1``'s class onto
    the ``('d', 2)`` row (fixed 2026-09-24,
    ``todo/done/dynamic-at-another-arity-moves-the-class-2026-09-17.md``).
    The row-matched leg must still not hand a ONE-field class to a ``d/2``
    assert: the caller locks it, recompiles through it and builds terms with
    it.  The misplaced state is now built by hand so the guard stays tested.
    """
    mod = _load(tmp_path, "fpc_ar", "-dynamic(d/1)\n-dynamic(d/2)\nd(1),\n")
    md = mod.module_dict
    # After the W4b-2d flip the load binds ``d`` to its HANDLE, which has no
    # arity to be wrong about: both d/1 and d/2 are this module's predicates,
    # so the handle is the binding at each.
    handle = md["d"]
    assert handle == mint_predicate_handle(mod.db, "d"), handle
    assert _find_pred_cls("d", 1, md) == handle
    assert _find_pred_cls("d", 2, md) == handle
    # The class arm of the guard is still engine code; the misplaced class
    # is built by hand -- a ONE-field class on d/1's row, then moved onto
    # the ('d', 2) row -- and bound under the name.
    cls = make_predicate("d", ["x"])
    cls._bind_row(mod.db, "d", 1, authorized=True)
    assert cls._row.key == ("d", 1)
    cls._bind_row(mod.db, "d", 2, authorized=True)
    md["d"] = cls
    # the state this test is built on, pinned so the test cannot go vacuous
    assert len(cls._fields) == 1 and cls._row.key == ("d", 2)
    assert mod.db.row("d", 2) is cls._row
    assert _find_pred_cls("d", 2, md) is None
    # ... and the honest arity still resolves
    assert _find_pred_cls("d", 1, md) is cls


# -- the last leg is symmetric with the no-row leg (L3) ----------------------


def test_a_row_here_does_not_hide_a_class_bound_to_another_databases_row(
        tmp_path, monkeypatch):
    """Row exists here, the module's binding reads ANOTHER database's row,
    and the head is generic (no class of its own).  The no-row leg would fall
    back to the arity-checked class read; this leg answered ``None``, which
    sends the caller down a cross-module write path for a predicate the
    module can plainly see.
    """
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path, "fpc_ex", "-module(fpc_ex, [qq(X)])\n\nqq(1),\n")
    exporter = _load_module("fpc_ex", str(tmp_path / "fpc_ex.clausal"))
    exported = exporter.__dict__["qq"]      # a handle, post-flip
    exporter_row = resolve_predicate_row(
        exported, arity=1, db=exporter.__dict__["$module"].db)
    assert exporter_row is not None

    # A local -dynamic mints a row for ('qq', 1) here ...
    mod = _load(tmp_path, "fpc_im", "-dynamic(qq/1)\n")
    assert mod.db.row("qq", 1) is not None
    # ... and then a plain Python import rebinds the NAME to the exporter's
    # binding, whose row belongs to the exporter's Database.
    mod.module_dict["qq"] = exported
    assert resolve_predicate_row(exported, arity=1, db=mod.db) is exporter_row
    assert exporter_row is not mod.db.row("qq", 1)

    assert _find_pred_cls("qq", 1, mod.module_dict) == exported
    # still arity-checked on that leg
    assert _find_pred_cls("qq", 2, mod.module_dict) is None
