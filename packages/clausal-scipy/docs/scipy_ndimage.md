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
| `gaussian_filter` | `gaussian_filter` |
| `uniform_filter` | `uniform_filter` |
| `median_filter` | `median_filter` |
| `convolve` | `convolve` |
| `label` | `label` |
| `binary_erosion` | `binary_erosion` |
| `binary_dilation` | `binary_dilation` |
| `binary_opening` | `binary_opening` |
| `binary_closing` | `binary_closing` |
| `zoom` | `zoom` |
| `rotate` | `rotate` |
| `shift` | `shift` |
| `find_objects` | `find_objects` |
| `center_of_mass` | `center_of_mass` |

---

## Predicate catalogue

### Smoothing filters

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:smoothing_filters"
```

Example — smooth a noisy 1-D signal:

```clausal
-import_from(scipy_ndimage, [gaussian_filter])

smooth_signal(NOISY, SMOOTHED) <- (
    gaussian_filter(NOISY, ++(2.0), SMOOTHED)
)
```

---

### Convolution

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:convolution"
```

Example — edge detection with a simple difference kernel:

```clausal
-import_from(scipy_ndimage, [convolve])

edge_detect(SIGNAL, EDGES) <- (
    KERNEL is ++([-1.0, 0.0, 1.0]),
    convolve(SIGNAL, KERNEL, EDGES)
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

count_blobs(IMAGE, COUNT) <- (
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
-import_from(scipy_ndimage, [binary_opening, binary_closing])

clean_mask(RAW_MASK, CLEAN) <- (
    binary_opening(RAW_MASK, OPENED),
    binary_closing(OPENED, CLEAN)
)
```

---

### Geometric transforms

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:geometric_transforms"
```

Example — centre-crop after zoom:

```clausal
-import_from(scipy_ndimage, [zoom])

zoom_image(IMAGE, FACTOR, ZOOMED) <- (
    zoom(IMAGE, FACTOR, ZOOMED)
)
```

---

### Measurement

```clausal
--8<-- "tests/fixtures/docs/scipy_ndimage_sigs.txt:measurement"
```

Example — find the centroid of a blob:

```clausal
-import_from(scipy_ndimage, [label, center_of_mass])

blob_centroid(BINARY_IMAGE, CENTROID) <- (
    label(BINARY_IMAGE, LABELED),
    center_of_mass(BINARY_IMAGE, CENTROID)
)
```

---

## Complete examples

### Gaussian smoothing and edge detection

```clausal
-import_from(scipy_ndimage, [gaussian_filter, convolve])

process_signal(NOISY, SMOOTHED, EDGES) <- (
    gaussian_filter(NOISY, ++(1.5), SMOOTHED),
    KERNEL is ++([-1.0, 0.0, 1.0]),
    convolve(SMOOTHED, KERNEL, EDGES)
)
```

### label and count connected components

```clausal
-import_from(scipy_ndimage, [label, find_objects])

label_and_locate(BINARY, COUNT, REGIONS) <- (
    label(BINARY, LABELED),
    COUNT is ++(int(LABELED['num_features'])),
    find_objects(LABELED['label_array'], REGIONS)
)
```

### Remove small noise blobs with morphological opening

```clausal
-import_from(scipy_ndimage, [binary_opening])

remove_noise(RAW, CLEAN) <- (
    binary_opening(RAW, CLEAN)
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
- **`find_objects` input**: pass the `label_array` value from
  `label`, not the raw binary array.
- **`center_of_mass` output**: for a 1-D array the result is a 1-tuple
  `(centre,)`; for a 2-D array it is `(row, col)`. Index with `++(COM[0])`.
- Predicates fail (no solution) when scipy raises an exception, or when a
  bound `RESULT` does not unify with the computed value.

---

*See also: [scipy.interpolate](scipy_interpolate.md) — image resampling and interpolation.*
