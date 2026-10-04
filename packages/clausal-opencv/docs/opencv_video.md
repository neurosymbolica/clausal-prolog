# `opencv_video` — Video I/O

`VideoCapture` and `VideoWriter` — the gateway to per-frame
processing. Plus `fourcc/2`, the bidirectional 4-char ↔ int codec
helper.

## ⚠ This is the only honestly-impure phase

Every other phase in the wrapper is either fully pure (Tier 1) or
uses handle-based encapsulation that preserves backtracking safety
(detectors, matchers, cascades, HOG). This phase is different:

**`VideoCapture` and `VideoWriter` are Tier 4 — stateful, with side
effects that backtracking does not unwind.**

Each `read_frame/2` or `video_frame/3` call advances the capture's
internal cursor in cv2's C++ underbelly. Each `write_frame/2`
appends bytes to the output file. **Backtracking past a read does
not rewind, and backtracking past a write does not roll back the
file.**

Why? Because `cv2.VideoCapture` wraps either:
- a file descriptor (with FFmpeg state, keyframe seeks, hardware
  decoder context, …), or
- a V4L / camera / network device (live stream — no rewind exists).

Python-level copies of the object aren't supported by cv2. Snapshot-
and-restore via `pos_frames` is possible only for seekable files,
and **only at keyframe boundaries** — exact frame-level rewind isn't
guaranteed.

So the wrapper is honest about what it can and can't do:

- `read_frame/2` and `video_frame/3` advance the cursor **and commit
  the read** to the underlying stream. Backtracking abandons the
  Clausal-side binding of `FRAME` but the cursor stays advanced.
- `video_property_set/4` returns the *same* handle as a state-
  threading nod, but the underlying object is mutated in place. The
  signature acknowledges *something happened*; it doesn't actually
  give you a separate handle to the old state.
- Users wanting to re-read frames must call
  `video_property_set(CAP, "pos_frames", 0, _)` explicitly.

This is the same honesty as Prolog's `read/1` from a stream — once
read, gone.

```clausal
-import_from(opencv_video, [
    make_video_capture, is_open, read_frame, video_frame,
    video_property, video_property_set, video_prop_name,
    make_video_writer, write_frame, fourcc, release,
])
-import_from(opencv, [free])
```

## VideoCapture

| Predicate | Arity | Description |
|---|---|---|
| `make_video_capture(SOURCE, HANDLE)` | /2 | `SOURCE` is a file path or integer device index |
| `is_open(HANDLE)` | /1 | Check — fails after `release` |
| `read_frame(HANDLE, FRAME)` | /2 | **One-shot** — fails at EOF; cursor advances |
| `video_frame(HANDLE, INDEX, FRAME)` | /3 | **Nondeterministic** — yields frames until EOF, committing each |

`make_video_capture/2` fails if the path doesn't exist or the
codec isn't supported (cv2 prints an FFmpeg error to stderr —
nothing the wrapper can hide).

### Properties

| Predicate | Arity | Description |
|---|---|---|
| `video_property(HANDLE, NAME, VALUE)` | /3 | Query a `cap_prop_*` |
| `video_property_set(HANDLE_IN, NAME, VALUE, HANDLE_OUT)` | /4 | **State-threaded** — same int handle, underlying object mutated |
| `video_prop_name(NAME, CODE)` | /2 | Bidirectional name↔code registry |

`NAME` is a lowercase string corresponding to the cv2 `CAP_PROP_*`
constant with the prefix stripped: `"frame_count"`, `"fps"`,
`"frame_width"`, `"frame_height"`, `"pos_frames"`, `"pos_msec"`,
`"fourcc"`, etc.

### State threading note

`video_property_set/4` returns the input handle unchanged
(`CAP == CAP_OUT`). This is *honest* about the underlying mutation —
the predicate signature acknowledges *something happened* — but does
**not** give backtracking safety. If you `set(pos_frames, 100)` and
then backtrack past that point, the capture remains at frame 100.

For seekable files this is usually what you want anyway:
`video_property_set(CAP, "pos_frames", 0, _)` to rewind, then
re-iterate.

## VideoWriter

| Predicate | Arity | Description |
|---|---|---|
| `make_video_writer(PATH, FOURCC, FPS, FRAME_SIZE, HANDLE)` | /5 | Default is_color=True |
| `make_video_writer(PATH, FOURCC, FPS, FRAME_SIZE, IS_COLOR, HANDLE)` | /6 | |
| `write_frame(HANDLE, FRAME)` | /2 | Append a frame |

`FRAME_SIZE` is `[W, H]` (OpenCV order — same as `size/2` from
`opencv`). Frames passed to `write_frame` must match this size and
have 3 channels (or 1 if `is_color=False`).

The codec is the integer `FOURCC` value from `fourcc/2`. Common
codecs: `"mp4v"` for `.mp4`, `"MJPG"` for `.avi`, `"XVID"` for
`.avi`. Codec availability depends on the cv2 build and FFmpeg
linking.

## `fourcc/2` — bidirectional

| Direction | Mode | Example |
|---|---|---|
| Forward | `(+chars, -code)` | `fourcc("mp4v", CODE)` |
| Backward | `(-chars, +code)` | `fourcc(CHARS, CODE)` |

The forward call goes through `cv2.VideoWriter_fourcc(*chars)`. The
backward call reconstructs the 4-character code from the integer's
byte pattern, as an ATOM (a codec tag is a symbolic name). Round-trip is
exact.

```clausal
fourcc("MJPG", CODE),
fourcc(CHARS, CODE),
CHARS == "MJPG"
```

## Lifecycle

| Predicate | Arity | Description |
|---|---|---|
| `release(HANDLE)` | /1 | Calls cv2's `.release()` and removes from registry |
| `free(HANDLE)` | /1 | Inherited from Phase 1, equivalent |

Both are idempotent in the "second call fails cleanly" sense — once
the handle is removed from the registry, a second `release` returns
predicate-failure (not an exception).

## Worked examples

Each example below is an exact copy of an integration test in
`tests/fixtures/opencv_phase10_video.seam`.

### Read the first frame of a video

```clausal
make_video_capture("/tmp/clip.mp4", CAP),
read_frame(CAP, FRAME),
shape(FRAME, [_, _, 3]),
release(CAP)
```

### Iterate every frame

```clausal
make_video_capture("/tmp/clip.mp4", CAP),
findall(I, video_frame(CAP, I, _), INDICES),
INDICES == [0, 1, 2, 3, 4],
release(CAP)
```

### Query metadata

```clausal
make_video_capture("/tmp/clip.mp4", CAP),
video_property(CAP, "frame_count", N),
video_property(CAP, "fps", FPS),
video_property(CAP, "frame_width", W),
video_property(CAP, "frame_height", H),
release(CAP)
```

### Explicit rewind to re-read

```clausal
make_video_capture("/tmp/clip.mp4", CAP),
findall(I, video_frame(CAP, I, _), _),         % exhausts stream
video_property_set(CAP, "pos_frames", 0, _),   % rewind
read_frame(CAP, FRAME),                         % works again
release(CAP)
```

### Write a 2-frame video and read it back

```clausal
fourcc("mp4v", FOURCC),
make_video_writer("/tmp/out.mp4", FOURCC, 30.0, [120, 90], WRITER),
FRAME is ++(numpy.zeros((90, 120, 3), dtype=numpy.uint8)),
write_frame(WRITER, FRAME),
write_frame(WRITER, FRAME),
release(WRITER),
make_video_capture("/tmp/out.mp4", CAP),
findall(I, video_frame(CAP, I, _), INDICES),
length(INDICES, 2),
release(CAP)
```

### Per-frame processing pipeline (cross-phase)

```clausal
make_video_capture("/tmp/clip.mp4", CAP),
findall(GRAY, (
    video_frame(CAP, _, FRAME),
    cvt_color(FRAME, color_bgr2gray, GRAY)
), GRAYS),
release(CAP)
```

## See also

- [`opencv`](opencv.md) — `free/1` lifecycle, the constants used by
  property names.
- [`opencv_color`](opencv_color.md), [`opencv_imgproc`](opencv_imgproc.md)
  — the per-frame transforms a video pipeline typically chains.
- [overview Step 3](../../implementation_plans/opencv/overview.md#step-3--purity-analysis)
  — the full purity analysis explains why this phase is the
  exception to the otherwise-pure wrapper.
