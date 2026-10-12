# tests/clpq_port/test_package_surface.py
"""clausal.logic.clpq exports the same names whichever solver is selected."""
import importlib
import os

import pytest

import clausal.logic.clpq as clpq

LEGACY_NAMES = sorted(n for n in dir(importlib.import_module(
    "clausal.logic.clpq.legacy")) if not n.startswith("__"))


@pytest.fixture
def restore_the_package():
    """Reload the package under the environment the session started with,
    so a test that reloads it under another CLAUSAL_CLPQ leaves SOLVER and
    the exported names as they were (Task 1, deferred minor)."""
    saved = os.environ.get("CLAUSAL_CLPQ")
    yield
    current = os.environ.get("CLAUSAL_CLPQ")
    legacy = importlib.import_module("clausal.logic.clpq.legacy")
    for name in clpq.HOLZBAUR_API:          # names legacy does not have
        if not hasattr(legacy, name):
            clpq.__dict__.pop(name, None)
    _set_env(saved)
    try:
        importlib.reload(clpq)
    finally:
        _set_env(current)       # monkeypatch undoes its own change after this
    assert clpq.SOLVER == (saved or "legacy")


def _set_env(value):
    if value is None:
        os.environ.pop("CLAUSAL_CLPQ", None)
    else:
        os.environ["CLAUSAL_CLPQ"] = value


def test_the_package_exports_every_legacy_name():
    missing = [n for n in LEGACY_NAMES if not hasattr(clpq, n)]
    assert missing == []


def test_the_default_solver_is_legacy(monkeypatch, restore_the_package):
    monkeypatch.delenv("CLAUSAL_CLPQ", raising=False)
    assert importlib.reload(clpq).SOLVER == "legacy"
    assert clpq.q_eq.__module__ == "clausal.logic.clpq.legacy"


def test_holzbaur_selects_the_port_behind_the_same_names(
        monkeypatch, restore_the_package):
    monkeypatch.setenv("CLAUSAL_CLPQ", "holzbaur")
    importlib.reload(clpq)
    assert clpq.SOLVER == "holzbaur"
    from clausal.logic.clpq import holzbaur
    from clausal.logic.clpq.attributes import CLPQ_KEY
    for name in clpq.HOLZBAUR_API:
        assert getattr(clpq, name) is getattr(holzbaur, name), name
    assert clpq.Q_KEY == CLPQ_KEY
    missing = [n for n in LEGACY_NAMES if not hasattr(clpq, n)]
    assert missing == []


def test_an_unknown_solver_name_raises(monkeypatch, restore_the_package):
    monkeypatch.setenv("CLAUSAL_CLPQ", "simplex")
    with pytest.raises(ValueError, match="CLAUSAL_CLPQ must be legacy or "
                                         "holzbaur, not 'simplex'"):
        importlib.reload(clpq)
