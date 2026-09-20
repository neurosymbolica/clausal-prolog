"""Regression test: a .clausal module that re-exports a Python-backed
``clausal.modules.py.*`` wrapper must stay importable from any working
directory.

Background
----------
``clausal_torch`` / ``clausal_jax`` are installed *non-editably* and drop bare
``.py`` files into ``site-packages/clausal/modules/`` (no ``__init__.py``),
turning that directory into a PEP 420 namespace portion. When a process runs
from a cwd that does not put the clausal *source* tree on ``sys.path`` (the
normal shape for a rulebase + separate test harness), the stdlib ``PathFinder``
resolves ``clausal.modules`` to that site-packages portion *before* the
editable finder is consulted — and that portion lacks the source-only ``py/``
subpackage. The result was::

    <load> — No module named 'clausal.modules.py'

for any ``-import_from(date_time, ...)`` (or regex/json/os/…) re-exported across
a ``.clausal`` module boundary. See
``todo/transitive-import-of-python-backed-module-bug.md``.

The fix (in ``clausal/import_hook.py``) ensures the source ``clausal/modules``
directory is always on ``clausal.modules.__path__`` so the ``py/`` subpackage is
discoverable regardless of cwd.

This test reproduces the failure faithfully by running ``clausal.testing`` in a
subprocess from a throwaway directory with the source root removed from
``PYTHONPATH`` (relying on the editable install to provide ``clausal``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

# Source tree root (parent of the ``clausal`` package dir).
_SRC_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _installed_python() -> str | None:
    """Path to an interpreter that has ``clausal`` *installed* (the project venv).

    The bug only manifests when ``clausal`` resolves via an installed
    distribution whose ``clausal/modules`` is shadowed by a site-packages
    namespace portion lacking the source-only ``py/`` subpackage. Under the
    pytest interpreter ``clausal`` is normally found via source-on-path, where
    the bug cannot reproduce — so we drive the project venv interpreter, which
    carries the editable install plus the shadowing extension packages.
    """
    for candidate in (
        os.path.join(_SRC_ROOT, "venv", "bin", "python"),
        os.path.join(_SRC_ROOT, "venv", "bin", "python3"),
    ):
        if os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(sys.executable):
            return candidate
    return None


def _env_without_source() -> dict:
    """A child-process environment with the source root stripped from PYTHONPATH.

    This forces ``clausal`` to resolve via the installed (editable) distribution
    rather than the source tree on the path, reproducing the namespace-shadow
    condition that triggered the bug.
    """
    env = dict(os.environ)
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
             if p and os.path.abspath(p) != _SRC_ROOT]
    if parts:
        env["PYTHONPATH"] = os.pathsep.join(parts)
    else:
        env.pop("PYTHONPATH", None)
    return env


_VENV_PY = _installed_python()
_skip_no_venv = pytest.mark.skipif(
    _VENV_PY is None,
    reason="no project venv interpreter with an installed clausal distribution found",
)


@_skip_no_venv
def test_transitive_python_backed_module_import(tmp_path):
    """B (.clausal) imports A (.clausal) which re-exports a py-backed module."""
    (tmp_path / "mod_dt.clausal").write_text(textwrap.dedent("""\
        -import_from(date_time, [date, date_diff])
        days_between(Y1,M1,D1, Y2,M2,D2, N) <- (
            S is date(Y1,M1,D1), E is date(Y2,M2,D2), date_diff(E, S, TD), N is ++TD.days)
    """))
    (tmp_path / "use_dt.clausal").write_text(textwrap.dedent("""\
        -import_from(mod_dt, [days_between])
        test("transitive import of a date_time module") <- (days_between(2026,1,1, 2026,4,1, N), N == 90)
    """))

    proc = subprocess.run(
        [_VENV_PY, "-m", "clausal.testing", "use_dt.clausal"],
        cwd=str(tmp_path),
        env=_env_without_source(),
        capture_output=True,
        text=True,
    )

    assert "No module named 'clausal.modules.py'" not in proc.stdout + proc.stderr, (
        "py-backed wrapper failed to resolve transitively:\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.returncode == 0, (
        f"transitive py-backed import test failed:\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "1 passed" in proc.stdout, proc.stdout


@_skip_no_venv
def test_direct_python_backed_module_import(tmp_path):
    """A single .clausal file importing a py-backed module also works from any cwd."""
    (tmp_path / "direct_dt.clausal").write_text(textwrap.dedent("""\
        -import_from(date_time, [date, date_diff])
        test("direct date_time import") <- (
            S is date(2026,1,1), E is date(2026,4,1), date_diff(E, S, TD), ++TD.days == 90)
    """))

    proc = subprocess.run(
        [_VENV_PY, "-m", "clausal.testing", "direct_dt.clausal"],
        cwd=str(tmp_path),
        env=_env_without_source(),
        capture_output=True,
        text=True,
    )

    assert "No module named 'clausal.modules.py'" not in proc.stdout + proc.stderr, (
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert proc.returncode == 0, (
        f"direct py-backed import test failed:\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "1 passed" in proc.stdout, proc.stdout
