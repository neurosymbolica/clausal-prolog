"""A failing docs code block must report the same goal-level diagnosis as a
failing ``.clausal`` file test.

``ClausalItem.runtest`` runs failures through ``diagnose_failure`` (see
``test_pytest_plugin_diagnostics.py``); ``DocItem`` — the collector for
```` ```clausal ```` blocks in ``docs/*.md`` — still raised a bare
``Test(...) has no solutions``, the same missing signal on the collector that
fires whenever a tutorial example rots.  The block's compile buffer used to be
unlinked before any item ran, which is why the diagnosis had no source to
quote; blocks now live in a session-scoped directory so the report can name
the failing conjunct and its variables.  See
``todo/done/doc-block-failures-report-a-bare-no-solutions.md``.

Exercised through a real ``pytest`` subprocess loading the root conftest, for
the same reason as the sibling test file: asserting on helpers would pass
while the call-site wiring was missing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load the root conftest by path (see test_pytest_plugin_diagnostics._SHIM)
# and retarget its docs directory at the tmp dir so a planted .md collects.
_SHIM = """\
import importlib.util as _util
from pathlib import Path as _Path

_spec = _util.spec_from_file_location("_clausal_root_conftest", {path!r})
_plugin = _util.module_from_spec(_spec)
_spec.loader.exec_module(_plugin)

_plugin._docs_dir = _Path({docs_dir!r})

pytest_collect_file = _plugin.pytest_collect_file
pytest_sessionfinish = getattr(_plugin, "pytest_sessionfinish", None)
"""


def run_doc_plugin(tmp_path: Path, md_source: str) -> str:
    """Run *md_source* as a docs .md file through the real conftest plugin."""
    (tmp_path / "conftest.py").write_text(
        _SHIM.format(path=str(REPO_ROOT / "conftest.py"), docs_dir=str(tmp_path))
    )
    (tmp_path / "sample.md").write_text(textwrap.dedent(md_source).lstrip())
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path / "sample.md"), "-q",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    return proc.stdout + proc.stderr


FAILING_MD = """
# Sample tutorial

```clausal
prc("alpha", 10),
prc("beta", 20),

Test("later goal fails after a binding") <- (
    prc("alpha", NUM),
    prc("gamma", NUM)
),
```
"""

PASSING_MD = """
# Sample tutorial

```clausal
prc("alpha", 10),

Test("passes") <- (
    prc("alpha", NUM),
    NUM > 5
),
```
"""

ERROR_MD = """
# Sample tutorial

```clausal
prc("alpha", 10),

Test("raises") <- (
    prc("alpha", NUM),
    atom_length(NUM, LEN),
    LEN > 0
),
```
"""


@pytest.fixture(scope="module")
def failing_report(tmp_path_factory):
    """One subprocess run, shared by the assertions about its report."""
    return run_doc_plugin(tmp_path_factory.mktemp("docfail"), FAILING_MD)


def test_failing_goal_named_for_doc_block(failing_report):
    assert "goal 2 of 2 failed" in failing_report
    # the source text of the failing conjunct with its source variable name —
    # the full diagnosis, not the degraded path-less fallback
    assert "prc(gamma, NUM)" in failing_report


def test_bindings_reported_for_doc_block(failing_report):
    assert "bindings at failure: NUM = 10" in failing_report


def test_bare_headline_is_kept_for_doc_block(failing_report):
    """The diagnosis is added under the message, not swapped in for it."""
    assert "has no solutions" in failing_report
    assert "1 failed" in failing_report


def test_raising_doc_block_also_diagnosed(tmp_path):
    out = run_doc_plugin(tmp_path, ERROR_MD)
    assert "raised:" in out
    assert "goal 2 of 3 raised" in out
    assert "atom_length(NUM, LEN)" in out


def test_passing_doc_block_reports_no_diagnosis(tmp_path):
    out = run_doc_plugin(tmp_path, PASSING_MD)
    assert "1 passed" in out
    assert "goal" not in out
