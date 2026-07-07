"""Compatibility shim — the regex predicates live in :mod:`clausal.modules.py.re`.

In ``.clausal`` sources the module is named ``regex`` and resolves through
``_IMPORT_ALIASES["regex"] = "py.re"`` (see
``clausal/templating/term_rewriting.py``). This shim re-exports the same
predicate objects for Python callers that follow the old ``clausal.regex``
name; import from ``clausal.modules.py.re`` directly in new code.
"""
from clausal.modules.py.re import (  # noqa: F401
    match,
    search,
    replace,
    split,
    findall,
)

__all__ = ["match", "search", "replace", "split", "findall"]
