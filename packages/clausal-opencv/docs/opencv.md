# `opencv` — OpenCV core, I/O, properties, arithmetic

The opencv module exposes the central image data type (a NumPy
`ndarray` with BGR channel order) along with I/O, property queries,
arithmetic, bitwise operations, reductions, and whole-image
transforms.

```seam
-import_from(opencv, [
    imread, shape, channels_count, is_color, IMG_COLOR  # see Conventions
])
```

## Conventions

### BGR, not RGB

`imread` returns BGR-ordered arrays by default. If you display an
image with matplotlib or feed it to PIL, convert with
`cvt_color(IMG, COLOR_BGR2RGB, RGB)` (Phase 2) first.

### Shape vs size

The two property predicates report image geometry in different
orders, matching the upstream library:

- `shape/2` returns the **NumPy** shape: `[H, W, C]` for a color
  image, `[H, W]` for grayscale.
- `size/2` returns the **OpenCV** size: `[W, H]`. Functions like
  `resize` and `warp_affine` (Phase 5) take size in this order.

### Lowercase constants

Constants from `cv2` are exported under **lowercase** aliases —
`imread_color`, `norm_l2`, `cv_8u` — *not* the upstream all-caps
form. This is forced: seam source treats every all-caps identifier as a
logic variable, so `IMREAD_COLOR` in a goal body would be parsed as
a fresh `Var`, not a constant lookup. The lowercase alias resolves
unambiguously and preserves the cv2 mapping (`imread_color` ↔
`cv2.IMREAD_COLOR`).

If you need the upstream constant directly, use `++cv2.IMREAD_COLOR`.

### `dst=` argument always omitted

OpenCV functions accept an optional `dst=` array to write into. The
wrapper never passes it — each call allocates a fresh output array.
This is what makes the predicates safe to use inside a relational
pipeline: backtracking abandons the output without corrupting the
input.

## I/O

| Predicate | Arity | Description |
|---|---|---|
| `imread(PATH, IMG)` | /2 | Read with default `imread_color` |
| `imread(PATH, FLAG, IMG)` | /3 | Read with explicit flag |
| `imwrite(PATH, IMG)` | /2 | Write to file |
| `imwrite(PATH, IMG, PARAMS)` | /3 | Write with flat `[flag, value, ...]` params |
| `image_encoded(IMG, EXT, BUF)` | /3 | Bidirectional encode/decode |

`image_encoded/3` is bidirectional:

- `(+IMG, +EXT, -BUF)` — encode IMG as bytes in format EXT (`.png`, `.jpg`, ...)
- `(-IMG, +EXT, +BUF)` — decode BUF back into an image

```seam
test("encode a PNG and decode it back") <- (
    imread("photo.png", imread_color, IMG),
    image_encoded(IMG, ".png", BUF),
    image_encoded(IMG2, ".png", BUF),
    shape(IMG, S),
    shape(IMG2, S)
)
```

`imread/2,3` **fails** (rather than returning a null image) if the
file is missing or unreadable. This makes file-existence checks fall
out of the predicate naturally:

```seam
load_or_warn(PATH, IMG) <- (
    imread(PATH, imread_color, IMG)
)
load_or_warn(PATH, _) <- (
    not imread(PATH, imread_color, _),
    print("skipping unreadable file: "), print(PATH)
)
```

## Properties

All property predicates are multi-mode — query when the second arg is
unbound, check when it's bound.

| Predicate | Arity | Query mode | Check mode |
|---|---|---|---|
| `shape(IMG, S)` | /2 | `(+,-)` returns `[H, W, C]` or `[H, W]` | `(+,+)` |
| `dtype(IMG, D)` | /2 | `(+,-)` returns numpy dtype | `(+,+)` |
| `channels_count(IMG, N)` | /2 | `(+,-)` returns 1 for 2-D, `shape[2]` for 3-D | `(+,+)` |
| `size(IMG, [W, H])` | /2 | `(+,-)` returns `[W, H]` (swapped from `shape`) | `(+,+)` |
| `element_count(IMG, N)` | /2 | `(+,-)` returns `img.size` | check mode also works |
| `is_grayscale(IMG)` | /1 | check: succeeds iff 2-D | — |
| `is_color(IMG)` | /1 | check: succeeds iff 3-D with 3 channels | — |
| `is_uint8(IMG)` | /1 | check: succeeds iff `dtype == uint8` | — |

Partial-pattern check is supported: `shape(IMG, [_, _, 3])` succeeds
iff IMG has 3 channels regardless of H and W.

```seam
# Match images that are at least 100x100
big_enough(IMG) <- (
    shape(IMG, [H, W, _]),
    H >= 100,
    W >= 100
)
```

## Arithmetic

All arithmetic is element-wise, saturated where the upstream `cv2`
function saturates. Pass two arrays of matching shape.

| Predicate | Arity | Description |
|---|---|---|
| `add(A, B, C)` | /3 | Saturated add |
| `subtract(A, B, C)` | /3 | Saturated subtract |
| `multiply(A, B, C)` | /3 | Element-wise multiply |
| `multiply(A, B, SCALE, C)` | /4 | Same with output scale |
| `divide(A, B, C)` | /3 | Element-wise divide |
| `divide(A, B, SCALE, C)` | /4 | Same with output scale |
| `absdiff(A, B, C)` | /3 | `|a - b|`, channel-wise |
| `bitwise_and(A, B, C)` | /3 | |
| `bitwise_and(A, B, MASK, C)` | /4 | Masked variant |
| `bitwise_or(A, B, C)` | /3 | |
| `bitwise_or(A, B, MASK, C)` | /4 | |
| `bitwise_xor(A, B, C)` | /3 | |
| `bitwise_xor(A, B, MASK, C)` | /4 | |
| `bitwise_not(A, C)` | /2 | |
| `bitwise_not(A, MASK, C)` | /3 | |
| `min(A, B, C)` | /3 | Element-wise min |
| `max(A, B, C)` | /3 | Element-wise max |

## Reductions

| Predicate | Arity | Description |
|---|---|---|
| `mean(IMG, M)` | /2 | Returns a 4-tuple `[B, G, R, A]` (zero in unused channels) |
| `mean(IMG, MASK, M)` | /3 | Same, restricted to MASK |
| `min_max_loc(IMG, R)` | /2 | `R = ("min_max", MIN_V, MAX_V, MIN_LOC, MAX_LOC)`, **single-channel only** |
| `min_max_loc(IMG, MASK, R)` | /3 | Same with MASK |

`min_max_loc` requires a single-channel image. For multi-channel
images, `split` (Phase 2) into individual channels first, or use
`mean` for an aggregate.

```seam
# How dark is the darkest pixel?
darkest(GRAY_IMG, MIN_V) <- (
    is_grayscale(GRAY_IMG),
    min_max_loc(GRAY_IMG, ("min_max", MIN_V, _, _, _))
)
```

## Whole-image transforms

| Predicate | Arity | Description |
|---|---|---|
| `flip(IMG, CODE, OUT)` | /3 | `CODE`: 0 = vertical, 1 = horizontal, -1 = both. Self-inverse at fixed code. |
| `transpose(IMG, OUT)` | /2 | Swap H and W (self-inverse) |
| `copy_image(IMG, COPY)` | /2 | Independent copy — useful before drawing in Phase 6 |

## Handle lifecycle

| Predicate | Arity | Description |
|---|---|---|
| `free(HANDLE)` | /1 | Release a handle allocated by later-phase predicates (detectors, capture devices, …) and remove it from the registry. Fails on unknown handles. |

`free/1` is part of Phase 1 because the same registry is shared by
every later phase that introduces a handle-based object (Phases 7, 8,
10).

## Constants

Listed under their lowercase aliases. The upstream `cv2` attribute
name is given in parentheses.

### Image read flags

`imread_color` (`IMREAD_COLOR`), `imread_grayscale`
(`IMREAD_GRAYSCALE`), `imread_unchanged` (`IMREAD_UNCHANGED`),
`imread_anydepth`, `imread_anycolor`, and the
`imread_reduced_{grayscale,color}_{2,4,8}` family.

### Image write params

`imwrite_jpeg_quality`, `imwrite_png_compression`,
`imwrite_webp_quality`, `imwrite_tiff_compression`.

### Data types

`cv_8u`, `cv_8s`, `cv_16u`, `cv_16s`, `cv_32s`, `cv_32f`, `cv_64f`.

### Norm types (used by Phase 7 matchers)

`norm_inf`, `norm_l1`, `norm_l2`, `norm_l2sqr`, `norm_hamming`,
`norm_hamming2`, `norm_minmax`.

## Worked examples

The examples below are exact copies of the `.seam` integration
tests under `tests/fixtures/opencv_phase1_core.seam`.

### Read a color image and check structure

```seam
imread("photo.png", imread_color, IMG),
shape(IMG, [_, _, 3]),
is_color(IMG)
```

### Roundtrip through an in-memory PNG buffer

```seam
imread("photo.png", imread_color, IMG),
image_encoded(IMG, ".png", BUF),
image_encoded(IMG2, ".png", BUF),
shape(IMG, S),
shape(IMG2, S)
```

### Verify an image is its own absdiff-zero

```seam
imread("photo.png", imread_grayscale, IMG),
absdiff(IMG, IMG, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### Verify `bitwise_not` is involutive (grayscale)

```seam
imread("photo.png", imread_grayscale, IMG),
bitwise_not(IMG, INV),
bitwise_not(INV, INV2),
absdiff(IMG, INV2, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### Vertical flip is its own inverse

```seam
imread("photo.png", imread_grayscale, IMG),
flip(IMG, 0, F),
flip(F, 0, F2),
absdiff(IMG, F2, D),
min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
```

### Convert OpenCV size to NumPy shape (and back)

```seam
imread("photo.png", imread_color, IMG),
shape(IMG, [H, W, _]),
size(IMG, [W, H])
```
