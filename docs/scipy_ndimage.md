# scipy.ndimage — N-dimensional Image Processing

The `scipy_ndimage` module wraps [`scipy.ndimage`](https://docs.scipy.org/doc/scipy/reference/ndimage.html) as Clausal predicates. It covers smoothing filters, convolution, morphological operations, connected-component labelling, geometric transforms, and measurement functions.

---

## Import

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:import"
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:import_ex2"
```

---

## Tier

All predicates are **Tier 1 — pure functions**: NumPy array in, result directly in `RESULT`. No result dicts that need a `ResultGet` accessor (except `label`, which returns a plain Python dict with named keys you can access directly).

---

## Naming conventions

Predicates are imported from `scipy_ndimage`, so there is no module prefix in the name — each predicate is just the operation name in `TitleCase`.

| scipy function | Clausal predicate |
|---|---|
| `gaussian_filter` | `GaussianFilter` |
| `uniform_filter` | `UniformFilter` |
| `median_filter` | `MedianFilter` |
| `convolve` | `Convolve` |
| `label` | `label` |
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

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:smoothing_filters"
```

Example — smooth a noisy 1-D signal:

```clausal
-import_from(scipy_ndimage, [GaussianFilter])

SmoothSignal(NOISY, SMOOTHED) <- (
    GaussianFilter(NOISY, ++(2.0), SMOOTHED)
)
```

---

### Convolution

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:convolution"
```

Example — edge detection with a simple difference kernel:

```clausal
-import_from(scipy_ndimage, [Convolve])

EdgeDetect(SIGNAL, EDGES) <- (
    KERNEL is ++([-1.0, 0.0, 1.0]),
    Convolve(SIGNAL, KERNEL, EDGES)
)
```

---

### Connected-component labelling

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:connected_component_labelling"
```

Example — count blobs in a binary image:

```clausal
-import_from(scipy_ndimage, [label])

CountBlobs(IMAGE, COUNT) <- (
    label(IMAGE, LABELED),
    COUNT is ++(int(LABELED['num_features']))
)
```

---

### Morphological operations

All four predicates operate on boolean (or 0/1 integer) arrays and use the
default 3×3 (or 3-point in 1-D) structuring element.

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:morphological_operations"
```

Example — remove noise then fill gaps in a binary mask:

```clausal
-import_from(scipy_ndimage, [BinaryOpening, BinaryClosing])

CleanMask(RAW_MASK, CLEAN) <- (
    BinaryOpening(RAW_MASK, OPENED),
    BinaryClosing(OPENED, CLEAN)
)
```

---

### Geometric transforms

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:geometric_transforms"
```

Example — centre-crop after zoom:

```clausal
-import_from(scipy_ndimage, [Zoom])

ZoomImage(IMAGE, FACTOR, ZOOMED) <- (
    Zoom(IMAGE, FACTOR, ZOOMED)
)
```

---

### Measurement

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:measurement"
```

Example — find the centroid of a blob:

```clausal
-import_from(scipy_ndimage, [label, CenterOfMass])

BlobCentroid(BINARY_IMAGE, CENTROID) <- (
    label(BINARY_IMAGE, LABELED),
    CenterOfMass(BINARY_IMAGE, CENTROID)
)
```

---

## Complete examples

### Gaussian smoothing and edge detection

```clausal
-import_from(scipy_ndimage, [GaussianFilter, Convolve])

ProcessSignal(NOISY, SMOOTHED, EDGES) <- (
    GaussianFilter(NOISY, ++(1.5), SMOOTHED),
    KERNEL is ++([-1.0, 0.0, 1.0]),
    Convolve(SMOOTHED, KERNEL, EDGES)
)
```

### label and count connected components

```clausal
-import_from(scipy_ndimage, [label, FindObjects])

LabelAndLocate(BINARY, COUNT, REGIONS) <- (
    label(BINARY, LABELED),
    COUNT is ++(int(LABELED['num_features'])),
    FindObjects(LABELED['label_array'], REGIONS)
)
```

### Remove small noise blobs with morphological opening

```clausal
-import_from(scipy_ndimage, [BinaryOpening])

RemoveNoise(RAW, CLEAN) <- (
    BinaryOpening(RAW, CLEAN)
)
```

---

## Notes

- **Array inputs**: pass Python lists or NumPy arrays via [`++()`](python_integration.md).
- **Default boundary handling**: all filter and convolution predicates use
  `mode='reflect'` by default; all geometric predicates use `mode='constant'`
  with `cval=0.0`. To use other modes, call the underlying scipy function
  directly via `++()`.
- **`label` result**: `RESULT['label_array']` is a NumPy integer array;
  `RESULT['num_features']` is a Python int. Access dict values inside
  `++()` expressions: `++(int(RESULT['num_features']))`.
- **`FindObjects` input**: pass the `label_array` value from
  `label`, not the raw binary array.
- **`CenterOfMass` output**: for a 1-D array the result is a 1-tuple
  `(centre,)`; for a 2-D array it is `(row, col)`. Index with `++(COM[0])`.
- Predicates fail (no solution) when scipy raises an exception, or when a
  bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.interpolate](scipy_interpolate.md) — image resampling and interpolation.*
