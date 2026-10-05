"""Smoke test for ``tools/show_generated.py``, the dev/audit script that prints
generated trampoline code.

It stopped running once (it imported the deleted ``PredicateMeta`` and set
the class's retired ``_locked``) and nothing noticed, because no test ran
it.  This runs it end to end, in a subprocess pinned to THIS tree, and
checks that section 7 (Phase 10) still prints the direct bucket reference.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "show_generated.py"


@pytest.mark.skipif(not SCRIPT.exists(), reason="tools/show_generated.py not in this tree")
def test_show_generated_runs_and_prints_the_phase_10_bucket_reference():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = proc.stdout
    # Every section header printed, so no section was skipped.
    for n in range(1, 8):
        assert f"# {n}." in out, f"section {n} missing"
    # Phase 10: the call site references the bucket function directly ...
    # Matched on whitespace-free text with either quote style.  Today the
    # script's optional ``black`` pass never applies (black rejects the
    # ``$``-names and the script prints the ``ast.unparse`` text as is); the
    # normalisation covers whitespace and quote changes only, so a
    # reformatter that did more (e.g. dropping or adding parentheses) could
    # still break these asserts.
    flat = re.sub(r"\s+", "", out).replace('"', "'")
    assert "StepGenerator(color.bucket(pos=0,('red',0))" in flat
    # ... and the no-hint comparison goes through the dispatch.
    assert "StepGenerator($dispatch_at(color,1)" in flat
