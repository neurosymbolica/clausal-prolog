# tests/clpq_port/test_package_surface.py
"""clausal.logic.clpq exports the port; CLAUSAL_CLPQ=legacy is refused by name.

The solver Clausal shipped before the port was retired by operator ruling
2026-11-05 ("we should retire legacy CLPQ").
"""
import importlib
import os
import pathlib
import subprocess
import sys

import pytest

import clausal.logic.clpq as clpq

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def restore_the_package():
    """Reload the package under the environment the session started with,
    so a test that reloads it under another CLAUSAL_CLPQ leaves SOLVER and
    the exported names as they were."""
    saved = os.environ.get("CLAUSAL_CLPQ")
    yield
    current = os.environ.get("CLAUSAL_CLPQ")
    _set_env(saved)
    try:
        importlib.reload(clpq)
    finally:
        _set_env(current)       # monkeypatch undoes its own change after this
    assert clpq.SOLVER == "holzbaur"


def _set_env(value):
    if value is None:
        os.environ.pop("CLAUSAL_CLPQ", None)
    else:
        os.environ["CLAUSAL_CLPQ"] = value


def test_the_package_exports_the_port():
    from clausal.logic.clpq import holzbaur
    from clausal.logic.clpq.attributes import CLPQ_KEY
    assert clpq.SOLVER == "holzbaur"
    for name in clpq.HOLZBAUR_API:
        assert getattr(clpq, name) is getattr(holzbaur, name), name
    assert clpq.Q_KEY == CLPQ_KEY


def test_the_legacy_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("clausal.logic.clpq.legacy")
    for name in ("Tableau", "QVar", "DQ", "_tableaux", "_linearize"):
        assert not hasattr(clpq, name), name


def test_the_default_solver_is_the_port(monkeypatch, restore_the_package):
    # Operator ruling 2026-11-05: the port is the default, and the only one.
    monkeypatch.delenv("CLAUSAL_CLPQ", raising=False)
    assert importlib.reload(clpq).SOLVER == "holzbaur"
    assert clpq.q_eq.__module__ == "clausal.logic.clpq.holzbaur"


def test_holzbaur_still_names_the_port(monkeypatch, restore_the_package):
    monkeypatch.setenv("CLAUSAL_CLPQ", "holzbaur")
    assert importlib.reload(clpq).SOLVER == "holzbaur"
    assert clpq.q_eq.__module__ == "clausal.logic.clpq.holzbaur"


def test_legacy_raises_a_named_error(monkeypatch, restore_the_package):
    # No silent fallback to the port.
    monkeypatch.setenv("CLAUSAL_CLPQ", "legacy")
    with pytest.raises(ValueError, match=r"CLAUSAL_CLPQ=legacy was removed "
                       r"after clausal 1\.4\.0 \(operator ruling 2026-11-05\); "
                       r"the port of clp\(q,r\) 1\.3\.3 is the only CLP\(Q\) "
                       r"solver"):
        importlib.reload(clpq)


def test_an_unknown_solver_name_raises(monkeypatch, restore_the_package):
    monkeypatch.setenv("CLAUSAL_CLPQ", "simplex")
    with pytest.raises(ValueError, match="CLAUSAL_CLPQ must be holzbaur "
                                         r"\(or unset\), not 'simplex'"):
        importlib.reload(clpq)


def test_legacy_stops_a_program_at_its_first_clp_q_goal(tmp_path):
    # The package is imported when CLP(Q) is first used, so that is where
    # the error comes; a program without CLP(Q) is unaffected.
    program = tmp_path / "q.pl"
    program.write_text(":- use_module(library(clpq)).\np(X) :- {X >= 1}.\n")
    env = dict(os.environ, CLAUSAL_CLPQ="legacy", PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-m", "clausal", str(program),
                        "-g", "p(X)"], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode != 0
    assert "CLAUSAL_CLPQ=legacy was removed" in r.stderr, r.stderr[-2000:]
    assert "{" not in r.stdout, r.stdout
