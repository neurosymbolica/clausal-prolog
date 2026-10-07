"""Real-ACL2 tests skip, with the reason, when no ACL2 bridge can be had.

The ``.seam`` fixtures under ``tests/fixtures/`` (and ``fixtures/docs/``)
talk to a REAL ACL2.  They use the bridge named by ``CLAUSAL_ACL2_SOCKET``
(a running ``(bridge::start "<path>")``), else start ``acl2`` from PATH --
which needs the ACL2 books, including ``centaur/bridge`` certified.  Where
neither works they are skipped, naming the error.  ``*_stubbed.py`` tests
use a fake bridge and always run.
"""

from __future__ import annotations

import os
import pathlib
import shutil

import pytest

_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
_STATE: list = []                # [] untried, [None] connected, [reason] not


def _bridge_unavailable() -> str | None:
    if not _STATE:
        from clausal.modules.py import acl2 as pyacl2  # noqa: PLC0415
        socket_path = os.environ.get("CLAUSAL_ACL2_SOCKET")
        if socket_path:
            pyacl2._reset({"socket": socket_path})
        elif shutil.which("acl2") is None:
            _STATE.append("no acl2 on PATH and CLAUSAL_ACL2_SOCKET unset")
            return _STATE[0]
        else:
            pyacl2._reset({"command": "acl2"})
        try:
            pyacl2._get_bridge("probe")
            _STATE.append(None)
        except Exception as exc:  # noqa: BLE001 -- any failure means no bridge
            _STATE.append(f"{type(exc).__name__}: {exc}"[:300])
    return _STATE[0]


def pytest_runtest_setup(item):
    path = pathlib.Path(str(item.path)).resolve()
    if _FIXTURES in path.parents:
        reason = _bridge_unavailable()
        if reason is not None:
            pytest.skip(f"ACL2 bridge not available: {reason}")
