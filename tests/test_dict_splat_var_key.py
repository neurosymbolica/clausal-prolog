"""A splat dict-literal key that is a logic variable bound in the same clause
frame (``{**OLD, K: V}``) must be dereferenced at construction time.

Before the fix the key reached dict construction as the Var object, so the
built dict was keyed by the variable and every later ``get(OUT, <value>, _)``
missed.  ``$dict_key`` now derefs the computed key.  (The domains hit this via
their ``what_if`` predicates, ``{**PROFILE, KEY: VALUE}``.)
"""

from __future__ import annotations

import os

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _load():
    return _load_module(
        "dict_splat_var_key",
        os.path.join(os.path.dirname(__file__), "fixtures", "dict_splat_var_key.clausal"),
    )


def _one(mod, pred, *args):
    logic_mod = mod.__dict__["$module"]
    out = Var()
    for _ in call(pred, *args, out, module=logic_mod):
        return deref(out)
    return None


def test_splat_same_frame_bound_var_key_reads_back():
    mod = _load()
    assert _one(mod, "splat_var_key") == 20


def test_splat_literal_key_control():
    mod = _load()
    assert _one(mod, "splat_literal_key") == 20


def test_splat_headarg_key_control():
    mod = _load()
    assert _one(mod, "splat_headarg_key", "age", 20) == 20
