"""The query cache must not serve a query compiled for a DEAD module.

todo/done/query-cache-keys-on-id-of-a-possibly-transient-module-2026-09-06.md.
The cache key is ``(structure, id(module))``.  ``solve`` over a plain Python
module wraps it in a fresh ``Module`` on every call, which died with the
query and freed its id; the next wrap often landed on the same id, HIT the
dead module's entry, and ran code resolved against the dead module's
namespace -- a silent wrong answer (measured on the base: 14 of 20 pairs
below answered the other module's value).
"""
import gc
import sys
import types
import weakref

import pytest

from clausal.logic.atoms import mangle
from clausal.logic.database import Module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("qctm")
    p = d / "qctm_owner.clausal"
    p.write_text("-module(qctm_owner, [p/1, q/1])\np(1),\nq(2),\n")
    mod = _load_module("qctm_owner", str(p))
    yield mod
    sys.modules.pop("qctm_owner", None)


def _plain(name, target):
    m = types.ModuleType(name)
    m.g = mangle("qctm_owner", target)   # a handle to the owner's predicate
    return m


def test_same_goal_over_two_plain_modules_answers_each_its_own(owner):
    wrong = []
    for i in range(40):
        a = _plain(f"qctm_a{i}", "p")
        b = _plain(f"qctm_b{i}", "q")
        X = Var()
        ra = [_deref_walk(X) for _ in solve(("g", X), a)]
        X = Var()
        rb = [_deref_walk(X) for _ in solve(("g", X), b)]
        if ra != [1] or rb != [2]:
            wrong.append((i, ra, rb))
    assert wrong == []


def test_a_cached_query_keeps_its_module_alive(owner):
    """Deterministic form: the entry holds the module, so its id cannot be
    reused while the entry lives."""
    pm = _plain("qctm_keep", "p")
    m = Module("qctm_keep", module_dict=vars(pm))
    ref = weakref.ref(m)
    X = Var()
    assert [_deref_walk(X) for _ in solve(("g", X), m)] == [1]
    del m
    gc.collect()
    assert ref() is not None
