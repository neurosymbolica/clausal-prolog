"""Shared handle registry for opencv-python wrapper modules.

Used by later phases (features, objdetect, video) to manage detector,
matcher, capture, and writer handles. Phase 1 also uses this to back
the `free/1` predicate exposed from ``clausal.modules.opencv``.

Pattern mirrors ``packages/clausal-scipy/clausal/modules/scipy_spatial.py``
(see ``_alloc_handle`` / ``_lookup_handle``).
"""

from __future__ import annotations

import threading as _threading

_REGISTRY: dict[int, object] = {}
_lock = _threading.Lock()
_counter = [0]


def alloc(obj: object) -> int:
    """Register *obj* under a fresh integer handle and return the handle."""
    with _lock:
        _counter[0] += 1
        h = _counter[0]
        _REGISTRY[h] = obj
    return h


def lookup(handle) -> object:
    """Return the object registered under *handle*.

    Raises ``KeyError`` if the handle is unknown or has been released.
    """
    obj = _REGISTRY.get(int(handle))
    if obj is None:
        raise KeyError(f"Unknown opencv handle: {handle!r}")
    return obj


def release(handle) -> bool:
    """Remove *handle* from the registry. Returns True if it was present."""
    with _lock:
        return _REGISTRY.pop(int(handle), None) is not None
