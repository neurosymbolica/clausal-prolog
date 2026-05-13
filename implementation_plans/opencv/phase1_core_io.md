# Phase 1 — Core, I/O, Properties, Arithmetic

The foundation. Defines the lazy `cv2` import, the constant export
mechanism, the shared handle registry (in `_opencv_handles.py`),
property predicates, image arithmetic, and the bidirectional
encode/decode pair.

This is the only phase that **must** ship before any other phase.
Every later phase imports `_cv()` and helpers from this file.

**Files to create:**

- `packages/clausal-opencv/pyproject.toml`
- `packages/clausal-opencv/README.md`
- `packages/clausal-opencv/clausal/modules/opencv.py`
- `packages/clausal-opencv/clausal/modules/_opencv_handles.py`
- `packages/clausal-opencv/tests/clausal_files/opencv_phase1_core.clausal`
- `packages/clausal-opencv/tests/test_opencv_infra.py`
- `packages/clausal-opencv/tests/fixtures/tiny_gray.png`
- `packages/clausal-opencv/tests/fixtures/tiny_rgb.png`
- `packages/clausal-opencv/docs/opencv.md`

---

## Predicates

### I/O (Tier 4)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `imread` | `/2` | `(+path, -img)` | Read image with default flags (`IMREAD_COLOR`) |
| `imread` | `/3` | `(+path, +flag, -img)` | Read with explicit flag |
| `imwrite` | `/2` | `(+path, +img)` | Write image |
| `imwrite` | `/3` | `(+path, +img, +params)` | Write with `params` (list of int pairs as a flat list, e.g. `[IMWRITE_JPEG_QUALITY, 80]`) |
| `image_encoded` | `/3` | `(+img, +ext, -buf)` / `(-img, +ext, +buf)` | Bijective encode/decode |

`image_encoded/3` is the bidirectional predicate:

- Forward (`+img, +ext, -buf`): calls `cv2.imencode(ext, img)`,
  returns the `bytes` of the resulting `np.ndarray` buffer.
- Backward (`-img, +ext, +buf`): calls
  `cv2.imdecode(np.frombuffer(buf, dtype=np.uint8), IMREAD_UNCHANGED)`.
- `ext` is required in both modes — the decoder doesn't need it, but
  symmetry with the forward direction makes the predicate easier to
  understand and prevents mode-detection bugs when `buf` is bound
  but `ext` is a var.

### Properties (Tier 1, multi-mode)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `shape` | `/2` | `(+img, -shape)`, `(+img, +shape)` | NumPy shape; `(H, W)` or `(H, W, C)` |
| `dtype` | `/2` | `(+img, -d)`, `(+img, +d)` | `img.dtype` |
| `channels_count` | `/2` | `(+img, -n)`, `(+img, +n)` | `1` if 2-D, `img.shape[2]` if 3-D |
| `size` | `/2` | `(+img, -[w, h])`, `(+img, +[w, h])` | OpenCV size — `(W, H)`, swapped from `shape` |
| `element_count` | `/2` | `(+img, -n)` | `img.size` |
| `is_grayscale` | `/1` | `(+img)` | Single-channel check |
| `is_color` | `/1` | `(+img)` | 3-channel check |
| `is_uint8` | `/1` | `(+img)` | dtype check |

### Arithmetic (Tier 1, pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `add` | `/3` | `(+a, +b, -c)` | Saturated add (`cv2.add`) |
| `subtract` | `/3` | `(+a, +b, -c)` | Saturated subtract |
| `multiply` | `/3` | `(+a, +b, -c)` | Element-wise multiply |
| `multiply` | `/4` | `(+a, +b, +scale, -c)` | With scale |
| `divide` | `/3` | `(+a, +b, -c)` | Element-wise divide |
| `divide` | `/4` | `(+a, +b, +scale, -c)` | With scale |
| `absdiff` | `/3` | `(+a, +b, -c)` | `|a - b|` |
| `bitwise_and` | `/3` | `(+a, +b, -c)` | |
| `bitwise_and` | `/4` | `(+a, +b, +mask, -c)` | |
| `bitwise_or` | `/3` | `(+a, +b, -c)` | |
| `bitwise_or` | `/4` | `(+a, +b, +mask, -c)` | |
| `bitwise_xor` | `/3` | `(+a, +b, -c)` | |
| `bitwise_xor` | `/4` | `(+a, +b, +mask, -c)` | |
| `bitwise_not` | `/2` | `(+a, -c)` | |
| `bitwise_not` | `/3` | `(+a, +mask, -c)` | |
| `min` | `/3` | `(+a, +b, -c)` | Element-wise min (`cv2.min`) |
| `max` | `/3` | `(+a, +b, -c)` | Element-wise max |

### Reductions (Tier 1, pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `mean` | `/2` | `(+img, -m)` | Channel-wise mean as 4-tuple |
| `mean` | `/3` | `(+img, +mask, -m)` | Masked mean |
| `min_max_loc` | `/2` | `(+img, -result)` | Returns `min_max(MIN_VAL, MAX_VAL, MIN_LOC, MAX_LOC)` |
| `min_max_loc` | `/3` | `(+img, +mask, -result)` | Masked |

### Whole-image transforms (Tier 1, pure)

| Name | Arity | Modes | Description |
|---|---|---|---|
| `flip` | `/3` | `(+img, +code, -out)` | `code` ∈ {0, 1, -1}; self-inverse at fixed code |
| `transpose` | `/2` | `(+img, -out)` | `cv2.transpose` |
| `copy_image` | `/2` | `(+img, -copy)` | `img.copy()` |

### Constants exported (re-exports of `cv2.*`)

The following constants are exported from `py.opencv` and can be
imported by name. Implementation is a module-level `__getattr__` that
looks up `cv2.NAME` on demand (lazy — avoids importing `cv2` at module
import time when the user only wants a constant).

- **Image read flags:** `IMREAD_COLOR`, `IMREAD_GRAYSCALE`,
  `IMREAD_UNCHANGED`, `IMREAD_ANYDEPTH`, `IMREAD_ANYCOLOR`,
  `IMREAD_REDUCED_GRAYSCALE_2`, `IMREAD_REDUCED_COLOR_2`,
  `IMREAD_REDUCED_GRAYSCALE_4`, `IMREAD_REDUCED_COLOR_4`,
  `IMREAD_REDUCED_GRAYSCALE_8`, `IMREAD_REDUCED_COLOR_8`.
- **Image write params:** `IMWRITE_JPEG_QUALITY`, `IMWRITE_PNG_COMPRESSION`,
  `IMWRITE_WEBP_QUALITY`, `IMWRITE_TIFF_COMPRESSION`.
- **Dtypes:** `CV_8U`, `CV_8S`, `CV_16U`, `CV_16S`, `CV_32S`,
  `CV_32F`, `CV_64F`.
- **Norm types** (used here by `min_max_loc` derivatives and Phase 7
  matchers): `NORM_INF`, `NORM_L1`, `NORM_L2`, `NORM_L2SQR`,
  `NORM_HAMMING`, `NORM_HAMMING2`, `NORM_MINMAX`.

Later phases extend the export list. The `__getattr__` implementation
delegates to `cv2`, so adding a new constant in a later phase is a
documentation update only.

---

## Context and Reference Patterns

### Package skeleton

Mirror `packages/clausal-torch/`:

```toml
# packages/clausal-opencv/pyproject.toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "clausal-opencv"
version = "0.1.0"
description = "OpenCV (cv2) predicates for Clausal"
readme = "README.md"
license = {text = "MIT"}
authors = [{name = "Mike Amy", email = "mikeamycoder@gmail.com"}]
requires-python = ">=3.13"
dependencies = [
    "clausal>=0.3.1",
    "opencv-python",
    "numpy",
]

[project.urls]
Repository = "https://gitlab.com/MikeAmy/clausal"

[tool.setuptools.packages.find]
where = ["."]
include = ["clausal*"]
```

The `clausal/` and `clausal/modules/` directories have no
`__init__.py` — they're PEP 420 namespace packages owned by the core
distribution. See `packages/clausal-torch/pyproject.toml` for the
verbatim layout.

### Lazy `cv2` import

Follow `packages/clausal-torch/clausal/modules/torch.py:228-245`:

```python
# packages/clausal-opencv/clausal/modules/opencv.py
import threading as _threading

_cv2 = None
_cv2_lock = _threading.Lock()

def _ensure_cv2():
    global _cv2
    if _cv2 is not None:
        return
    with _cv2_lock:
        if _cv2 is not None:
            return
        from clausal.modules.py import _import_stdlib
        _cv2 = _import_stdlib("cv2")

def _cv():
    _ensure_cv2()
    return _cv2
```

### Constant exports via `__getattr__`

Follow `packages/clausal-torch/clausal/modules/torch.py` (see the
dtype exports near the bottom of the file). The module defines:

```python
_CONSTANT_NAMES = frozenset([
    # imread flags
    "IMREAD_COLOR", "IMREAD_GRAYSCALE", "IMREAD_UNCHANGED",
    "IMREAD_ANYDEPTH", "IMREAD_ANYCOLOR",
    "IMREAD_REDUCED_GRAYSCALE_2", "IMREAD_REDUCED_COLOR_2",
    "IMREAD_REDUCED_GRAYSCALE_4", "IMREAD_REDUCED_COLOR_4",
    "IMREAD_REDUCED_GRAYSCALE_8", "IMREAD_REDUCED_COLOR_8",
    # imwrite params
    "IMWRITE_JPEG_QUALITY", "IMWRITE_PNG_COMPRESSION",
    "IMWRITE_WEBP_QUALITY", "IMWRITE_TIFF_COMPRESSION",
    # dtypes
    "CV_8U", "CV_8S", "CV_16U", "CV_16S", "CV_32S", "CV_32F", "CV_64F",
    # norm types
    "NORM_INF", "NORM_L1", "NORM_L2", "NORM_L2SQR",
    "NORM_HAMMING", "NORM_HAMMING2", "NORM_MINMAX",
    # ... extended by later phases via _CONSTANT_NAMES |= {...}
])

def __getattr__(name):
    if name in _CONSTANT_NAMES:
        return getattr(_cv(), name)
    raise AttributeError(name)
```

Subsequent phases extend `_CONSTANT_NAMES` by adding to the frozenset
literal in their phase-specific section of `opencv.py` — or by
defining their own module-level constants, depending on which file
they live in.

### Tier-1 dispatch helpers

Use the shared helpers from `clausal/modules/py/_helpers.py` (already
imported by torch):

```python
from clausal.modules.py._helpers import (
    _pred, _pure, _property_2, _bidir_3_mid, _check_1, _deep_deref,
)
```

- `_pred(name, (arity, dispatch_fn), ...)` — create a `ModulePredicate`.
- `_pure(fn)` — wraps a pure function as a Tier-1 dispatch.
- `_property_2(getter)` — multi-mode query/check predicate.
- `_bidir_3_mid(forward, backward)` — bidirectional with middle arg
  (used by `image_encoded/3`).
- `_check_1(predicate_fn)` — boolean check (used by `is_grayscale/1`,
  `is_color/1`, `is_uint8/1`).

### Shared handle registry

Create `packages/clausal-opencv/clausal/modules/_opencv_handles.py`,
mirroring `packages/clausal-scipy/clausal/modules/scipy_spatial.py:196-260`:

```python
"""Shared handle registry for opencv-python wrapper modules.

Used by opencv_features, opencv_objdetect, opencv_video for managing
detector / matcher / capture device handles. Phase 1 creates the
file but does not use it — phases 7+ are the first consumers.
"""
import threading as _threading

_REGISTRY: dict[int, object] = {}
_lock = _threading.Lock()
_counter = [0]

def alloc(obj):
    with _lock:
        _counter[0] += 1
        h = _counter[0]
        _REGISTRY[h] = obj
    return h

def lookup(handle):
    obj = _REGISTRY.get(int(handle))
    if obj is None:
        raise KeyError(f"Unknown opencv handle: {handle!r}")
    return obj

def release(handle):
    with _lock:
        _REGISTRY.pop(int(handle), None)
```

Phase 1 creates this file and adds a `free/1` predicate to `opencv.py`
so all later phases have a single free predicate to share:

```python
free = _pred("free",
    (1, _free_dispatch),
)
```

where `_free_dispatch` calls `lookup(handle)` (to verify it exists,
plus call `.release()` if the held object has one) then `release(handle)`.
`cv2.VideoCapture`, `cv2.VideoWriter` have `.release()`; detectors and
matchers do not.

### Arithmetic predicates pattern

```python
add = _pred("add",
    (3, _pure(lambda a, b: _cv().add(a, b))),
)

subtract = _pred("subtract",
    (3, _pure(lambda a, b: _cv().subtract(a, b))),
)

multiply = _pred("multiply",
    (3, _pure(lambda a, b: _cv().multiply(a, b))),
    (4, _pure(lambda a, b, scale: _cv().multiply(a, b, scale=float(scale)))),
)

# bitwise_and with optional mask:
bitwise_and = _pred("bitwise_and",
    (3, _pure(lambda a, b: _cv().bitwise_and(a, b))),
    (4, _pure(lambda a, b, mask: _cv().bitwise_and(a, b, mask=mask))),
)
```

All arithmetic predicates wrap with `make_quantity_aware` per the
overview:

```python
from clausal.modules._scipy_units import make_quantity_aware, STRIP_TO_PLAIN

_raw_add = lambda a, b: _cv().add(a, b)
# Algebraic propagation requires both operands' dims to match.
add = _pred("add",
    (3, _pure(make_quantity_aware(_raw_add, "algebraic"))),
)
```

Reuse the scipy `_scipy_units.py` directly — it's already in the
namespace package. No new units file is needed for opencv.

### Property dispatches

```python
shape = _pred("shape",
    (2, _property_2(lambda img: list(img.shape))),
)

dtype = _pred("dtype",
    (2, _property_2(lambda img: img.dtype)),
)

channels_count = _pred("channels_count",
    (2, _property_2(lambda img: 1 if img.ndim == 2 else img.shape[2])),
)

size = _pred("size",
    (2, _property_2(lambda img: [img.shape[1], img.shape[0]])),
)

element_count = _pred("element_count",
    (2, _pure(lambda img: int(img.size))),
)

is_grayscale = _pred("is_grayscale", (1, _check_1(lambda img: img.ndim == 2)))
is_color     = _pred("is_color",     (1, _check_1(lambda img: img.ndim == 3 and img.shape[2] == 3)))

import numpy as _np
is_uint8     = _pred("is_uint8",     (1, _check_1(lambda img: img.dtype == _np.uint8)))
```

### `image_encoded/3` (bidirectional)

Follow `tensor_numpy` in `torch.py:482-487`:

```python
import numpy as _np

def _encode(img, ext):
    ok, buf = _cv().imencode(ext, img)
    if not ok:
        raise RuntimeError(f"imencode failed for ext={ext!r}")
    return bytes(buf.tobytes())

def _decode(buf, ext):
    arr = _np.frombuffer(buf, dtype=_np.uint8)
    return _cv().imdecode(arr, _cv().IMREAD_UNCHANGED)

image_encoded = _pred("image_encoded",
    (3, _bidir_3_mid(_encode, _decode)),
)
```

Note: `_bidir_3_mid` passes the middle arg (`ext`) to both forward and
backward. The `ext` argument is unused by the decoder in cv2 itself,
but accepting it makes the predicate symmetric and prevents the
backward call from being mistaken for the forward call when only `ext`
is bound.

### `imread` / `imwrite` (Tier 4)

```python
imread = _pred("imread",
    (2, _pure(lambda path: _cv().imread(path))),
    (3, _pure(lambda path, flag: _cv().imread(path, int(flag)))),
)

# imwrite has no result; we still need a dispatch that yields proceed/fail.
def _imwrite_2(this_generator, _proceed, _fail, _catcher, path_var, img_var, trail):
    from clausal.logic.variables import deref
    path = deref(path_var)
    img = _deep_deref(img_var)
    try:
        ok = _cv().imwrite(path, img)
    except Exception:
        yield (_fail, DONE); return
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)

def _imwrite_3(this_generator, _proceed, _fail, _catcher, path_var, img_var, params_var, trail):
    from clausal.logic.variables import deref
    path = deref(path_var)
    img = _deep_deref(img_var)
    params = _deep_deref(params_var)
    try:
        ok = _cv().imwrite(path, img, list(params))
    except Exception:
        yield (_fail, DONE); return
    if ok:
        yield (_proceed, None)
    yield (_fail, DONE)

imwrite = _pred("imwrite",
    (2, _imwrite_2),
    (3, _imwrite_3),
)
```

`imwrite` is the one place in Phase 1 that needs a custom dispatch
rather than `_pure` — it has no RESULT to unify, so it must yield
proceed/fail directly based on the C call's return value.

### `min_max_loc/2`

Returns a tagged term `min_max(MIN_VAL, MAX_VAL, MIN_LOC, MAX_LOC)`.
The term is a plain tuple with a string tag — Clausal terms can be
plain tuples or tagged tuples; the convention here matches torch's
`tensor_list` pattern.

```python
def _min_max_loc(img):
    min_val, max_val, min_loc, max_loc = _cv().minMaxLoc(img)
    # Use a tagged tuple matching clause-head decomposition style.
    return ("min_max", float(min_val), float(max_val),
            list(min_loc), list(max_loc))

def _min_max_loc_masked(img, mask):
    min_val, max_val, min_loc, max_loc = _cv().minMaxLoc(img, mask=mask)
    return ("min_max", float(min_val), float(max_val),
            list(min_loc), list(max_loc))

min_max_loc = _pred("min_max_loc",
    (2, _pure(_min_max_loc)),
    (3, _pure(_min_max_loc_masked)),
)
```

In `.clausal` users decompose with:

```clausal
min_max_loc(IMG, R),
R is ("min_max", MIN_V, MAX_V, MIN_L, MAX_L)
```

### `mean/2`

`cv2.mean` returns a 4-tuple even for single-channel images (with
zeros in unused channels). The wrapper returns it verbatim — users
slice with `R is [B, G, R, A]` or `nth0(0, R, M)`.

```python
mean = _pred("mean",
    (2, _pure(lambda img: list(_cv().mean(img)))),
    (3, _pure(lambda img, mask: list(_cv().mean(img, mask=mask)))),
)
```

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, imwrite, image_encoded, shape, dtype, channels_count,
    size, element_count, is_grayscale, is_color, is_uint8,
    add, subtract, absdiff, multiply, divide,
    bitwise_and, bitwise_or, bitwise_xor, bitwise_not,
    min, max, mean, min_max_loc, flip, transpose, copy_image,
    IMREAD_COLOR, IMREAD_GRAYSCALE, IMREAD_UNCHANGED, CV_8U
])

Test("imread color and shape query") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, [_, _, 3]),
    is_color(IMG)
)

Test("imread grayscale yields 2-D shape") <- (
    imread("fixtures/tiny_gray.png", IMREAD_GRAYSCALE, IMG),
    shape(IMG, [_, _]),
    is_grayscale(IMG),
    channels_count(IMG, 1)
)

Test("imread unchanged") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_UNCHANGED, IMG),
    is_uint8(IMG)
)

Test("shape check mode succeeds with concrete shape") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, SHAPE),
    shape(IMG, SHAPE)  # check mode with already-bound shape
)

Test("size returns [W, H]") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, [H, W, _]),
    size(IMG, [W, H])
)

Test("element_count matches H*W*C") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, [H, W, C]),
    element_count(IMG, N),
    N is H * W * C
)

Test("image_encoded roundtrip png") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    image_encoded(IMG, ".png", BUF),
    image_encoded(IMG2, ".png", BUF),
    shape(IMG, S),
    shape(IMG2, S)
)

Test("absdiff with self is zero") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    absdiff(IMG, IMG, D),
    min_max_loc(D, R),
    R is ("min_max", 0.0, 0.0, _, _)
)

Test("bitwise_not is involutive") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    bitwise_not(IMG, INV),
    bitwise_not(INV, INV2),
    absdiff(IMG, INV2, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("flip code 0 is involutive (vertical)") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    flip(IMG, 0, F),
    flip(F, 0, F2),
    absdiff(IMG, F2, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("transpose swaps H and W") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    shape(IMG, [H, W, _]),
    transpose(IMG, T),
    shape(T, [W, H, _])
)

Test("imwrite roundtrip png to tmpdir") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, IMG),
    imwrite("/tmp/clausal_opencv_test_out.png", IMG),
    imread("/tmp/clausal_opencv_test_out.png", IMREAD_COLOR, IMG2),
    shape(IMG, S),
    shape(IMG2, S)
)

Test("imread fails on missing file") <- (
    not(imread("does/not/exist.png", IMREAD_COLOR, _))
)
```

---

## Tests

### `.clausal` integration tests

Single file: `tests/clausal_files/opencv_phase1_core.clausal`,
containing every Test above plus:

- `add` / `subtract` saturation behaviour with `uint8` (255 + 1 == 255).
- `multiply` with scale.
- `bitwise_and/or/xor` mask variants — read two grayscale fixtures and
  verify mask-restricted output.
- `mean` returns the right length for grayscale (4-tuple, zeros in
  channels 1..3).
- `copy_image` produces an independent array — modify the original
  via `bitwise_not` and check the copy is unchanged.
- All property predicates in check mode (success + failure with
  `not(...)`).
- `dtype` in query and check mode with a `numpy` dtype.

### Python unit tests

`tests/test_opencv_infra.py`:

- Lazy import: `import clausal.modules.opencv as m` does not import
  `cv2` until `m._cv()` is called.
- `_CONSTANT_NAMES` `__getattr__` raises `AttributeError` for unknown
  names (so introspection tools work correctly).
- Handle registry: `alloc(obj)` returns distinct integers across
  threads; `lookup` returns the right object; `release` removes the
  entry and `lookup` then raises `KeyError`.
- `free/1` calls `.release()` on objects that have it and a no-op on
  those that don't — using a mock object.

### Test fixtures

Two tiny PNG files committed as binary blobs:

- `fixtures/tiny_rgb.png` — 4×4 BGR image, mix of pixel values
- `fixtures/tiny_gray.png` — 4×4 grayscale image

These can be generated once and checked in:

```python
import cv2, numpy as np
rgb = (np.arange(48, dtype=np.uint8).reshape(4, 4, 3))
cv2.imwrite("fixtures/tiny_rgb.png", rgb)
gray = (np.arange(16, dtype=np.uint8).reshape(4, 4))
cv2.imwrite("fixtures/tiny_gray.png", gray)
```

---

## Docs

`packages/clausal-opencv/docs/opencv.md`:

- One-paragraph intro: "OpenCV is a computer-vision library. This
  module exposes its core image data type (numpy.ndarray with BGR
  layout) along with I/O, properties, arithmetic, and bitwise
  operations as Clausal predicates."
- **Two prominent callouts**:
  - **BGR not RGB**: `imread` returns BGR-layout arrays by default.
    Convert with `cvt_color(IMG, COLOR_BGR2RGB, RGB)` (Phase 2) before
    feeding to matplotlib or PIL.
  - **Shape vs size**: `shape/2` returns `[H, W, C]` (numpy
    convention); `size/2` returns `[W, H]` (OpenCV convention).
- Each predicate group with a worked example. Every example
  appears verbatim in the `.clausal` test file.

---

## Issues

### 1. ALL-CAPS constants are logic variables — FIXED

Clausal parses any all-caps identifier as a logic variable (see
`clausal/templating/term_rewriting.py:_is_logic_var_name`). The plan
originally proposed re-exporting `IMREAD_COLOR`, `BORDER_REFLECT`,
etc. directly from `py.opencv`, but `imread(PATH, IMREAD_COLOR, IMG)`
in a goal body binds `IMREAD_COLOR` to a fresh Var instead of looking
up the int 1. **Fixed** by exporting constants under **lowercase**
aliases — `imread_color`, `border_reflect`, etc. — with the upstream
cv2 attribute name preserved in the alias map. Documented in
`docs/opencv.md`. This propagates to **every** later phase: all
constant lists in phase plans 2–10 must be lowercase. The phase
files will need a doc pass.

### 2. `_property_2` from `_helpers` uses `==`, not `unify` — FIXED locally

The shared helper's check mode uses `actual == v`, which fails when
the bound value contains unbound Vars inside a list
(e.g. `shape(IMG, [_, _, 3])` → the right-hand list has anonymous
Vars). **Fixed** by defining a local `_property_2` in `opencv.py`
that uses `unify` in both modes with a `_values_equal` fallback for
array-typed operands (the same pattern as `_bidir_2` in
`_helpers.py`). The helper-level `_property_2` is unchanged; this
is an opencv-specific dispatch.

### 3. `cv2.minMaxLoc` requires a single-channel image — DOCUMENTED

`min_max_loc(IMG, R)` raises on multi-channel images. Tests use a
grayscale fixture for equality-via-`min_max_loc` checks; the docs
recommend `split` (Phase 2) before `min_max_loc` for color images.

### 4. `is` does not reduce arithmetic when the RHS contains Vars bound to ints — DOCUMENTED

Calling `MULT is H * W * C` where `H`, `W`, `C` were bound to ints
by a previous `shape/2` unification leaves `MULT` bound to the AST
node `Mult(...)`, not the reduced int `48`. Compare to `N is 3 * 4 * 5`,
which does reduce because the RHS is constant. The test was rewritten
to use a literal shape pattern (`shape(IMG, [4, 4, 3])`) and a literal
element count (`element_count(IMG, 48)`). This is a Clausal-level
behaviour, not an opencv issue; downstream phases that compute on
shape-extracted dims should compute in Python via `++()` or
restructure to feed concrete literals.

### 5. cv2 bootstrap is fragile across `del sys.modules['cv2']` — DOCUMENTED

Calling `del sys.modules['cv2']` then re-importing cv2 leaves
`cv2.dnn` in a state where `cv2.dnn.DictValue` is missing, which
breaks subsequent cv2 imports for the rest of the test session.
**The original lazy-import test was rewritten** to set `m._cv2 = None`
on the wrapper module directly rather than tampering with
`sys.modules`. This still verifies the lazy-import guard works; it
doesn't break cv2.

### 6. Editable install of clausal-opencv conflicts with cwd-on-sys.path — WORKED AROUND

setuptools' editable-install meta-path finder maps
`clausal.modules` to the package's source tree, but the core
`clausal.modules.__init__.py` only extends `__path__` with
site-packages locations. Running Python from
`packages/clausal-opencv/` adds the package source to `sys.path`,
which then shadows the site-packages `clausal.modules.opencv` with
the package source's `opencv.py` — which then can't find
`clausal.modules.py._helpers` because the source tree doesn't
include the core's `py/` subdirectory. **Worked around** by
installing the package non-editably (`pip install`) and
symlinking the two files into site-packages for dev iteration:

```
ln -sf $SRC/opencv.py             site-packages/clausal/modules/opencv.py
ln -sf $SRC/_opencv_handles.py    site-packages/clausal/modules/_opencv_handles.py
```

The proper fix is to update core clausal's
`clausal/modules/__init__.py` to extend `__path__` with editable-source
locations of installed packages, but that touches the core distribution
and is out of scope for Phase 1.
