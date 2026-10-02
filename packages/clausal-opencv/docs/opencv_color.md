# `opencv_color` — Color-space conversions

OpenCV defines colour-space conversion through `cv2.cvtColor` and a
large registry of `COLOR_*` integer codes (hundreds of pairwise
conversions between BGR, RGB, grayscale, HSV, HLS, Lab, Luv, YCrCb,
XYZ, YUV, and Bayer demosaic patterns).

This module exposes both the integer-code (`cvt_color/3`) and
string-name (`cvt_color_named/3`) forms, plus a bidirectional name ↔
code registry (`color_code/2`) and a single `channels/2` predicate
that collapses `cv2.split` / `cv2.merge`.

```clausal
-import_from(opencv, [color_bgr2gray, color_bgr2hsv, color_hsv2bgr])
-import_from(opencv_color, [cvt_color, cvt_color_named, color_code, channels])
```

## Predicates

| Predicate | Arity | Description |
|---|---|---|
| `cvt_color(IMG, CODE, OUT)` | /3 | `cv2.cvtColor` with an integer code |
| `cvt_color_named(IMG, NAME, OUT)` | /3 | `cv2.cvtColor` keyed by lowercase short name |
| `color_code(NAME, CODE)` | /2 | Bidirectional name ↔ int registry |
| `channels(IMG, LIST)` | /2 | Bidirectional `split` ↔ `merge` |

## Name convention

The short names are lowercase versions of the upstream `cv2.COLOR_*`
constants with the `COLOR_` prefix stripped:

| cv2 constant | clausal short name |
|---|---|
| `cv2.COLOR_BGR2GRAY` | `"bgr2gray"` |
| `cv2.COLOR_BGR2HSV` | `"bgr2hsv"` |
| `cv2.COLOR_BAYER_BG2BGR` | `"bayer_bg2bgr"` |

The same lowercase form is reachable as a top-level Clausal constant
prefixed with `color_`:

| cv2 constant | clausal constant |
|---|---|
| `cv2.COLOR_BGR2GRAY` | `color_bgr2gray` |
| `cv2.COLOR_BGR2HSV` | `color_bgr2hsv` |

Why two surfaces? Because the workflow differs:

- **Constant**: known at write-time, used directly as a positional
  argument to `cvt_color/3`. Has IDE-style discovery via the import
  list.
- **Registry**: name-as-data, used when the colour code comes from a
  config file or user input. Look it up at runtime via `color_code/2`
  and pass to `cvt_color/3`, or skip the lookup and pass the name
  directly to `cvt_color_named/3`.

Only the most-used pairs (BGR↔gray, BGR↔RGB/HSV/HLS/Lab/Luv/YCrCb/
XYZ/YUV, BGRA↔BGR, RGBA↔RGB, common Bayer patterns) are exported as
named constants. The full set of ~150 conversions is always reachable
through `color_code/2`.

## Worked examples

The examples below are exact copies of the `.clausal` integration
tests under `tests/fixtures/opencv_phase2_color.seam`.

### BGR → grayscale by code

```clausal
imread("photo.png", imread_color, BGR),
cvt_color(BGR, color_bgr2gray, GRAY),
is_grayscale(GRAY)
```

### BGR → grayscale by name

```clausal
imread("photo.png", imread_color, BGR),
cvt_color_named(BGR, "bgr2gray", GRAY),
is_grayscale(GRAY)
```

### Registry lookup name → code

```clausal
color_code("bgr2gray", CODE),
CODE == color_bgr2gray
```

### Registry reverse lookup code → name

```clausal
color_code(NAME, color_bgr2hsv),
NAME == "bgr2hsv"
```

### Enumerate all available color codes

```clausal
findall(N, color_code(N, _), NAMES),
length(NAMES, K),
K >= 100
```

### Split a BGR image into channels

```clausal
imread("photo.png", imread_color, BGR),
channels(BGR, [B, G, R]),
shape(B, [_, _])  % each channel is a 2-D array
```

### Merge channels back into a multi-channel image

```clausal
% Backward mode: given a channel list, produce a multi-channel image
channels(MERGED, [B, G, R]),
channels_count(MERGED, 3)
```

### gray → BGR replicates a single channel

```clausal
imread("photo.png", imread_grayscale, GRAY),
cvt_color(GRAY, color_gray2bgr, BGR),
channels(BGR, [B, G, R]),
absdiff(B, G, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### HSV roundtrip is approximately identity

```clausal
imread("photo.png", imread_color, BGR),
cvt_color(BGR, color_bgr2hsv, HSV),
cvt_color(HSV, color_hsv2bgr, BGR2),
channels(BGR, [B0, G0, R0]),
channels(BGR2, [B1, G1, R1]),
absdiff(B0, B1, D),
min_max_loc(D, ("min_max", _, MAX, _, _)),
MAX <= 2.0
```

## See also

- [`opencv`](opencv.md) — the BGR/shape conventions documented in
  the core module apply to every cvtColor target. BGR is the default
  channel order; use `color_bgr2rgb` before handing an image to
  matplotlib or PIL.
- [`opencv_imgproc`](opencv_imgproc.md) (Phase 3) — filtering and
  morphology, which often follow a colour conversion to grayscale.
