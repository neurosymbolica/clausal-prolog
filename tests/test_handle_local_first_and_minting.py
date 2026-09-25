"""Rulings Q0 and X3 (2026-09-24): how a module-qualified predicate HANDLE
(a mangled atom) finds its database, and how one is minted.

Q0: the ``.clausal`` test runner pops every module it loads from
``sys.modules``, and ``_db_for_module_name`` looked only there -- so a handle
to a test module's own predicate resolved to nothing in 43 of 46 measured
descents.  Every era-agnostic resolver now takes the CALLER's ``db=`` and
resolves a handle naming that database's own module there first.

X3: a handle is minted from the DATABASE (``mint_predicate_handle``), never
from a class's ``__module__``, which names the minter for a
``make_predicate`` class.
"""

from __future__ import annotations

import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import demangle, mangle
from clausal.logic.database import Database
from clausal.logic.predicate import (
    _HANDLE_OWNERS, is_declared_predicate, is_declared_predicate_name, mint_predicate_handle, predicate_arities_for, predicate_binding_name,
    resolve_predicate_row,
)
from tests.predicate_api_support import class_arm_predicate


def _load_popped(tmp_path, name, source):
    """Load a module, then drop it from ``sys.modules`` as the runner does."""
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(source).lstrip())
    sys.modules.pop(name, None)
    module = _load_module(name, str(path))
    sys.modules.pop(name, None)
    # Isolate the caller's-db HINT from the handle-owner registry (the
    # cross-module remainder, test_handle_owner_registry.py), which would
    # otherwise answer for the popped module and hide a dropped hint.
    _HANDLE_OWNERS.pop(name, None)
    return module.__dict__["$module"].db


def test_a_local_handle_resolves_in_the_caller_s_db_after_a_pop(tmp_path):
    db = _load_popped(tmp_path, "q0_local", """
        q0_p(1),
        q0_p(2),
    """)
    handle = mint_predicate_handle(db, "q0_p")
    assert "q0_local" not in sys.modules
    row = db.row("q0_p", 1)
    assert row is not None and row.clauses, "nothing to resolve: no control"

    # Without the hint (registry isolated): the popped owner is unreachable.
    assert resolve_predicate_row(handle, arity=1) is None
    # With the caller's db: every resolver answers.
    assert resolve_predicate_row(handle, arity=1, db=db) is row
    assert is_declared_predicate(handle, arity=1, db=db)
    assert not is_declared_predicate(handle, arity=2, db=db)
    assert is_declared_predicate_name(handle, db=db)
    assert predicate_binding_name(handle, db=db) == "q0_p"
    assert predicate_arities_for(handle, db=db) == {1}


def test_a_handle_to_another_module_is_not_captured_by_the_caller(tmp_path):
    """The hint only short-circuits the caller's OWN module: a foreign
    handle still resolves to its owner, even when the caller defines the
    same functor."""
    here = _load_popped(tmp_path, "q0_here", "q0_same(1),\n")
    (tmp_path / "q0_there.clausal").write_text("q0_same(2),\n")
    sys.modules.pop("q0_there", None)
    there = _load_module("q0_there", str(tmp_path / "q0_there.clausal"))
    try:
        there_db = there.__dict__["$module"].db
        foreign = mint_predicate_handle(there_db, "q0_same")
        assert resolve_predicate_row(foreign, arity=1, db=here) \
            is there_db.row("q0_same", 1)
        assert resolve_predicate_row(foreign, arity=1, db=here) \
            is not here.row("q0_same", 1)
    finally:
        sys.modules.pop("q0_there", None)


def test_a_handle_is_minted_from_the_database(tmp_path):
    db = _load_popped(tmp_path, "q0_mint", "q0_m(1),\n")
    handle = mint_predicate_handle(db, "q0_m")
    assert demangle(handle) == ("q0_mint", "q0_m")
    # The shape X3 forbids: a make_predicate class names its MINTER.
    cls = class_arm_predicate("q0_m", ["x"])
    wrong = mangle(cls.__module__, "q0_m")
    assert resolve_predicate_row(wrong, arity=1, db=db) is None


def test_a_database_with_no_module_cannot_mint():
    with pytest.raises(ValueError, match="belongs to no module"):
        mint_predicate_handle(Database(), "q0_orphan")


def test_a_local_handle_to_an_undefined_functor_answers_nothing(tmp_path):
    """The short-circuit does not fall back to sys.modules: a local handle
    naming nothing here is not a predicate."""
    db = _load_popped(tmp_path, "q0_undef", "q0_d(1),\n")
    handle = mangle("q0_undef", "q0_nothing")
    assert resolve_predicate_row(handle, arity=1, db=db) is None
    assert not is_declared_predicate(handle, arity=1, db=db)
    assert not is_declared_predicate_name(handle, db=db)
    assert predicate_binding_name(handle, db=db) is None
    assert predicate_arities_for(handle, db=db) == set()


def test_the_class_arm_uses_the_hint_too(tmp_path):
    """A class whose owner was popped: with the hint its owner's defined
    arities are found, exactly as the mangled arm finds them."""
    path = tmp_path / "q0_cls.clausal"
    path.write_text("-dynamic(q0_two/1, q0_two/2)\n\nq0_other(1),\n")
    sys.modules.pop("q0_cls", None)
    module = _load_module("q0_cls", str(path))
    sys.modules.pop("q0_cls", None)
    _HANDLE_OWNERS.pop("q0_cls", None)      # isolate the hint (see above)
    db = module.__dict__["$module"].db
    handle = mint_predicate_handle(db, "q0_two")
    # After the W4b-2d flip the load binds the HANDLE; the class arm is still
    # engine code, so its class -- one the popped module owns -- is built by
    # hand, exactly the shape the load used to bind.
    assert module.__dict__["q0_two"] == handle
    cls = class_arm_predicate("q0_two", ["x"])
    cls.__module__ = "q0_cls"
    assert cls.__module__ == "q0_cls"
    assert predicate_arities_for(handle, db=db) == {1, 2}
    assert predicate_arities_for(cls, db=db) == {1, 2}
    assert predicate_arities_for(cls) == {len(cls._fields)}   # popped, no hint


def test_a_string_named_database_does_not_capture_a_loaded_module_s_handle(
        tmp_path):
    loaded = _load_popped(tmp_path, "q0_real", "q0_r(1),\n")
    sys.modules["q0_real"] = type(sys)("q0_real")
    sys.modules["q0_real"].__dict__["$module"] = type(
        "LM", (), {"db": loaded})()
    try:
        handle = mint_predicate_handle(loaded, "q0_r")
        impostor = Database("q0_real")      # module_name() == "q0_real"
        assert resolve_predicate_row(handle, arity=1, db=impostor) \
            is loaded.row("q0_r", 1)
    finally:
        sys.modules.pop("q0_real", None)
