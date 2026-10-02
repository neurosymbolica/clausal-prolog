"""The pytest plugin must report the same goal-level diagnosis as the CLI.

``clausal.testing.diagnose_failure`` names the failing conjunct, the bindings
live at that point and the solution the predicate did have — but it was opt-in
and only ``run_file`` opted in, so the detail existed solely for
``python -m clausal.testing``.  Under ``pytest`` — which is where CI and most
day-to-day runs read failures — the same test reported a bare
``test(...) failed (no solutions)``.  See
``todo/done/test-diagnostics-not-wired-into-the-pytest-plugin.md``.

The plugin is a root ``conftest.py``, so it is exercised here through a real
``pytest`` subprocess that loads it.  Asserting on a message-building helper
instead would pass while the wiring at the call site was still missing, which
is precisely the defect being fixed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from tests._suffix import SEAM

REPO_ROOT = Path(__file__).resolve().parent.parent

# The child's own rootdir conftest is imported by pytest under the module name
# ``conftest``, so a plain ``import conftest`` there would find *itself*.  Load
# the plugin under test by path instead, and take only the collection hook:
# the root conftest's session fixture clears the checkout's ``__pycache__``,
# which must not happen underneath the run that spawned us.
_SHIM = """\
import importlib.util as _util

_spec = _util.spec_from_file_location("_clausal_root_conftest", {path!r})
_plugin = _util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin)

pytest_collect_file = _plugin.pytest_collect_file
"""


def run_plugin(tmp_path: Path, source: str, filename: str = f"case{SEAM}") -> str:
    """Run *source* as a .clausal file through the real conftest plugin."""
    (tmp_path / "conftest.py").write_text(
        _SHIM.format(path=str(REPO_ROOT / "conftest.py"))
    )
    (tmp_path / filename).write_text(textwrap.dedent(source).lstrip())
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    return proc.stdout + proc.stderr


BINDINGS_SRC = """
-double_quotes(atom)
prc("alpha", 10),
prc("beta", 20),

test("later goal fails after a binding") <- (
    prc("alpha", NUM),
    prc("gamma", NUM)
),
"""

ERROR_SRC = """
-double_quotes(atom)
prc("alpha", 10),

test("raises") <- (
    prc("alpha", NUM),
    atom_length(NUM, LEN),
    LEN > 0
),
"""

PASSING_SRC = """
-double_quotes(atom)
prc("alpha", 10),

test("passes") <- (
    prc("alpha", NUM),
    NUM > 5
),
"""


@pytest.fixture(scope="module")
def bindings_report(tmp_path_factory):
    """One subprocess run, shared by the assertions about its report."""
    return run_plugin(tmp_path_factory.mktemp("bindings"), BINDINGS_SRC)


def test_failing_goal_named_under_pytest(bindings_report):
    assert "goal 2 of 2 failed" in bindings_report
    # the source text of the failing conjunct, not a Python repr
    assert "prc(gamma, NUM)" in bindings_report


def test_bindings_reported_under_pytest(bindings_report):
    assert "bindings at failure: NUM = 10" in bindings_report


def test_nearest_solution_reported_under_pytest(bindings_report):
    assert "did not unify" in bindings_report
    assert "prc(alpha, 10)" in bindings_report


def test_bare_headline_is_kept(bindings_report):
    """The diagnosis is added to the message, not swapped in for it."""
    assert "failed (no solutions)" in bindings_report
    assert "1 failed" in bindings_report


def test_raising_test_also_diagnosed(tmp_path):
    """A raised error names its goal too — the CLI reports both the same way."""
    out = run_plugin(tmp_path, ERROR_SRC)
    assert "raised:" in out
    assert "goal 2 of 3 raised" in out
    assert "atom_length(NUM, LEN)" in out


def test_passing_test_is_not_rerun(tmp_path):
    """Diagnostics stay on the failure path: a green test must not re-execute.

    The re-run replays body goals and their side effects, so paying for it on
    a passing test would be both a slowdown and a behaviour change.
    """
    out = run_plugin(tmp_path, PASSING_SRC)
    assert "1 passed" in out
    assert "goal" not in out


def test_passing_test_computes_no_diagnostic_at_all(tmp_path):
    """Pin the guard itself, not just the absence of output.

    The test above only shows a green run *prints* no diagnosis — which it
    would do even if the re-run had happened and been discarded.  What costs
    time and replays side effects is the re-run, so assert on the thing that
    proves it did not happen: ``run_test`` leaves ``diagnostic`` unset for a
    passing test even when ``diagnose=True`` (``clausal/testing.py:262``).
    """
    from clausal.import_hook import _load_module
    from clausal.testing import run_test

    src = tmp_path / f"green{SEAM}"
    src.write_text(PASSING_SRC)
    mod = _load_module("_diag_guard_probe", str(src))
    result = run_test(mod, "passes", path=str(src), diagnose=True)
    assert result.passed
    assert result.diagnostic is None


def test_seam_file_is_collected_by_the_plugin(tmp_path):
    """``.seam`` is an alias extension for ``.clausal``: the plugin collects it."""
    out = run_plugin(tmp_path, PASSING_SRC, filename="case.seam")
    assert "1 passed" in out, out


def test_txt_file_is_not_collected_by_the_plugin(tmp_path):
    """Negative control: only the two predicate-module extensions are collected."""
    out = run_plugin(tmp_path, PASSING_SRC, filename="case.txt")
    assert "no tests ran" in out, out
