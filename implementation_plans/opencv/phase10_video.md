# Phase 10 — Video I/O

`VideoCapture` and `VideoWriter` — the gateway to per-frame
processing. This is the only **truly stateful** subsystem in the
wrapper (apart from `hog_set_svm_detector`): each `read()` advances
the capture's internal cursor, and **backtracking does not rewind**.

The phase ships:

- Tier-3 handle predicates for both capture and writer.
- A nondeterministic `video_frame/3` that yields frames lazily — with
  explicit documentation that it commits each read.
- A `video_property/3` query predicate over the `CAP_PROP_*` namespace,
  plus a state-threaded `video_property_set/4`.
- A bidirectional `fourcc/2` for converting between 4-character codec
  strings and integer codes.

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_video.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — Phase 1
  already adds `free/1`. No new constants are exported via
  `_CONSTANT_NAMES` — instead, the `CAP_PROP_*` constants live behind
  the registry (`video_prop_name/2`). They are too numerous to
  enumerate by hand and rarely needed by integer code.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase10_video.clausal`
- `packages/clausal-opencv/docs/opencv_video.md`
- `packages/clausal-opencv/tests/fixtures/tiny.mp4` — a 2-frame
  120×90 video committed as a small binary fixture.

---

## Predicates

### VideoCapture (Tier 4)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `make_video_capture` | `/2` | `(+source, -handle)` | `source` is filename or int device index |
| `is_open` | `/1` | `(+handle)` check | Capture is open |
| `read_frame` | `/2` | `(+handle, -frame)` | Single read; fails at EOF |
| `video_frame` | `/3` | `(+handle, -index, -frame)` | **Nondeterministic** — yields frames until end-of-stream |
| `video_property` | `/3` | `(+handle, +name, -value)` | `name` is a `cap_prop_*` lowercase string |
| `video_property_set` | `/4` | `(+handle, +name, +value, -handle)` | **State-threaded** — returns same handle for convenience |
| `video_prop_name` | `/2` | `(+name,-code)`, `(-name,+code)`, enum | Registry of `cv2.CAP_PROP_*` |

### VideoWriter (Tier 4)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `make_video_writer` | `/5` | `(+path, +fourcc_code, +fps, +frame_size, -handle)` | Default isColor=True |
| `make_video_writer` | `/6` | `(+path, +fourcc_code, +fps, +frame_size, +is_color, -handle)` | |
| `write_frame` | `/2` | `(+handle, +frame)` | Append frame |

### Codec helpers (Tier 1)

| Name | Arity | Modes | Tier | Bijective? | Description |
|---|---|---|---|---|---|
| `fourcc` | `/2` | `(+chars, -code)` / `(-chars, +code)` | 1 | yes | 4-char string ↔ integer code |

### Lifecycle

| Name | Arity | Modes | Description |
|---|---|---|---|
| `release` | `/1` | `(+handle)` | Explicit release for capture/writer |
| `free` | `/1` | `(+handle)` | Inherited from Phase 1; also calls `release()` if present |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_video.py
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _check_1, _bidir_2, _fact_table_2, _deep_deref
from clausal.modules.opencv import _cv
from clausal.modules._opencv_handles import alloc, lookup
```

### `make_video_capture/2`

```python
def _make_video_capture(source):
    cv = _cv()
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
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
```

### `read_frame/2` and `video_frame/3` — the IO-honesty story

```python
def _read_frame_dispatch(this_generator, _proceed, _fail, _catcher,
                         handle_v, frame_v, trail):
    handle = deref(handle_v)
    try:
        cap = lookup(handle)
        ok, frame = cap.read()
    except Exception:
        yield (_fail, DONE); return
    if not ok:
        yield (_fail, DONE); return
    if unify(frame_v, frame, trail):
        yield (_proceed, None)
    yield (_fail, DONE)

read_frame = _pred("read_frame",
    (2, _read_frame_dispatch),
)
```

`video_frame/3` is nondeterministic — each backtrack reads the *next*
frame. **The frames already read are not re-readable**: this is a
property of the underlying `VideoCapture`, not a wrapper limitation.

```python
def _video_frame_dispatch(this_generator, _proceed, _fail, _catcher,
                          handle_v, index_v, frame_v, trail):
    handle = deref(handle_v)
    try:
        cap = lookup(handle)
    except Exception:
        yield (_fail, DONE); return
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
    (3, _video_frame_dispatch),
)
```

The crucial design note: this predicate is documented as a one-way
generator. Backtracking past `video_frame/3` does **not** rewind the
stream — the read is committed. For seekable files, users can
explicitly rewind with `video_property_set(CAP, "pos_frames", 0, _)`.

### `video_property/3` and `video_property_set/4`

```python
def _video_prop_facts():
    cv = _cv()
    facts = []
    for name in dir(cv):
        if not name.startswith("CAP_PROP_"):
            continue
        val = getattr(cv, name)
        if isinstance(val, int):
            short = name[len("CAP_PROP_"):].lower()
            facts.append((short, val))
    return facts

video_prop_name = _pred("video_prop_name",
    (2, _fact_table_2(_video_prop_facts)),
)

def _video_property(handle, name):
    cap = lookup(handle)
    table = dict(_video_prop_facts())
    code = table.get(str(name))
    if code is None:
        raise KeyError(f"Unknown video property: {name!r}")
    return float(cap.get(code))

video_property = _pred("video_property",
    (3, _pure(_video_property)),
)

def _video_property_set(handle, name, value):
    cap = lookup(handle)
    table = dict(_video_prop_facts())
    code = table.get(str(name))
    if code is None:
        raise KeyError(f"Unknown video property: {name!r}")
    cap.set(code, float(value))
    return handle  # state-threaded result: same handle, mutated

video_property_set = _pred("video_property_set",
    (4, _pure(_video_property_set)),
)
```

`video_property_set/4` is honest state-threading on a stateful object
— **the underlying VideoCapture is mutated**, and the returned handle
is the same integer. Backtracking past this call does *not* restore
the previous property value. Documented in the phase docs.

This is a deviation from the pure state-threading ideal. The
alternative — copying the entire VideoCapture for each property set —
isn't supported by OpenCV (VideoCapture is not copyable) and would
be wrong anyway (the underlying file/device cursor would be ambiguous).
The wrapper is honest about it: the predicate returns the handle to
acknowledge that *something happened*, but the mutation is in-place.

### `make_video_writer/5,6`

```python
def _make_video_writer(path, fourcc_code, fps, frame_size, is_color=True):
    cv = _cv()
    writer = cv.VideoWriter(str(path), int(fourcc_code), float(fps),
                             tuple(frame_size), bool(is_color))
    if not writer.isOpened():
        writer.release()
        raise RuntimeError(f"VideoWriter failed to open: {path!r}")
    return alloc(writer)

make_video_writer = _pred("make_video_writer",
    (5, _pure(_make_video_writer)),
    (6, _pure(_make_video_writer)),
)

def _write_frame_dispatch(this_generator, _proceed, _fail, _catcher,
                          handle_v, frame_v, trail):
    handle = deref(handle_v)
    frame = _deep_deref(frame_v)
    try:
        writer = lookup(handle)
        writer.write(frame)
    except Exception:
        yield (_fail, DONE); return
    yield (_proceed, None)
    yield (_fail, DONE)

write_frame = _pred("write_frame",
    (2, _write_frame_dispatch),
)
```

### `fourcc/2` (bijective)

```python
def _fourcc_forward(chars):
    s = str(chars)
    if len(s) != 4:
        raise ValueError(f"fourcc requires exactly 4 chars, got {s!r}")
    return _cv().VideoWriter_fourcc(*s)

def _fourcc_backward(code):
    n = int(code)
    chars = "".join(chr((n >> (8 * i)) & 0xff) for i in range(4))
    return chars

fourcc = _pred("fourcc",
    (2, _bidir_2(_fourcc_forward, _fourcc_backward)),
)
```

### `release/1`

```python
def _release_dispatch(this_generator, _proceed, _fail, _catcher,
                      handle_v, trail):
    handle = deref(handle_v)
    try:
        obj = lookup(handle)
    except Exception:
        yield (_fail, DONE); return
    if hasattr(obj, "release"):
        obj.release()
    from clausal.modules._opencv_handles import release as _registry_release
    _registry_release(handle)
    yield (_proceed, None)
    yield (_fail, DONE)

release = _pred("release",
    (1, _release_dispatch),
)
```

Phase 1's `free/1` does effectively the same thing; `release/1` is a
named alias that matches the OpenCV API. Both predicates ship; both
remove the handle from the registry.

---

## Example Usage

```clausal
-import_from(py.opencv, [shape, free])
-import_from(py.opencv_video, [
    make_video_capture, is_open, read_frame, video_frame,
    video_property, video_property_set, video_prop_name,
    make_video_writer, write_frame, fourcc, release
])

Test("open and query frame_count") <- (
    make_video_capture("fixtures/tiny.mp4", CAP),
    is_open(CAP),
    video_property(CAP, "frame_count", N),
    N >= 1.0,
    release(CAP)
)

Test("read_frame yields a frame") <- (
    make_video_capture("fixtures/tiny.mp4", CAP),
    read_frame(CAP, FRAME),
    shape(FRAME, [_, _, 3]),
    release(CAP)
)

Test("video_frame enumerates all frames") <- (
    make_video_capture("fixtures/tiny.mp4", CAP),
    findall(I, video_frame(CAP, I, _), INDICES),
    INDICES = [0, 1],
    release(CAP)
)

Test("fourcc round-trip") <- (
    fourcc("mp4v", CODE),
    fourcc(CHARS, CODE),
    CHARS = "mp4v"
)

Test("video_prop_name registry lookup") <- (
    video_prop_name("frame_count", CODE),
    integer(CODE)
)

Test("write a 2-frame video then read it back") <- (
    fourcc("mp4v", FOURCC),
    make_video_writer("/tmp/clausal_opencv_video_test.mp4",
                       FOURCC, 30.0, [120, 90], WRITER),
    # Use a synthetic frame
    FRAME = ++(numpy.zeros((90, 120, 3), dtype=numpy.uint8)),
    write_frame(WRITER, FRAME),
    write_frame(WRITER, FRAME),
    release(WRITER),
    make_video_capture("/tmp/clausal_opencv_video_test.mp4", CAP),
    findall(I, video_frame(CAP, I, _), INDICES),
    length(INDICES, 2),
    release(CAP)
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase10_video.clausal`:

- All Test cases above.
- `is_open` after `release` fails (uses `not(is_open(...))`).
- `video_property_set` followed by `video_property` returns the
  written value, where the property is one of `pos_frames`,
  `pos_msec` (seekable on mp4).
- A test demonstrating the **no-rewind** behaviour: after
  `findall(I, video_frame(...), _)`, a subsequent `read_frame/2`
  fails (stream exhausted).
- `make_video_capture` on a non-existent file fails.

### Python unit tests

`tests/test_opencv_infra.py` extends with:

- `release/1` removes the handle from the registry; subsequent
  `lookup` raises.
- `release/1` is idempotent (second call on the same handle fails
  cleanly).

### Test fixture

Generate `tests/fixtures/tiny.mp4` once and commit it (≤10 KB):

```python
import cv2, numpy as np
fourcc = cv2.VideoWriter_fourcc(*"mp4v")
w = cv2.VideoWriter("fixtures/tiny.mp4", fourcc, 30.0, (120, 90), True)
w.write(np.zeros((90, 120, 3), dtype=np.uint8))
w.write(np.full((90, 120, 3), 128, dtype=np.uint8))
w.release()
```

A 120×90 2-frame mp4 is small enough to commit. If the OpenCV build
in CI doesn't have an mp4 codec, the test should fall back to
generating an avi with `MJPG`. Document the codec choice in the
phase notes.

---

## Docs

`packages/clausal-opencv/docs/opencv_video.md`:

- Intro: "Video I/O — `VideoCapture` for reading, `VideoWriter` for
  writing, plus the `fourcc/2` codec helper."
- **Prominent callout: video iteration is one-way.** `video_frame/3`
  yields frames via backtracking, but each read commits — the stream
  cannot be rewound implicitly. For seekable files, use
  `video_property_set(CAP, "pos_frames", N, _)` to seek.
- Section per predicate group.
- A worked end-to-end example: read a video, apply a Phase 3 filter
  to each frame, write to a new video.

---

## Issues

### 1. `CAP_PROP_*` exposed only via registry — DECIDED

There are ~80 `CAP_PROP_*` constants in cv2. Rather than exporting
each one under a lowercase alias in `opencv.py` (cluttering the
constant set), the wrapper exposes them **only** through the
`video_prop_name/2` registry and as string-name lookups in
`video_property/3` / `video_property_set/4`.

Users write `video_property(CAP, "frame_count", N)` — readable and
discoverable via `findall`. The escape `++cv2.CAP_PROP_FRAME_COUNT`
is always available for the rare case where the integer code is
needed directly.

### 2. `video_property_set/4` returns the same handle — STATE-THREADING NOD

This is **honest state threading on a stateful object**. The handle
returned (`HANDLE_OUT`) is the *same int* as `HANDLE_IN` because the
underlying cv2 object can't be copied — there's no
`cv2.VideoCapture.__copy__`. The predicate signature mimics
state-threading (`(IN, NAME, VALUE, OUT)`) to acknowledge that
*something happened*, but the mutation is in-place.

Backtracking past `video_property_set` does **not** restore the
previous property value. Documented loudly in `opencv_video.md` and
in the overview's [Step 3](../../implementation_plans/opencv/overview.md#step-3--purity-analysis).

### 3. `video_frame/3` commits each read — DOCUMENTED

The nondeterministic enumerator yields each frame as it's read from
the underlying capture. Backtracking past a yielded frame **does
not rewind** the capture cursor — that read is committed. Tested
explicitly: after `findall(I, video_frame(CAP, I, _), _)`, the
stream is exhausted and a subsequent `read_frame` fails.

For seekable files users can rewind via
`video_property_set(CAP, "pos_frames", 0, _)`. Tested.

### 4. cv2 codec availability is build-dependent — HANDLED

The `make_video_writer` codec choice depends on the cv2 build's
FFmpeg link. The test fixture is `tiny.mp4` with the `mp4v` codec
(universally supported by opencv-python builds). Tests for
write-then-read use `mp4v`. Documented as a deployment caveat.

### 5. `opencv-python` keeps getting reinstalled — RECURRENT FRICTION

The `clausal-opencv` package depends on `opencv-python`. When pip
needs to reinstall the package (which happens during dependency
resolution if another change touches the dist-info), it pulls
`opencv-python` (which needs `libGL.so.1`) over the manually-
installed `opencv-python-headless`. In headless environments this
breaks all phases that load cv2.

Workaround: `pip uninstall opencv-python -y && pip install
opencv-python-headless --force-reinstall --no-deps`. Hit this
during Phase 9 and Phase 10 testing.

A cleaner fix is to make `opencv-python` an *optional* dependency
in `pyproject.toml` and let the user choose between the two
variants, but that breaks the simple `pip install clausal-opencv`
story.

### 6. `release/1` and `free/1` are equivalent — DOCUMENTED

`release/1` is a named alias for `free/1` that matches the OpenCV
API surface (`cv2.VideoCapture.release()`). Both predicates remove
the handle from the registry and (for objects with a `.release`
method) invoke it. Tests verify both work on capture and writer
handles. Choice between them is purely cosmetic.

### 7. `fourcc/2` byte-pack format — VERIFIED

cv2's `VideoWriter_fourcc('m','p','4','v')` produces an int whose
4 bytes spell `"mp4v"` in little-endian order. The wrapper's
backward direction reconstructs the string via
`chr((n >> (8 * i)) & 0xff) for i in 0..3`. Round-trip verified
exact for `"mp4v"`, `"MJPG"`, `"XVID"`. Documented in
`opencv_video.md`.

### 8. Phase 10 ships independent of Phase 9 — STRUCTURAL

The video module has no dependency on calib3d. Phase 10 could in
principle ship before Phase 9. The plan's ordering is just the
catalogue order — the implementation here confirms there's no
hidden coupling.
