"""Shared helpers for the 2026-05-25 string audit adversarial tests."""

from __future__ import annotations

import os
import tempfile
from typing import Any

from clausal.import_hook import _load_module
from tests._suffix import SEAM


def load_inline_clausal(name: str, source: str) -> Any:
    """Load a .clausal source string as a module, returning the module object.

    Writes *source* to a tempfile, loads it via the clausal import hook,
    and unlinks the tempfile. Returns the loaded module; the caller can
    pass `module=mod.__dict__["$module"]` to `clausal.logic.solve.call`.

    Use this in tests that need to register predicates inline (any test
    that exercises the Database / dispatch / compile pipeline). Pure-Python
    unit tests on `clausal.terms.SegList`/`.SegString` don't need this.
    """
    with tempfile.NamedTemporaryFile(
        suffix=SEAM, mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)
