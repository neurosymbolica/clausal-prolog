"""`qualify_mangled_goal` must decide "is this a Clausal module" -- not "is
this ANY loaded Python module" (todo:
`todo/qualify-mangled-goal-tests-only-sys-modules-2026-09-23.md`, W4b-2).

`clausal/logic/cells.py:qualify_mangled_goal` used to ask only
``module_name in sys.modules``, which is true of every imported Python
module (``json``, ``csv``, ``types``, ...), not just ones Clausal loaded.  A
mangled atom whose module half happens to collide with an ordinary Python
import would get auto-qualified into that module and then fail with an
implementation-specific, wrongly-worded error
("json defines no predicates of its own. -> define whatever/1 in json").

Scope (deliberately narrow): fix the VALIDITY TEST only.  The error term/
shape a genuine mistake gets (``existence_error(procedure, ..)`` vs
``existence_error(module, ..)``) is an open, unrelated ruling -- not
touched here.
"""
import os

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import mangle
from clausal.logic.cells import qualify_mangled_goal
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def test_a_mangled_atom_over_an_ordinary_python_module_does_not_qualify():
    """`json` is a real, loaded Python module Clausal never touched.  A
    mangled atom whose module half is "json" must come back UNTOUCHED, not
    qualified into it."""
    import json  # noqa: F401 -- just needs to be a loaded, non-Clausal module

    cell = (mangle("json", "whatever"), 1)
    assert qualify_mangled_goal(cell) == cell, (
        "a plain Python module (no Clausal $module marker) must not be "
        "treated as a predicate-handle target"
    )


def test_a_mangled_atom_over_an_ordinary_python_module_is_not_swallowed_by_solve():
    """End to end: `solve` must not report the nonsensical "define
    whatever/1 in json" advice -- that message is the SYMPTOM of wrongly
    qualifying into `json`, and it must be gone once the module-half test is
    correct (whatever the eventual error term looks like -- that shape is
    out of scope here)."""
    import json  # noqa: F401

    with pytest.raises(Exception) as info:
        list(solve((mangle("json", "whatever"), 1)))
    assert "json defines no predicates of its own" not in str(info.value)
    assert "define whatever/1 in json" not in str(info.value)


def test_a_mangled_atom_over_a_real_loaded_clausal_module_still_qualifies():
    """The positive case the fix must not break: a handle whose module half
    IS a loaded `.clausal` module (declares `holds/1` among others) still
    qualifies to the `(":", module, goal)` form the engine resolves."""
    mod_name = "tests.fixtures.hide_owner"
    _load_module(mod_name, _fixture_path("hide_owner.clausal"))

    cell = (mangle(mod_name, "holds"), 1)
    qualified = qualify_mangled_goal(cell)
    assert qualified == (":", mod_name, ("holds", 1))

    X = Var()
    got = sorted(deref(X) for _ in solve((mangle(mod_name, "holds"), X)))
    assert got, "the qualified goal must actually resolve against the module's db"
