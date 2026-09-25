"""clausal-provenance is DISABLED pending a redesign (2026-09-25).

Every test here is skipped, visibly, rather than collected against a package
whose import now refuses.  See the package README.
"""
import pytest

collect_ignore_glob = ["test_*.py", "fixtures/*"]


def pytest_collection_finish(session):
    session.config.pluginmanager.get_plugin("terminalreporter").write_line(
        "clausal-provenance: DISABLED pending redesign -- tests not collected")
