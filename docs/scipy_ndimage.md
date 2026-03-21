# scipy.ndimage — N-dimensional Image Processing

The `scipy_ndimage` module wraps [`scipy.ndimage`](https://docs.scipy.org/doc/scipy/reference/ndimage.html) as Clausal predicates. It covers smoothing filters, convolution, morphological operations, connected-component labelling, geometric transforms, and measurement functions.

---

## Import

```
-import_from(scipy_ndimage, [GaussianFilter, Label, Zoom, ...])
```

Or via the canonical `py.*` path:

```
-import_from(py.scipy_ndimage, [GaussianFilter, ...])
```

---

## Tier

All predicates are **Tier 1 — pure functions**: NumPy array in, result directly in `RESULT`. No result dicts that need a `ResultGet` accessor (except `Label`, which returns a plain Python dict with named keys you can access directly).

---

## Naming conventions

Predicates are imported from `scipy_ndimage`, so there is no module prefix in the name — each predicate is just the operation name in `TitleCase`.

| scipy function | Clausal predicate |
|---|---|
| `gaussian_filter` | `GaussianFilter` |
| `uniform_filter` | `UniformFilter` |
| `median_filter` | `MedianFilter` |
| `convolve` | `Convolve` |
| `label` | `Label` |
| `binary_erosion` | `BinaryErosion` |
| `binary_dilation` | `BinaryDilation` |
| `binary_opening` | `BinaryOpening` |
| `binary_closing` | `BinaryClosing` |
| `zoom` | `Zoom` |
| `rotate` | `Rotate` |
| `shift` | `Shift` |
| `find_objects` | `FindObjects` |
| `center_of_mass` | `CenterOfMass` |

---

## Predicate catalogue

### Smoothing filters

```
GaussianFilter(INPUT, SIGMA, RESULT)
    Gaussian smoothing of INPUT with standard deviation SIGMA.
    INPUT:  N-D real array
    SIGMA:  scalar (same sigma for all axes) or sequence of one sigma per axis
    RESULT: smoothed array of the same shape as INPUT

UniformFilter(INPUT, RESULT)
    Box (uniform/mean) filter with default size 3.
    RESULT: filtered array of the same shape as INPUT

UniformFilter(INPUT, SIZE, RESULT)
    SIZE: integer side length of the box kernel (same for all axes).

MedianFilter(INPUT, SIZE, RESULT)
    Median filter of INPUT using a box of side SIZE.
    INPUT:  N-D real array
    SIZE:   integer (same for all axes) or sequence of one size per axis
    RESULT: filtered array of the same shape as INPUT
```

Example — smooth a noisy 1-D signal:

```
-import_from(scipy_ndimage, [GaussianFilter])

SmoothSignal(NOISY_, SMOOTHED_) <- (
    GaussianFilter(NOISY_, ++(2.0), SMOOTHED_)
)
```

---

### Convolution

```
Convolve(INPUT, WEIGHTS, RESULT)
    N-D discrete convolution of INPUT with kernel WEIGHTS.
    INPUT:    N-D real array
    WEIGHTS:  kernel array (must have the same number of dimensions as INPUT)
    RESULT:   convolved array of the same shape as INPUT
    Note: boundary is handled with reflect mode by default.
```

Example — edge detection with a simple difference kernel:

```
-import_from(scipy_ndimage, [Convolve])

EdgeDetect(SIGNAL_, EDGES_) <- (
    KERNEL_ is ++([-1.0, 0.0, 1.0]) and
    Convolve(SIGNAL_, KERNEL_, EDGES_)
)
```

---

### Connected-component labelling

```
Label(INPUT, RESULT)
    Label connected components of non-zero values in INPUT.
    INPUT:  N-D integer or boolean array (non-zero = foreground)
    RESULT: dict with two keys:
        'label_array'  — integer array of the same shape, each component
                         assigned a unique positive integer; background = 0
        'num_features' — total number of labelled components (integer)
```

Example — count blobs in a binary image:

```
-import_from(scipy_ndimage, [Label])

CountBlobs(IMAGE_, COUNT_) <- (
    Label(IMAGE_, LABELED_) and
    COUNT_ is ++(int(LABELED_['num_features']))
)
```

---

### Morphological operations

All four predicates operate on boolean (or 0/1 integer) arrays and use the
default 3×3 (or 3-point in 1-D) structuring element.

```
BinaryErosion(INPUT, RESULT)
    Erode: keep only True pixels whose entire neighbourhood is True.
    Shrinks foreground objects; removes isolated pixels.

BinaryDilation(INPUT, RESULT)
    Dilate: set True any pixel adjacent to a True pixel.
    Expands foreground objects.

BinaryOpening(INPUT, RESULT)
    Open = erosion followed by dilation.
    Removes small isolated foreground regions; smooths object boundaries.

BinaryClosing(INPUT, RESULT)
    Close = dilation followed by erosion.
    Fills small holes and gaps inside foreground regions.
```

Example — remove noise then fill gaps in a binary mask:

```
-import_from(scipy_ndimage, [BinaryOpening, BinaryClosing])

CleanMask(RAW_MASK_, CLEAN_) <- (
    BinaryOpening(RAW_MASK_, OPENED_) and
    BinaryClosing(OPENED_, CLEAN_)
)
```

---

### Geometric transforms

```
Zoom(INPUT, ZOOM, RESULT)
    Rescale INPUT by the given zoom factor.
    INPUT:  N-D array
    ZOOM:   scalar (same factor for all axes) or sequence of one factor per axis
    RESULT: rescaled array; shape is round(shape * zoom) per axis

Rotate(INPUT, ANGLE, RESULT)
    Rotate a 2-D array by ANGLE degrees (counter-clockwise).
    INPUT:  2-D array
    ANGLE:  rotation angle in degrees
    RESULT: rotated array; output shape is chosen to contain the full rotated
            image (reshape=True by default); background filled with 0.0

Shift(INPUT, SHIFT, RESULT)
    Shift INPUT by the given offset.
    INPUT:  N-D array
    SHIFT:  scalar (same for all axes) or sequence of one offset per axis
    RESULT: shifted array of the same shape; regions shifted out of bounds are
            filled with 0.0 (constant mode)
```

Example — centre-crop after zoom:

```
-import_from(scipy_ndimage, [Zoom])

ZoomImage(IMAGE_, FACTOR_, ZOOMED_) <- (
    Zoom(IMAGE_, FACTOR_, ZOOMED_)
)
```

---

### Measurement

```
FindObjects(INPUT, RESULT)
    Find bounding-box slices for each labelled component in INPUT.
    INPUT:  integer-labelled array (e.g., the 'label_array' from Label)
    RESULT: list of slice-tuple bounding boxes, one per component;
            RESULT[i] is a tuple of slice objects covering component i+1;
            components whose label is absent give None entries

CenterOfMass(INPUT, RESULT)
    Compute the centre of mass of INPUT.
    INPUT:  N-D real array (values used as weights)
    RESULT: tuple of length N giving the centre-of-mass coordinate per axis
```

Example — find the centroid of a blob:

```
-import_from(scipy_ndimage, [Label, CenterOfMass])

BlobCentroid(BINARY_IMAGE_, CENTROID_) <- (
    Label(BINARY_IMAGE_, LABELED_) and
    CenterOfMass(BINARY_IMAGE_, CENTROID_)
)
```

---

## Complete examples

### Gaussian smoothing and edge detection

```
-import_from(scipy_ndimage, [GaussianFilter, Convolve])

ProcessSignal(NOISY_, SMOOTHED_, EDGES_) <- (
    GaussianFilter(NOISY_, ++(1.5), SMOOTHED_) and
    KERNEL_ is ++([-1.0, 0.0, 1.0]) and
    Convolve(SMOOTHED_, KERNEL_, EDGES_)
)
```

### Label and count connected components

```
-import_from(scipy_ndimage, [Label, FindObjects])

LabelAndLocate(BINARY_, COUNT_, REGIONS_) <- (
    Label(BINARY_, LABELED_) and
    COUNT_ is ++(int(LABELED_['num_features'])) and
    FindObjects(LABELED_['label_array'], REGIONS_)
)
```

### Remove small noise blobs with morphological opening

```
-import_from(scipy_ndimage, [BinaryOpening])

RemoveNoise(RAW_, CLEAN_) <- (
    BinaryOpening(RAW_, CLEAN_)
)
```

---

## Notes

- **Array inputs**: pass Python lists or NumPy arrays via `++()`.
- **Default boundary handling**: all filter and convolution predicates use
  `mode='reflect'` by default; all geometric predicates use `mode='constant'`
  with `cval=0.0`. To use other modes, call the underlying scipy function
  directly via `++()`.
- **`Label` result**: `RESULT['label_array']` is a NumPy integer array;
  `RESULT['num_features']` is a Python int. Access dict values inside
  `++()` expressions: `++(int(RESULT['num_features']))`.
- **`FindObjects` input**: pass the `label_array` value from
  `Label`, not the raw binary array.
- **`CenterOfMass` output**: for a 1-D array the result is a 1-tuple
  `(centre,)`; for a 2-D array it is `(row, col)`. Index with `++(COM[0])`.
- Predicates fail (no solution) when scipy raises an exception, or when a
  bound `RESULT` does not unify with the computed value.
