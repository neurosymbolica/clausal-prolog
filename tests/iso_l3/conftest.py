"""Shared fixture for the native ``.pl`` front-end slices (plan
native-iso-reader-step2 §4): every load clears ``__pycache__``, asserts WHICH
front end ran (the loader class), and asserts L3's read/lowered/refused counts
with a NON-ZERO denominator -- a comparison that passes without the front end
under test running proves nothing (it happened to the P1 author once)."""
from __future__ import annotations

import importlib
import shutil
import sys

import pytest

ENV = "CLAUSAL_PL_FRONTEND"

# The slice-1 exit rulebase and its seam twin are DATA for
# test_l3_s1_exit.py, and s2/ the slice-2 rulebase for test_l3_s2_exit.py;
# each runs them under the native front end.  Collected
# as test files they would run under the default (the translator) instead.
collect_ignore = ["rulebase_s1.pl", "rulebase_s1_twin.seam", "s2"]


class NativeLoads:
    def __init__(self, tmp, monkeypatch):
        self.tmp = tmp
        self._mp = monkeypatch
        self._names: list[str] = []

    def _clear(self):
        for p in self.tmp.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)

    def load(self, name: str, text: str, *, suffix: str = ".pl",
             frontend: "str | None" = "native", refused: int = 0):
        """Write *text* as ``name + suffix`` and import it fresh.  For a
        ``.pl`` under the native front end, assert the loader and the stats
        (``read == lowered + refused``, ``read > 0``)."""
        from clausal import import_hook as ih
        (self.tmp / (name + suffix)).write_text(text, encoding="utf-8")
        if frontend is None:
            self._mp.delenv(ENV, raising=False)
        else:
            self._mp.setenv(ENV, frontend)
        self._clear()
        sys.modules.pop(name, None)
        self._names.append(name)
        importlib.invalidate_caches()
        mod = importlib.import_module(name)
        if suffix == ".pl":
            want = (ih.NativePrologLoader if frontend == "native"
                    else ih.PrologLoader)
            assert type(mod.__loader__) is want, type(mod.__loader__)
            if frontend == "native":
                st = mod.__loader__.l3_stats
                assert st is not None, "L3 never ran"
                assert st["read"] > 0, st
                assert st["refused"] == refused, st
                assert st["read"] == st["lowered"] + st["refused"], st
        return mod

    def close(self):
        for n in self._names:
            sys.modules.pop(n, None)
        self._clear()


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    loads = NativeLoads(tmp_path, monkeypatch)
    yield loads
    loads.close()


def answers(mod, name, arity=1, *fixed):
    """All answers of ``name(*fixed, V1..Vk)`` (k = arity - len(fixed)), in
    order, each a tuple of the walked free arguments (a bare value if k=1)."""
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    vs = [Var() for _ in range(arity - len(fixed))]
    out = []
    for _ in call(name, *fixed, *vs, module=mod):
        row = tuple(walk(deref(v)) for v in vs)
        out.append(row[0] if len(row) == 1 else row)
    return out


@pytest.fixture
def ans():
    return answers
