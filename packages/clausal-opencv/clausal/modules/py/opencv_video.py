"""clausal.modules.py.opencv_video — Video I/O predicates.

Phase 10 — Video I/O.

``VideoCapture`` and ``VideoWriter`` — the gateway to per-frame
processing. **The only honestly-impure subsystem in the wrapper**.

Each ``read_frame``/``video_frame`` call advances the capture's
internal cursor in cv2's C++ underbelly. **Backtracking does not
rewind** — once a frame is read, it's read. Users wanting rewind
must call ``video_property_set(CAP, "pos_frames", N, _)`` explicitly
on seekable files.

This is the same Tier 4 honesty as a Prolog program opening a file
and reading it line by line. Documented loudly.

Use::

    -import_from(opencv_video, [
        make_video_capture, is_open, read_frame, video_frame,
        video_property, video_property_set, video_prop_name,
        make_video_writer, write_frame, fourcc, release,
    ])
    -import_from(opencv, [free])

Predicate catalogue
-------------------
VideoCapture (Tier 4):
    make_video_capture(SOURCE, HANDLE)        path or device index
    is_open(HANDLE)                            check predicate
    read_frame(HANDLE, FRAME)                  single read; fails at EOF
    video_frame(HANDLE, INDEX, FRAME)          nondet — yields frames
                                                until EOF; not safe to
                                                backtrack across
    video_property(HANDLE, NAME, VALUE)
    video_property_set(HANDLE_IN, NAME, VALUE, HANDLE_OUT)
                                                state-threaded — same int
                                                handle; underlying state
                                                mutated in place
    video_prop_name(NAME, CODE)                CAP_PROP_* registry

VideoWriter (Tier 4):
    make_video_writer(PATH, FOURCC, FPS, FRAME_SIZE, HANDLE)
    make_video_writer(..., IS_COLOR, HANDLE)
    write_frame(HANDLE, FRAME)

Codec helper (Tier 1):
    fourcc(CHARS, CODE)                        bidirectional 4-char ↔ int

Lifecycle:
    release(HANDLE)                            cv2 release + remove handle
    free(HANDLE) — inherited from Phase 1 — equivalent.
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import (
    _pred, _pure, _check_1, _bidir_2, _fact_table_2, _deep_deref,
)
from clausal.modules.py.opencv import _cv
from clausal.modules.py._opencv_handles import alloc, lookup, release as _registry_release


# ══════════════════════════════════════════════════════════════════════════
# CAP_PROP_* registry (built lazily on first use)
# ══════════════════════════════════════════════════════════════════════════


def _video_prop_facts():
    cv = _cv()
    facts = []
    seen = set()
    for attr in dir(cv):
        if not attr.startswith("CAP_PROP_"):
            continue
        val = getattr(cv, attr)
        if not isinstance(val, int) or val in seen:
            continue
        seen.add(val)
        short = attr[len("CAP_PROP_"):].lower()
        facts.append((short, val))
    facts.sort(key=lambda kv: kv[0])
    return facts


video_prop_name = _pred("video_prop_name",
    (2, _fact_table_2(_video_prop_facts)),
)


# Cache the name→code map for the property accessors.
_prop_table_cache: dict[str, int] | None = None


def _prop_lookup(name: str) -> int:
    global _prop_table_cache
    if _prop_table_cache is None:
        _prop_table_cache = dict(_video_prop_facts())
    code = _prop_table_cache.get(str(name))
    if code is None:
        raise KeyError(f"Unknown video property: {name!r}")
    return code


# ══════════════════════════════════════════════════════════════════════════
# VideoCapture
# ══════════════════════════════════════════════════════════════════════════


def _make_video_capture(source):
    cv = _cv()
    # Accept int or string-digit as a camera/device index; otherwise treat
    # as a path.
    if isinstance(source, int):
        cap = cv.VideoCapture(int(source))
    elif isinstance(source, str) and source.isdigit():
        cap = cv.VideoCapture(int(source))
    else:
        cap = cv.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"VideoCapture failed to open: {source!r}")
    return alloc(cap)


make_video_capture = _pred("make_video_capture",
    (2, _pure(_make_video_capture)),
)


is_open = _pred("is_open",
    (1, _check_1(lambda h: lookup(h).isOpened())),
)


# ── read_frame — one-shot read ────────────────────────────────────────────


def _read_frame(this_generator, _proceed, _fail, _catcher,
                handle_v, frame_v, trail):
    handle = deref(handle_v)
    try:
        cap = lookup(handle)
        ok, frame = cap.read()
    except Exception:
        yield (_fail, DONE)
        return
    if not ok:
        yield (_fail, DONE)
        return
    if unify(frame_v, frame, trail):
        yield (_proceed, None)
    yield (_fail, DONE)


read_frame = _pred("read_frame",
    (2, _read_frame),
)


# ── video_frame — nondeterministic, but commits each read ─────────────────
#
# This is the one place where the wrapper deliberately breaks
# monotonicity. The predicate yields each frame in sequence, but
# **backtracking does not rewind the underlying VideoCapture**.
# Documented in `docs/opencv_video.md`.


def _video_frame(this_generator, _proceed, _fail, _catcher,
                 handle_v, index_v, frame_v, trail):
    handle = deref(handle_v)
    try:
        cap = lookup(handle)
    except Exception:
        yield (_fail, DONE)
        return
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        mark = trail.mark()
        if (unify(index_v, index, trail)
                and unify(frame_v, frame, trail)):
            yield (_proceed, None)
        trail.undo(mark)
        index += 1
    yield (_fail, DONE)


video_frame = _pred("video_frame",
    (3, _video_frame),
)


# ── Properties ────────────────────────────────────────────────────────────


def _video_property(handle, name):
    cap = lookup(handle)
    return float(cap.get(_prop_lookup(str(name))))


video_property = _pred("video_property",
    (3, _pure(_video_property)),
)


def _video_property_set(handle, name, value):
    cap = lookup(handle)
    cap.set(_prop_lookup(str(name)), float(value))
    return handle      # state-threaded: same handle, mutated in place


video_property_set = _pred("video_property_set",
    (4, _pure(_video_property_set)),
)


# ══════════════════════════════════════════════════════════════════════════
# VideoWriter
# ══════════════════════════════════════════════════════════════════════════


def _make_video_writer_5(path, fourcc_code, fps, frame_size):
    cv = _cv()
    writer = cv.VideoWriter(str(path), int(fourcc_code), float(fps),
                              tuple(frame_size))
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"VideoWriter failed to open: {path!r}")
    return alloc(writer)


def _make_video_writer_6(path, fourcc_code, fps, frame_size, is_color):
    cv = _cv()
    writer = cv.VideoWriter(str(path), int(fourcc_code), float(fps),
                              tuple(frame_size), bool(is_color))
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"VideoWriter failed to open: {path!r}")
    return alloc(writer)


make_video_writer = _pred("make_video_writer",
    (5, _pure(_make_video_writer_5)),
    (6, _pure(_make_video_writer_6)),
)


def _write_frame(this_generator, _proceed, _fail, _catcher,
                 handle_v, frame_v, trail):
    handle = deref(handle_v)
    frame = _deep_deref(frame_v)
    try:
        lookup(handle).write(frame)
    except Exception:
        yield (_fail, DONE)
        return
    yield (_proceed, None)
    yield (_fail, DONE)


write_frame = _pred("write_frame",
    (2, _write_frame),
)


# ══════════════════════════════════════════════════════════════════════════
# fourcc — bidirectional
# ══════════════════════════════════════════════════════════════════════════


def _fourcc_forward(chars):
    s = str(chars)
    if len(s) != 4:
        raise ValueError(f"fourcc requires exactly 4 chars, got {s!r}")
    return int(_cv().VideoWriter_fourcc(*s))


def _fourcc_backward(code):
    n = int(code)
    chars = "".join(chr((n >> (8 * i)) & 0xff) for i in range(4))
    return chars


fourcc = _pred("fourcc",
    (2, _bidir_2(_fourcc_forward, _fourcc_backward)),
)


# ══════════════════════════════════════════════════════════════════════════
# Lifecycle
# ══════════════════════════════════════════════════════════════════════════


def _release_dispatch(this_generator, _proceed, _fail, _catcher,
                      handle_v, trail):
    handle = deref(handle_v)
    try:
        obj = lookup(handle)
    except Exception:
        yield (_fail, DONE)
        return
    if hasattr(obj, "release"):
        try:
            obj.release()
        except Exception:
            pass
    _registry_release(handle)
    yield (_proceed, None)
    yield (_fail, DONE)


release = _pred("release",
    (1, _release_dispatch),
)


__all__ = [
    # VideoCapture
    "make_video_capture", "is_open",
    "read_frame", "video_frame",
    "video_property", "video_property_set",
    "video_prop_name",
    # VideoWriter
    "make_video_writer", "write_frame",
    # Codec helper
    "fourcc",
    # Lifecycle
    "release",
]
