# Phase 2 — Color Conversions

Color-space conversion is the most commonly-used surface of OpenCV
after I/O. This phase ships:

1. `cvt_color/3` — the workhorse predicate, parameterised by integer
   COLOR_* code.
2. `cvt_color_named/3` — the same operation keyed by a string name
   (`"BGR2GRAY"`) for users who keep colour codes in config files.
3. `color_code/2` — the bidirectional name ↔ code registry.
4. `channels/2` — bidirectional `split` / `merge` pair.

**Files to create / modify:**

- `packages/clausal-opencv/clausal/modules/opencv_color.py` (new)
- `packages/clausal-opencv/clausal/modules/opencv.py` — extend the
  `_CONSTANT_NAMES` frozenset with the `COLOR_*` constants.
- `packages/clausal-opencv/tests/clausal_files/opencv_phase2_color.clausal`
- `packages/clausal-opencv/docs/opencv_color.md`

---

## Predicates

| Name | Arity | Modes | Tier | Description |
|---|---|---|---|---|
| `cvt_color` | `/3` | `(+img, +code, -out)` | 1 | `cv2.cvtColor(img, code)` |
| `cvt_color_named` | `/3` | `(+img, +name, -out)` | 1 | Same, keyed by string |
| `color_code` | `/2` | `(+name, -code)`, `(-name, +code)`, `(-name, -code)` | 2 | Name ↔ code registry |
| `channels` | `/2` | `(+img, -list)` / `(-img, +list)` | 1 | `split` ↔ `merge` |

---

## Context and Reference Patterns

### Imports

```python
# packages/clausal-opencv/clausal/modules/opencv_color.py
from clausal.modules.py._helpers import _pred, _pure, _bidir_2, _fact_table_2
from clausal.modules.opencv import _cv
```

### `cvt_color/3`

Standard `_pure` dispatch:

```python
cvt_color = _pred("cvt_color",
    (3, _pure(lambda img, code: _cv().cvtColor(img, int(code)))),
)
```

### `color_code/2` (registry)

Uses `_fact_table_2` from `clausal/modules/py/_helpers.py:421`. The
fact list is built once on first use by introspecting `cv2` for any
attribute starting with `COLOR_` whose value is an integer:

```python
def _build_color_facts():
    cv = _cv()
    facts = []
    for name in dir(cv):
        if not name.startswith("COLOR_"):
            continue
        val = getattr(cv, name)
        if isinstance(val, int):
            # Lowercase short name — strip "COLOR_" prefix
            short = name[len("COLOR_"):].lower()
            facts.append((short, val))
    return facts

color_code = _pred("color_code",
    (2, _fact_table_2(_build_color_facts)),
)
```

The short name (`"bgr2gray"` instead of `"COLOR_BGR2GRAY"`) is the
key. The full uppercase constant is still available via the
`from py.opencv import COLOR_BGR2GRAY` constant export.

### `cvt_color_named/3`

Uses the same registry, looking up the integer code from the name
before calling `cvtColor`:

```python
def _cvt_named(img, name):
    facts = _build_color_facts()
    table = dict(facts)
    code = table.get(name)
    if code is None:
        raise KeyError(f"Unknown color code name: {name!r}")
    return _cv().cvtColor(img, code)

cvt_color_named = _pred("cvt_color_named",
    (3, _pure(_cvt_named)),
)
```

For efficiency the lookup table should be cached at module load.
Reuse the cache inside `_fact_table_2`'s closure if possible, or keep
a module-level dict initialised on first call.

### `channels/2` (bidirectional)

Uses `_bidir_2` from `clausal/modules/py/_helpers.py:147`:

```python
def _split(img):
    return list(_cv().split(img))

def _merge(channels):
    return _cv().merge(channels)

channels = _pred("channels",
    (2, _bidir_2(_split, _merge)),
)
```

Modes:

- `(+img, -list)`: forward — splits the image into a list of
  single-channel arrays.
- `(-img, +list)`: backward — merges the list back into a multi-channel
  image.
- `(+img, +list)`: check — splits the image, compares element-wise to
  the bound list. The shared `_values_equal` fallback in
  `_helpers.py:116` handles array equality correctly.

### Constants to add to `_CONSTANT_NAMES`

The Phase 2 update to `opencv.py` adds the most-used COLOR_* constants
directly so users don't have to look them up through the registry:

```python
# Extends Phase 1's frozenset:
_CONSTANT_NAMES |= frozenset([
    # Common BGR ↔ * conversions
    "COLOR_BGR2GRAY", "COLOR_GRAY2BGR",
    "COLOR_BGR2RGB",  "COLOR_RGB2BGR",
    "COLOR_BGR2HSV",  "COLOR_HSV2BGR",
    "COLOR_BGR2HLS",  "COLOR_HLS2BGR",
    "COLOR_BGR2LAB",  "COLOR_LAB2BGR",
    "COLOR_BGR2LUV",  "COLOR_LUV2BGR",
    "COLOR_BGR2YCRCB", "COLOR_YCRCB2BGR",
    "COLOR_BGR2XYZ",  "COLOR_XYZ2BGR",
    "COLOR_BGR2YUV",  "COLOR_YUV2BGR",
    # Common RGBA ↔ * conversions
    "COLOR_BGRA2BGR", "COLOR_BGR2BGRA",
    "COLOR_RGBA2RGB", "COLOR_RGB2RGBA",
    # Bayer demosaic (cameras)
    "COLOR_BAYER_BG2BGR", "COLOR_BAYER_GB2BGR",
    "COLOR_BAYER_RG2BGR", "COLOR_BAYER_GR2BGR",
])
```

Users importing `COLOR_BGR2GRAY` from `py.opencv` get the integer
constant directly — no `++()`, no registry lookup. The full registry
remains the right tool when the colour code is data, not code.

---

## Example Usage

```clausal
-import_from(py.opencv, [
    imread, shape, channels_count, is_grayscale, is_color, absdiff,
    min_max_loc, IMREAD_COLOR,
    COLOR_BGR2GRAY, COLOR_GRAY2BGR, COLOR_BGR2HSV, COLOR_HSV2BGR
])
-import_from(py.opencv_color, [
    cvt_color, cvt_color_named, color_code, channels
])

Test("BGR to grayscale by code") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, BGR),
    cvt_color(BGR, COLOR_BGR2GRAY, GRAY),
    is_grayscale(GRAY)
)

Test("BGR to grayscale by name") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, BGR),
    cvt_color_named(BGR, "bgr2gray", GRAY),
    is_grayscale(GRAY)
)

Test("color_code lookup name to int") <- (
    color_code("bgr2gray", CODE),
    CODE = COLOR_BGR2GRAY
)

Test("color_code lookup int to name") <- (
    color_code(NAME, COLOR_BGR2HSV),
    NAME = "bgr2hsv"
)

Test("findall over color_code yields many names") <- (
    findall(NAME, color_code(NAME, _), NAMES),
    length(NAMES, N),
    N > 100
)

Test("HSV roundtrip is approximately identity") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, BGR),
    cvt_color(BGR, COLOR_BGR2HSV, HSV),
    cvt_color(HSV, COLOR_HSV2BGR, BGR2),
    absdiff(BGR, BGR2, D),
    min_max_loc(D, R),
    R is ("min_max", 0.0, MAX, _, _),
    MAX =< 2.0
)

Test("channels split then merge is identity") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, BGR),
    channels(BGR, [B, G, R]),
    channels(BGR2, [B, G, R]),
    absdiff(BGR, BGR2, D),
    min_max_loc(D, ("min_max", 0.0, 0.0, _, _))
)

Test("channels backward yields 3-channel image") <- (
    imread("fixtures/tiny_rgb.png", IMREAD_COLOR, BGR),
    channels(BGR, [B, G, R]),
    channels(MERGED, [B, G, R]),
    channels_count(MERGED, 3)
)

Test("gray to BGR replicates channel") <- (
    imread("fixtures/tiny_gray.png", _, GRAY),
    cvt_color(GRAY, COLOR_GRAY2BGR, BGR),
    is_color(BGR),
    channels(BGR, [B, G, R]),
    absdiff(B, G, D1),
    min_max_loc(D1, ("min_max", 0.0, 0.0, _, _)),
    absdiff(G, R, D2),
    min_max_loc(D2, ("min_max", 0.0, 0.0, _, _))
)
```

---

## Tests

### `.clausal` integration tests

`tests/clausal_files/opencv_phase2_color.clausal`:

- All Test cases above.
- A representative sample of color codes through `cvt_color_named`:
  `bgr2hsv`, `bgr2lab`, `bgr2yuv`, `gray2bgr`.
- Failure case: `cvt_color_named(IMG, "not_a_real_code", _)` fails.
- Failure case: `cvt_color(IMG, 99999, _)` fails (invalid integer code).
- Registry enumeration: `findall(N, color_code(N, _), NS)` returns
  more than 100 entries.

### Python unit tests

None additional — the registry caching logic is well exercised by the
`.clausal` enumeration test, and `_fact_table_2` is already covered
by torch's tests.

---

## Docs

`packages/clausal-opencv/docs/opencv_color.md`:

- Intro: "OpenCV defines colour-space conversion through `cvtColor` and
  a large registry of `COLOR_*` integer codes. This module exposes both
  the integer-code (`cvt_color/3`) and string-name (`cvt_color_named/3`)
  forms, plus a bidirectional registry (`color_code/2`)."
- Worked examples for each predicate.
- Note on the **BGR convention** — refer back to `opencv.md`.
- Note that `channels/2` is bidirectional and self-inverse (split then
  merge is identity).
- Note on naming convention: registry names are lowercase
  (`"bgr2gray"`), while the integer-constant aliases are full
  uppercase (`COLOR_BGR2GRAY`).

---

## Issues

### 1. Constants use lowercase aliases — INHERITED FROM PHASE 1

All `COLOR_*` constants exported from `opencv.py` use lowercase
aliases (`color_bgr2gray`, `color_bgr2hsv`, …). The registry
`color_code/2` uses lowercase short names (`"bgr2gray"`, `"bgr2hsv"`)
keyed off the same convention. This is forced by Clausal's
ALL-CAPS-is-variable rule; see Phase 1 Issue 1 for the underlying
reason. The plan's predicate catalogue and examples were drafted with
upstream cv2 spelling; the implementation and docs use lowercase.

### 2. Multiple cv2 constants share the same int value — DOCUMENTED

The registry-build helper observes that several `COLOR_*` constants
are aliases for the same integer (e.g. `COLOR_BGR2RGB` and
`COLOR_RGB2BGR` have the same int because the operation is
symmetric). To make reverse lookup `(-NAME, +CODE)` deterministic,
the first short-name encountered for each int wins. Sorting by
short-name before building the map makes the choice reproducible.
There's a small ergonomics cost: reverse lookup may return a name
that's a synonym of what the user expected, but never one that
points to a different operation. Tests verify this with `bgr2hsv`
specifically (no known same-int alias).

### 3. `channels/2` backward mode — VERIFIED

`channels(MERGED, [B, G, R])` with `MERGED` unbound calls
`cv2.merge([B, G, R])`. cv2 returns a new ndarray, which unifies
into `MERGED`. The check mode `(+IMG, +LIST)` works through the
shared `_bidir_2` fallback — `unify` raises on element-wise array
comparison and `_values_equal` reduces via `.all()`. No special
handling required.
