"""Model tests skip, with the reason, when laya's checkpoint cannot load.

The ``.seam`` fixtures under ``tests/fixtures/`` (and the doc examples under
``tests/fixtures/docs/``) ask the REAL model: laya downloads its checkpoint
from the Hugging Face Hub on first use.  Where that cannot happen -- no
network, the Hub blocked -- they are skipped, naming the error, rather than
failed.  The ``*_stubbed.py`` tests use a fake router and always run.
"""

from __future__ import annotations

import pathlib

import pytest

_FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
_MODEL_ERROR: list = []          # [] untried, [None] loaded, [reason] failed


def _model_unavailable() -> str | None:
    if not _MODEL_ERROR:
        try:
            from clausal.modules.py import laya as pylaya  # noqa: PLC0415
            pylaya._get_router().load("english")
            _MODEL_ERROR.append(None)
        except Exception as exc:  # noqa: BLE001 -- any failure means no model
            _MODEL_ERROR.append(f"{type(exc).__name__}: {exc}"[:300])
    return _MODEL_ERROR[0]


def pytest_runtest_setup(item):
    path = pathlib.Path(str(item.path)).resolve()
    if _FIXTURES in path.parents:
        reason = _model_unavailable()
        if reason is not None:
            pytest.skip(f"laya checkpoint not available: {reason}")
