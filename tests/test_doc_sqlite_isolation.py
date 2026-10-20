"""Doc examples that open sqlite connections do not leak them into one
another.

The sqlite module keeps its connections in a process-wide table keyed by
alias, and ``connect/2`` on a connected alias reuses the open database.  So
running docs/sqlite.md's blocks twice in one process -- once through
``check_clausal_blocks`` (tests/test_doc_clausal_blocks.py), once through the
root conftest's docs/*.md collection -- found the first run's tables and
failed 8 examples with "table users already exists", in either order.  Each
checked block, and each collected page, now closes the connections it opened.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from clausal.tools.doc_snippet_check import check_clausal_blocks

REPO_ROOT = Path(__file__).resolve().parent.parent

BLOCK = """\
```clausal
:- use_module(library(sqlite), [connect/2, exec/2, query/3]).

test("fresh table") :-
    connect(":memory:", "doc_isolation_db"),
    exec("doc_isolation_db", "CREATE TABLE t (x INTEGER)"),
    exec("doc_isolation_db", "INSERT INTO t VALUES (1)"),
    findall(X, query("doc_isolation_db", "SELECT x FROM t", X), [1]).
```
"""


def test_a_checked_block_closes_the_connections_it_opened(tmp_path):
    (tmp_path / "a.md").write_text(BLOCK)
    (tmp_path / "b.md").write_text(BLOCK)
    assert check_clausal_blocks(tmp_path) == []
    # Twice over the same pages: nothing is left from the first pass.
    assert check_clausal_blocks(tmp_path) == []
    from clausal.modules.py.sqlite import _CONNECTIONS
    assert "doc_isolation_db" not in _CONNECTIONS


@pytest.mark.parametrize("order", [
    ["tests/test_doc_clausal_blocks.py", "docs/sqlite.md"],
    ["docs/sqlite.md", "tests/test_doc_clausal_blocks.py"],
], ids=["blocks-then-page", "page-then-blocks"])
def test_the_sqlite_page_passes_after_the_block_check_in_either_order(
        tmp_path, order):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["TMPDIR"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         f"--basetemp={tmp_path / 'pt'}", *order],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
    assert "already exists" not in proc.stdout, proc.stdout[-4000:]
