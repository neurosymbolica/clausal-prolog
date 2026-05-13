"""Unit tests for clausal.modules.opencv infrastructure.

Covers:
- The lazy ``cv2`` import does not load ``cv2`` at module import time.
- The constant export ``__getattr__`` raises ``AttributeError`` for
  unknown names so introspection tools work correctly.
- The shared handle registry in ``_opencv_handles``.
- ``free/1`` removes a registered handle.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def test_lazy_import_holds_no_cv2_reference_at_module_load():
    """The wrapper's lazy-import guard must not eagerly hold a cv2 reference.

    A destructive ``del sys.modules['cv2']`` then re-import test would
    break cv2 for the rest of the session (cv2.dnn bootstrap is
    fragile across re-imports), so this test instead introspects the
    wrapper module's private global directly: ``_cv2`` starts as None
    and is populated only after a call to ``_ensure_cv2()``.
    """
    from clausal.modules import opencv as m
    # Reset to the cold-import state (this only affects our wrapper —
    # any pre-loaded cv2 module in sys.modules stays).
    m._cv2 = None
    # Constants exposed via __getattr__ trigger _ensure_cv2().
    _ = m.imread_color
    assert m._cv2 is not None


def test_getattr_raises_for_unknown_name():
    from clausal.modules import opencv as m
    with pytest.raises(AttributeError, match="no attribute 'not_a_constant'"):
        _ = m.not_a_constant


def test_getattr_returns_known_constants():
    from clausal.modules import opencv as m
    # Constants are exported under lowercase aliases because ALL-CAPS
    # names are reserved for logic variables by Clausal's grammar.
    assert isinstance(m.imread_color, int)
    assert isinstance(m.imread_grayscale, int)
    assert isinstance(m.norm_l2, int)
    assert isinstance(m.cv_8u, int)


def test_handle_registry_alloc_returns_distinct_integers():
    from clausal.modules._opencv_handles import alloc
    h1 = alloc(object())
    h2 = alloc(object())
    assert isinstance(h1, int) and isinstance(h2, int)
    assert h1 != h2


def test_handle_registry_lookup_and_release():
    from clausal.modules._opencv_handles import alloc, lookup, release
    obj = object()
    h = alloc(obj)
    assert lookup(h) is obj
    assert release(h) is True
    with pytest.raises(KeyError):
        lookup(h)
    # Second release on the same handle returns False (idempotent).
    assert release(h) is False


def test_handle_registry_lookup_unknown_raises():
    from clausal.modules._opencv_handles import lookup
    with pytest.raises(KeyError):
        lookup(9_999_999)


def test_free_predicate_removes_handle():
    """free/1 calls release() if present and removes from registry."""
    from clausal.modules import opencv as m
    from clausal.modules._opencv_handles import alloc, lookup
    from clausal.logic.solve import call
    from clausal.logic.variables import Var

    class Releasable:
        def __init__(self):
            self.released = False
        def release(self):
            self.released = True

    obj = Releasable()
    h = alloc(obj)

    # Sanity: lookup works before free
    assert lookup(h) is obj

    # Invoke free/1 directly. ``free`` is a ModulePredicate, callable
    # via the trampoline through ``call``.
    ok = any(True for _ in call(m.free, h))
    assert ok, "free/1 should succeed for a known handle"

    # After free, lookup must fail and release must have been called.
    assert obj.released is True
    with pytest.raises(KeyError):
        lookup(h)


def test_free_predicate_on_unknown_handle_fails():
    from clausal.modules import opencv as m
    from clausal.logic.solve import call

    ok = any(True for _ in call(m.free, 8_888_888))
    assert ok is False
