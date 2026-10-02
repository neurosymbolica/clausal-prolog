"""A NON-splat dict-literal key that is a logic variable bound in the same
clause frame (``{K: V}``) must be dereferenced at construction time.

Before the fix the key reached dict construction as the Var object — the
``DictTerm`` branch of ``term_to_ast_expr`` (unlike the ``DictLiteral`` branch
fixed for the splat form) emitted the frame var bare — so the built dict was
keyed by the variable and every later ``get(OUT, <value>, _)`` missed, silently.
A never-bound key must raise a catchable instantiation error at call time; the
clause merely existing must not break module load.
"""

from __future__ import annotations

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load():
    return _load_module(
        "dict_nonsplat_var_key",
        os.path.join(os.path.dirname(__file__), "fixtures", "dict_nonsplat_var_key.seam"),
    )


def _one(mod, pred, *args):
    logic_mod = mod.__dict__["$module"]
    out = Var()
    for _ in call(pred, *args, out, module=logic_mod):
        return deref(out)
    return None


def test_nonsplat_same_frame_bound_var_key_reads_back():
    mod = _load()
    assert _one(mod, "nonsplat_var_key") == 20


def test_nonsplat_literal_key_control():
    mod = _load()
    assert _one(mod, "nonsplat_literal_key") == 20


def test_nonsplat_headarg_key_control():
    mod = _load()
    assert _one(mod, "nonsplat_headarg_key", "age", 20) == 20


def test_nonsplat_var_value_control():
    mod = _load()
    assert _one(mod, "nonsplat_var_value") == 20


def test_nonsplat_unbound_key_raises_catchable_at_call_time():
    # Module load already succeeded in _load(); the never-bound key must
    # surface as a catchable LogicException (instantiation_error), not a
    # silent miss and not a load-time crash.
    from clausal.logic.exceptions import LogicException

    mod = _load()
    with pytest.raises(LogicException, match="instantiation"):
        _one(mod, "nonsplat_unbound_key")
