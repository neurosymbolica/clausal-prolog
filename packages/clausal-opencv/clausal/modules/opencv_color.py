"""clausal.modules.opencv_color — OpenCV color-space predicates.

Phase 2 — Color Conversions.

Provides ``cv2.cvtColor`` (via integer code or string name), the
``color_code/2`` bidirectional name↔code registry, and a single
``channels/2`` predicate that collapses ``cv2.split`` / ``cv2.merge``
into a bidirectional pair.

Use::

    -import_from(opencv_color, [cvt_color, channels, color_code])
    -import_from(opencv, [color_bgr2gray, color_bgr2hsv])  # constants

Predicate catalogue
-------------------
    cvt_color(IMG, CODE, OUT)            cvtColor by integer code
    cvt_color_named(IMG, NAME, OUT)      cvtColor by lowercase short name
    color_code(NAME, CODE)               Name ↔ int code registry
    channels(IMG, LIST)                  Bidirectional split/merge
"""

from __future__ import annotations

import threading as _threading

from clausal.modules.py._helpers import _pred, _pure, _bidir_2, _fact_table_2
from clausal.modules.opencv import _cv


# ── Cached name ↔ code maps ───────────────────────────────────────────────
#
# cv2 exposes hundreds of COLOR_* integer constants. Both the registry
# and ``cvt_color_named`` need the (name, code) pairs; build them once
# on first use and cache.

_color_facts: list[tuple[str, int]] | None = None
_color_by_name: dict[str, int] | None = None
_color_facts_lock = _threading.Lock()


def _build_color_facts() -> list[tuple[str, int]]:
    global _color_facts, _color_by_name
    if _color_facts is not None:
        return _color_facts
    with _color_facts_lock:
        if _color_facts is not None:
            return _color_facts
        cv = _cv()
        facts: list[tuple[str, int]] = []
        seen: dict[int, str] = {}
        for attr in dir(cv):
            if not attr.startswith("COLOR_"):
                continue
            val = getattr(cv, attr)
            if not isinstance(val, int):
                continue
            short = attr[len("COLOR_"):].lower()
            # cv2 has multiple aliases for the same int code; keep the
            # first short-name we see for that int to make reverse
            # lookup deterministic.
            if val in seen:
                continue
            seen[val] = short
            facts.append((short, val))
        # Stable sort so enumeration order is reproducible across runs.
        facts.sort(key=lambda kv: kv[0])
        _color_facts = facts
        _color_by_name = dict(facts)
        return facts


def _lookup_color_code(name: str) -> int:
    _build_color_facts()
    code = _color_by_name.get(str(name))
    if code is None:
        raise KeyError(f"Unknown color code name: {name!r}")
    return code


# ── Predicates ─────────────────────────────────────────────────────────────


cvt_color = _pred("cvt_color",
    (3, _pure(lambda img, code: _cv().cvtColor(img, int(code)))),
)


def _cvt_named(img, name):
    return _cv().cvtColor(img, _lookup_color_code(name))


cvt_color_named = _pred("cvt_color_named",
    (3, _pure(_cvt_named)),
)


color_code = _pred("color_code",
    (2, _fact_table_2(_build_color_facts)),
)


def _split_channels(img):
    return list(_cv().split(img))


def _merge_channels(channels_list):
    return _cv().merge(channels_list)


channels = _pred("channels",
    (2, _bidir_2(_split_channels, _merge_channels)),
)


__all__ = [
    "cvt_color",
    "cvt_color_named",
    "color_code",
    "channels",
]
