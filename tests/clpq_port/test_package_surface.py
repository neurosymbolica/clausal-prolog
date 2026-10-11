# tests/clpq_port/test_package_surface.py
"""clausal.logic.clpq exports the same names whichever solver is selected."""
import importlib

import clausal.logic.clpq as clpq

LEGACY_NAMES = sorted(n for n in dir(importlib.import_module(
    "clausal.logic.clpq.legacy")) if not n.startswith("__"))


def test_the_package_exports_every_legacy_name():
    missing = [n for n in LEGACY_NAMES if not hasattr(clpq, n)]
    assert missing == []


def test_the_default_solver_is_legacy(monkeypatch):
    monkeypatch.delenv("CLAUSAL_CLPQ", raising=False)
    assert importlib.reload(clpq).SOLVER == "legacy"
